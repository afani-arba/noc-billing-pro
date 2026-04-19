"""
GenieACS router: endpoints for managing TR-069 CPE devices via GenieACS NBI.
All endpoints prefixed with /genieacs
"""
import asyncio
import logging
import uuid
from datetime import datetime, timezone
from typing import Optional
from fastapi import APIRouter, HTTPException, Depends, Query
from pydantic import BaseModel
from core.auth import get_current_user, require_admin, require_noc, get_user_allowed_devices
from core.db import get_db
from services import genieacs_service as svc
from mikrotik_api import get_api_client

router = APIRouter(prefix="/genieacs", tags=["genieacs"])
logger = logging.getLogger(__name__)


def _now():
    return datetime.now(timezone.utc).isoformat()


def _err(e: Exception, default="GenieACS error"):
    msg = str(e)
    if "Connection refused" in msg or "Failed to establish" in msg or "Max retries" in msg:
        raise HTTPException(503, "Tidak dapat terhubung ke GenieACS. Pastikan GENIEACS_URL benar dan server GenieACS aktif.")
    if "401" in msg or "Unauthorized" in msg:
        # PENTING: Jangan forward 401 ke frontend — frontend akan logout!
        # 401 dari GenieACS = kredensial salah, bukan token user NOC.
        raise HTTPException(503, "Autentikasi GenieACS gagal. Periksa GENIEACS_USERNAME dan GENIEACS_PASSWORD di Konfigurasi Server.")
    if "404" in msg:
        raise HTTPException(404, "Device tidak ditemukan di GenieACS.")
    raise HTTPException(503, f"{default}: {msg}")


# ── Stats ─────────────────────────────────────────────────────────────────────

@router.get("/stats")
async def get_stats(user=Depends(get_current_user)):
    """Overall GenieACS stats: total, online, offline, faults."""
    try:
        return await asyncio.to_thread(svc.get_stats)
    except HTTPException:
        raise
    except Exception as e:
        _err(e, "Failed to get stats")


# ── Devices ───────────────────────────────────────────────────────────────────

@router.get("/devices")
async def list_devices(
    limit: int = Query(200, le=5000),
    search: str = Query(""),
    model: str = Query(""),
    user=Depends(get_current_user),
):
    """List CPE devices with optional search/filter.
    
    RBAC Logic:
    - Admin (super_admin/administrator): semua CPE ditampilkan
    - User dengan allowed_devices: 
        * CPE yang sudah punya PPPoE username → filter berdasarkan customer yang terdaftar
        * CPE baru (belum punya PPPoE username) → cek IP-nya via DHCP lease ke MikroTik yang diizinkan
        * ZTP tetap bisa digunakan untuk CPE yang IP-nya masuk ke range MikroTik user
    """
    try:
        devices = await asyncio.to_thread(svc.get_devices, limit, search, model)
        normalized = _normalize_devices(devices)

        # ── RBAC: filter berdasarkan allowed_devices user ────────────────────────
        scope = get_user_allowed_devices(user)  # None = admin (semua), list = terbatas
        if scope is None or len(scope) == 0:
            # Admin atau user tanpa restriction → tampilkan semua
            return normalized

        # User terbatas → pisahkan CPE berdasarkan apakah sudah punya PPPoE username
        db = get_db()

        # 1. Ambil semua PPPoE username dari customer yang terkait ke allowed devices
        allowed_customers = await db.customers.find(
            {"device_id": {"$in": scope}},
            {"_id": 0, "username": 1, "pppoe_username": 1}
        ).to_list(5000)
        allowed_usernames = set()
        for c in allowed_customers:
            if c.get("username"): allowed_usernames.add(c["username"].lower())
            if c.get("pppoe_username"): allowed_usernames.add(c["pppoe_username"].lower())

        # 2. Ambil info MikroTik yang diizinkan (untuk cek DHCP lease)
        allowed_mt_devices = await db.devices.find(
            {"id": {"$in": scope}},
            {"_id": 0, "id": 1, "name": 1, "ip_address": 1, "api_mode": 1,
             "api_username": 1, "api_password": 1, "api_port": 1,
             "use_https": 1, "api_ssl": 1, "api_plaintext_login": 1}
        ).to_list(100)

        # 3. Kumpulkan semua IP dari DHCP leases di MikroTik yang diizinkan
        dhcp_lease_ips = set()
        for mt in allowed_mt_devices:
            try:
                from mikrotik_api import get_api_client
                client = get_api_client(mt)
                leases = await asyncio.to_thread(client.list_dhcp_leases)
                for lease in (leases or []):
                    ip = lease.get("address") or lease.get("ip-address") or ""
                    if ip:
                        dhcp_lease_ips.add(ip.strip())
            except Exception as e:
                logger.debug(f"DHCP lease check failed for {mt.get('name')}: {e}")

        # 4. Filter CPE
        filtered = []
        for d in normalized:
            pppoe_user = d.get("pppoe_username", "")
            # management_ip = IP dari mana CPE terhubung ke GenieACS (dari DHCP MikroTik)
            management_ip = d.get("management_ip", "")

            if pppoe_user:
                # CPE sudah terkonfigurasi → cek berdasarkan PPPoE username customer
                if pppoe_user.lower() in allowed_usernames:
                    filtered.append(d)
            else:
                # CPE baru (belum ada PPPoE username) → cek management IP via DHCP lease MikroTik
                # Ini memastikan ZTP tetap berfungsi untuk user yang CPE-nya berada di MikroTik mereka
                if not dhcp_lease_ips:
                    # Tidak bisa cek DHCP (koneksi MikroTik gagal) → tampilkan semua CPE baru
                    filtered.append(d)
                elif management_ip and management_ip in dhcp_lease_ips:
                    # Management IP CPE ada di DHCP lease MikroTik yang diizinkan → tampilkan
                    filtered.append(d)
                elif not management_ip:
                    # Tidak ada management IP sama sekali → tampilkan (CPE belum terhubung)
                    filtered.append(d)

        return filtered
    except HTTPException:
        raise
    except Exception as e:
        _err(e, "Failed to list devices")


@router.get("/devices/{device_id:path}")
async def get_device(device_id: str, user=Depends(get_current_user)):
    """Get detailed info + parameter tree for one device."""
    try:
        return await asyncio.to_thread(svc.get_device, device_id)
    except HTTPException:
        raise
    except Exception as e:
        _err(e, "Failed to get device")


# ── Actions ───────────────────────────────────────────────────────────────────

@router.post("/devices/{device_id:path}/reboot")
async def reboot_device(device_id: str, user=Depends(require_admin)):
    """Send reboot command to CPE."""
    try:
        result = await asyncio.to_thread(svc.reboot_device, device_id)
        return {"message": "Perintah reboot dikirim ke device", "result": result}
    except HTTPException:
        raise
    except Exception as e:
        _err(e, "Reboot failed")


@router.post("/devices/{device_id:path}/factory-reset")
async def factory_reset(device_id: str, user=Depends(require_admin)):
    """Send factory reset to CPE."""
    try:
        result = await asyncio.to_thread(svc.factory_reset_device, device_id)
        return {"message": "Perintah factory reset dikirim", "result": result}
    except HTTPException:
        raise
    except Exception as e:
        _err(e, "Factory reset failed")


@router.post("/devices/{device_id:path}/refresh")
async def refresh_device(device_id: str, user=Depends(require_admin)):
    """Refresh all parameters from CPE."""
    try:
        result = await asyncio.to_thread(svc.refresh_device, device_id)
        return {"message": "Refresh parameter dikirim", "result": result}
    except HTTPException:
        raise
    except Exception as e:
        _err(e, "Refresh failed")


@router.post("/devices/{device_id:path}/set-parameter")
async def set_param(device_id: str, body: dict, user=Depends(require_admin)):
    """Set a specific TR-069 parameter on device."""
    name = body.get("name")
    value = body.get("value", "")
    type_ = body.get("type", "xsd:string")
    if not name:
        raise HTTPException(400, "Parameter name wajib diisi")
    try:
        result = await asyncio.to_thread(svc.set_parameter, device_id, name, value, type_)
        return {"message": f"Parameter {name} berhasil diset", "result": result}
    except HTTPException:
        raise
    except Exception as e:
        _err(e, "Set parameter failed")


@router.post("/devices/{device_id:path}/provision")
async def provision_device(device_id: str, body: dict, user=Depends(require_admin)):
    """ZTP: Configure PPPoE and WiFi."""
    pppoe_user = body.get("pppoe_user", "")
    pppoe_pass = body.get("pppoe_pass", "")
    ssid = body.get("ssid", "")
    wifi_pass = body.get("wifi_pass", "")
    try:
        result = await asyncio.to_thread(svc.provision_cpe, device_id, pppoe_user, pppoe_pass, ssid, wifi_pass)
        return result
    except HTTPException:
        raise
    except Exception as e:
        _err(e, "Provisioning failed")


@router.get("/devices/{device_id:path}/wifi")
async def get_wifi(device_id: str, user=Depends(get_current_user)):
    """Get WiFi SSID and Password."""
    try:
        return await asyncio.to_thread(svc.get_wifi_settings, device_id)
    except HTTPException:
        raise
    except Exception as e:
        _err(e, "Failed to get WiFi settings")


@router.put("/devices/{device_id:path}/wifi")
async def update_wifi(device_id: str, body: dict, user=Depends(require_admin)):
    """Update WiFi SSID and Password."""
    ssid = body.get("ssid", "")
    password = body.get("password", "")
    try:
        result = await asyncio.to_thread(svc.set_wifi_settings, device_id, ssid, password)
        return result
    except HTTPException:
        raise
    except Exception as e:
        _err(e, "Failed to update WiFi settings")


@router.post("/devices/{device_id:path}/hard-isolate")
async def hard_isolate_device(device_id: str, body: dict, user=Depends(require_admin)):
    """Enable or disable WiFi radio (Hardcore Isolation)."""
    enable_isolation = body.get("enable", True)
    try:
        result = await asyncio.to_thread(svc.set_hard_isolation, device_id, enable_isolation)
        return result
    except HTTPException:
        raise
    except Exception as e:
        _err(e, "Hard isolation failed")


# ── Faults ────────────────────────────────────────────────────────────────────

@router.get("/faults")
async def list_faults(limit: int = Query(100), user=Depends(get_current_user)):
    try:
        return await asyncio.to_thread(svc.get_faults, limit)
    except HTTPException:
        raise
    except Exception as e:
        _err(e, "Failed to get faults")


@router.delete("/faults/{fault_id:path}")
async def delete_fault(fault_id: str, user=Depends(require_admin)):
    try:
        return await asyncio.to_thread(svc.delete_fault, fault_id)
    except HTTPException:
        raise
    except Exception as e:
        _err(e, "Failed to delete fault")


# ── Presets & Files ───────────────────────────────────────────────────────────

@router.get("/presets")
async def list_presets(user=Depends(get_current_user)):
    try:
        return await asyncio.to_thread(svc.get_presets)
    except HTTPException:
        raise
    except Exception as e:
        _err(e, "Failed to get presets")


@router.get("/files")
async def list_files(user=Depends(get_current_user)):
    try:
        return await asyncio.to_thread(svc.get_files)
    except HTTPException:
        raise
    except Exception as e:
        _err(e, "Failed to get files")


# ── Test Connection ───────────────────────────────────────────────────────────

@router.get("/test-connection")
async def test_connection(user=Depends(require_admin)):
    """Test connectivity to GenieACS server using current env settings."""
    try:
        from services.genieacs_service import check_health
        res = await asyncio.to_thread(check_health)
        return {
            "success": res.get("connected", False),
            "message": "Terhubung dengan sukses ke server GenieACS." if res.get("connected") else "Gagal menghubungi server GenieACS.",
            "error": res.get("error", ""),
            "latency": res.get("latency_ms", 0)
        }
    except Exception as e:
        return {"success": False, "message": "Kesalahan sistem", "error": str(e), "latency": 0}

@router.post("/devices/{device_id:path}/summon")
async def summon_device(device_id: str, user=Depends(require_noc)):
    """Trigger connection request to CPE (summon device to check in). Allowed: noc_engineer, admin."""
    try:
        result = await asyncio.to_thread(svc.summon_device, device_id)
        status = result.get("status", "?")
        if result.get("online"):
            return {"message": f"Device merespons (online) — connection request terkirim. Status: {status}", "result": result}
        else:
            return {"message": f"Device offline — task diantrekan untuk saat device check-in berikutnya. Status: {status}", "result": result}
    except HTTPException:
        raise
    except Exception as e:
        _err(e, "Summon failed")


@router.post("/bulk-reboot")
async def bulk_reboot(
    body: dict,
    user=Depends(require_admin),
):
    """
    Bulk reboot ONT via GenieACS.
    Terima: {device_ids: ["id1", "id2"]} atau {filter: "offline"}
    Return: {success, failed, total, results}
    """
    device_ids: list[str] = body.get("device_ids", [])
    filter_mode: str = body.get("filter", "")  # "offline" = otomatis ambil semua offline

    # Jika filter=offline, ambil semua device yang offline dari GenieACS
    if filter_mode == "offline" and not device_ids:
        try:
            all_devices = await asyncio.to_thread(svc.get_devices, 500, "", "")
            device_ids = [
                d.get("_id", "")
                for d in all_devices
                if not _is_online(d)
            ]
        except Exception as e:
            raise HTTPException(503, f"Gagal ambil daftar device offline: {e}")

    if not device_ids:
        return {"message": "Tidak ada device yang perlu di-reboot", "success": 0, "failed": 0, "total": 0, "results": []}

    async def _do_reboot(dev_id: str) -> dict:
        try:
            result = await asyncio.to_thread(svc.reboot_device, dev_id)
            return {"device_id": dev_id, "success": True, "message": "Reboot task dikirim", "result": result}
        except Exception as e:
            return {"device_id": dev_id, "success": False, "message": str(e)}

    # Concurrent reboot — batching 20 per wave agar tidak overload GenieACS
    BATCH = 20
    all_results = []
    for i in range(0, len(device_ids), BATCH):
        batch = device_ids[i:i + BATCH]
        batch_results = await asyncio.gather(*[_do_reboot(did) for did in batch])
        all_results.extend(batch_results)

    success = sum(1 for r in all_results if r["success"])
    failed = len(all_results) - success

    return {
        "message": f"Bulk reboot selesai: {success} berhasil, {failed} gagal",
        "success": success,
        "failed": failed,
        "total": len(all_results),
        "results": all_results,
    }


def _is_online(device: dict) -> bool:
    """Cek apakah device GenieACS online (last_inform < 15 menit)."""
    from datetime import datetime, timezone, timedelta
    last = device.get("_lastInform", "")
    if not last:
        return False
    try:
        dt = datetime.fromisoformat(last.replace("Z", "+00:00"))
        return dt > datetime.now(timezone.utc) - timedelta(minutes=15)
    except Exception:
        return False


# ── Helpers ───────────────────────────────────────────────────────────────────


# ── ZTP: Activation Options ───────────────────────────────────────────────────

@router.get("/activation-options")
async def get_activation_options(user=Depends(get_current_user)):
    """
    Return dropdown data for ZTP activation form:
    - mikrotik_devices: list of registered MikroTik routers
    - billing_packages: list of active PPPoE billing packages
    """
    db = get_db()
    try:
        scope = get_user_allowed_devices(user)
        query = {}
        if scope is not None:
            query["id"] = {"$in": scope}
            
        devices = await db.devices.find(
            query, {"_id": 0, "id": 1, "name": 1, "ip_address": 1, "api_mode": 1}
        ).to_list(200)
        
        # Cari di 'type' atau 'service_type' agar paket hasil sync MikroTik muncul
        packages = await db.billing_packages.find(
            {
                "active": True, 
                "$or": [
                    {"type": {"$in": ["pppoe", "both"]}},
                    {"service_type": {"$in": ["pppoe", "both"]}}
                ]
            },
            {"_id": 0, "id": 1, "name": 1, "price": 1, "speed_up": 1, "speed_down": 1, "profile_name": 1}
        ).to_list(200)
        
        return {"mikrotik_devices": devices, "billing_packages": packages}
    except Exception as e:
        raise HTTPException(500, f"Gagal ambil data opsi aktivasi: {e}")


@router.get("/mikrotik-profiles/{device_id}")
async def get_mikrotik_profiles(device_id: str, user=Depends(get_current_user)):
    """Fetch all PPP profiles from a MikroTik device."""
    db = get_db()
    device = await db.devices.find_one({"id": device_id})
    if not device:
        raise HTTPException(404, "MikroTik device tidak ditemukan")
    
    try:
        mt = get_api_client(device)
        profiles = await mt.list_pppoe_profiles()
        return [{"name": p.get("name")} for p in profiles if p.get("name")]
    except Exception as e:
        logger.error(f"Failed to fetch profiles from MT {device_id}: {e}")
        return []


# ── ZTP: Activate Customer (1-Click) ──────────────────────────────────────────

class ZTPActivateRequest(BaseModel):
    customer_name: str
    phone: str = ""
    address: str = ""
    pppoe_username: str
    pppoe_password: str
    mikrotik_device_id: str          # UUID router MikroTik di DB
    mikrotik_profile: str = ""       # Manual PPP Profile selection
    package_id: str = ""             # UUID paket billing
    due_day: int = 10
    ssid: str = ""                   # nama WiFi yang akan dipush ke ONT
    wifi_password: str = ""          # password WiFi ONT
    vlan_id: str = ""                # VLAN ID untuk WAN PPPoE (ZTE)
    installation_fee: int = 0
    billing_type: str = "prepaid"        # prepaid | postpaid
    payment_status: str = "belum_bayar"  # sudah_bayar | belum_bayar
    initial_payment_method: str = "cash" # cash | transfer
    use_radius: bool = True              # Gunakan RADIUS sebagai default
    bind_lan: list[str] = []             # List of LANs, e.g. ["LAN1"]
    bind_ssid: list[str] = []            # List of SSIDs, e.g. ["SSID1"]


@router.post("/devices/{device_id:path}/activate-customer")
async def activate_customer_ztp(
    device_id: str,
    body: ZTPActivateRequest,
    user=Depends(require_admin),
):
    """
    Zero Touch Provisioning: Aktivasi pelanggan baru dalam 1 klik.
    Eksekusi 3 step secara berurutan:
      1. Buat PPPoE Secret di MikroTik
      2. Push PPPoE + WiFi config ke ONT via GenieACS/TR-069
      3. Daftarkan customer ke sistem billing

    Setiap step dicatat hasilnya. Jika ada step yang gagal,
    step berikutnya tetap dicoba dan hasil partial dikembalikan
    sehingga admin bisa retry step yang gagal secara manual.
    """
    db = get_db()
    steps = []  # list of {step, ok, message}

    # ─── Validate & fetch supporting data ────────────────────────────────────
    # Validate MikroTik device
    mt_device = await db.devices.find_one({"id": body.mikrotik_device_id}, {"_id": 0})
    if not mt_device:
        raise HTTPException(404, "MikroTik device tidak ditemukan di database")

    # Fetch profile name (Priority: manual selection > package suggested)
    profile_name = body.mikrotik_profile
    pkg = None
    if body.package_id:
        pkg = await db.billing_packages.find_one({"id": body.package_id}, {"_id": 0})
        if pkg and not profile_name:
            profile_name = pkg.get("profile_name", "") or pkg.get("name", "")

    # Generate client_id for billing
    import random, string
    client_id = ''.join(random.choices(string.digits, k=10))

    # ─── STEP 1: Create PPPoE Secret on MikroTik ─────────────────────────────
    mt_ok = False
    if body.use_radius:
        mt_ok = True
        steps.append({
            "step": "MikroTik PPPoE Secret",
            "ok": True,
            "message": "Dilewati: Menggunakan server autenfikasi terpusat (RADIUS)"
        })
        logger.info(f"ZTP: Skipping PPPoE secret creation for '{body.pppoe_username}' (RADIUS mode)")
    else:
        try:
            mt = get_api_client(mt_device)
            is_disabled = (body.billing_type == "prepaid" and body.payment_status == "belum_bayar")
            secret_data = {
                "name":     body.pppoe_username,
                "password": body.pppoe_password,
                "service":  "ppp",
                "disabled": "yes" if is_disabled else "no",
            }
            if profile_name:
                secret_data["profile"] = profile_name
            if body.customer_name:
                secret_data["comment"] = body.customer_name
    
            await mt.create_pppoe_secret(secret_data)
            mt_ok = True
            steps.append({
                "step": "MikroTik PPPoE Secret",
                "ok": True,
                "message": f"PPPoE Secret '{body.pppoe_username}' berhasil dibuat"
                           + (f" dengan profile '{profile_name}'" if profile_name else "")
            })
            logger.info(f"ZTP: PPPoE secret '{body.pppoe_username}' created on {mt_device.get('name')}")
        except Exception as e:
            steps.append({
                "step": "MikroTik PPPoE Secret",
                "ok": False,
                "message": f"Gagal membuat PPPoE Secret: {e}"
            })
            logger.warning(f"ZTP step1 failed for {body.pppoe_username}: {e}")

    # ─── STEP 2: Provision ONT via GenieACS ──────────────────────────────────
    genieacs_ok = False
    try:
        result = await asyncio.to_thread(
            svc.provision_cpe,
            device_id,
            body.pppoe_username,
            body.pppoe_password,
            body.ssid,
            body.wifi_password,
            body.vlan_id,
            body.bind_lan,
            body.bind_ssid,
        )
        genieacs_ok = True
        steps.append({
            "step": "GenieACS / TR-069 Provision",
            "ok": True,
            "message": "Konfigurasi PPPoE dan WiFi berhasil dikirim ke ONT"
        })
        # ─── AUTO SUMMON ──────────────────────────────────────────────────────
        # Force ONT to check-in so status updates immediately
        try:
            await asyncio.to_thread(svc.summon_device, device_id)
            logger.info(f"ZTP: Auto-summon triggered for {device_id}")
        except Exception: pass

        logger.info(f"ZTP: ONT {device_id} provisioned (PPPoE={body.pppoe_username}, SSID={body.ssid})")
    except Exception as e:
        steps.append({
            "step": "GenieACS / TR-069 Provision",
            "ok": False,
            "message": f"Gagal provision ONT (mungkin ONT sedang offline): {e}"
        })
        logger.warning(f"ZTP step2 failed for device {device_id}: {e}")

    # ─── STEP 3: Create Customer in Billing DB ────────────────────────────────
    billing_ok = False
    customer_id = str(uuid.uuid4())
    try:
        customer_doc = {
            "id":           customer_id,
            "client_id":    client_id,
            "name":         body.customer_name,
            "phone":        body.phone,
            "address":      body.address,
            "service_type": "pppoe",
            "username":     body.pppoe_username,
            "device_id":    body.mikrotik_device_id,
            "package_id":   body.package_id,
            "due_day":      body.due_day,
            "billing_type": body.billing_type,
            "active":       True,
            "auth_method":  "radius" if body.use_radius else "local",
            "password":     body.pppoe_password,
            "start_date":   _now(),      # untuk perhitungan prorata
            "profile":      profile_name,
            "ont_device_id": device_id,  # referensi ke GenieACS device ID
            "created_at":   _now(),
            "created_by":   user.get("username", "") if isinstance(user, dict) else getattr(user, "username", ""),
        }
        await db.customers.insert_one(customer_doc)
        customer_doc.pop("_id", None)
        billing_ok = True
        steps.append({
            "step": "Billing — Pendaftaran Pelanggan",
            "ok": True,
            "message": f"Pelanggan '{body.customer_name}' (ID: {client_id}) berhasil didaftarkan"
        })
        logger.info(f"ZTP: customer '{body.customer_name}' ({client_id}) registered in billing")
    except Exception as e:
        steps.append({
            "step": "Billing — Pendaftaran Pelanggan",
            "ok": False,
            "message": f"Gagal mendaftarkan pelanggan di sistem billing: {e}"
        })
        logger.warning(f"ZTP step3 failed for {body.customer_name}: {e}")

    # ─── STEP 4: Create Initial Invoice (Biaya Pasang + Bulan Pertama + Pro-Rata) ─
    invoice_ok = True
    inv_doc = None   # kita butuh referensi ini di STEP 5 (WA notification)
    if billing_ok and (body.installation_fee > 0 or body.package_id):
        try:
            from datetime import date
            from calendar import monthrange

            def _inv_num(seq: int) -> str:
                d = date.today()
                return f"INV-{d.year}-{d.month:02d}-{seq:04d}"

            today = date.today()
            _, last_day = monthrange(today.year, today.month)

            # ── Pro-Rata Calculation ──────────────────────────────────────────
            # Hitung biaya paket berdasarkan sisa hari di bulan berjalan.
            # Biaya pasang (installation_fee) TIDAK ikut pro-rata, selalu penuh.
            #
            # Rumus: round((harga_paket / total_hari) * sisa_hari)
            # Contoh: Pasang tgl 20, hari dlm bulan = 30 → sisa = 11 hari
            #   Pro-rata = round((100_000 / 30) * 11) = 36_667
            #
            # Jika pasang di tanggal 1 atau sisa >= total hari → tagih PENUH.
            pkg_price_full = pkg.get("price", 0) if pkg else 0
            days_remaining = last_day - today.day + 1   # termasuk hari ini
            is_prorata = days_remaining < last_day       # False jika pasang tgl 1

            if is_prorata and pkg_price_full > 0:
                pkg_price_prorata = round((pkg_price_full / last_day) * days_remaining)
                prorata_note = (
                    f"Pro-Rata {days_remaining}/{last_day} hari "
                    f"(Rp {pkg_price_full:,} × {days_remaining}/{last_day} = Rp {pkg_price_prorata:,})"
                )
            else:
                pkg_price_prorata = pkg_price_full
                prorata_note = "Tagihan penuh (pasang awal bulan)"

            amount = pkg_price_prorata + body.installation_fee

            # Period billing: hari ini → akhir bulan berjalan
            period_start = today.isoformat()
            period_end   = f"{today.year}-{today.month:02d}-{last_day:02d}"
            due_day_safe = min(body.due_day, last_day)
            due_date     = f"{today.year}-{today.month:02d}-{due_day_safe:02d}"

            period_prefix = f"{today.year}-{today.month:02d}"
            count = await db.invoices.count_documents(
                {"period_start": {"$regex": f"^{period_prefix}"}}
            )

            if amount > 0:
                # ── Unique Code: hanya untuk pembayaran transfer ──────────────
                # Pembayaran cash/tunai → kode unik = 0 (total tepat = amount)
                # Pembayaran transfer   → kode unik = random 1-999 (agar unik di bank)
                is_transfer = body.initial_payment_method.lower() in ("transfer", "bank_transfer", "online")
                if is_transfer:
                    import random
                    unique_code = random.randint(1, 999)
                else:
                    unique_code = 0   # Cash/QRIS scan = nominal persis, tidak perlu kode unik

                total = amount + unique_code
                is_paid = (body.payment_status == "sudah_bayar")

                notes_parts = [
                    f"Tagihan Pertama.",
                    f"Paket: Rp {pkg_price_prorata:,}" + (f" (Pro-Rata dari Rp {pkg_price_full:,})" if is_prorata else ""),
                    f"Biaya Pasang: Rp {body.installation_fee:,}",
                    prorata_note,
                ]

                inv_doc = {
                    "id": str(uuid.uuid4()),
                    "invoice_number": _inv_num(count + 1),
                    "customer_id": customer_id,
                    "package_id": body.package_id,
                    "amount": amount,
                    "discount": 0,
                    "unique_code": unique_code,
                    "total": total,
                    "period_start": period_start,
                    "period_end": period_end,
                    "due_date": due_date,
                    "status": "paid" if is_paid else "unpaid",
                    "notes": " | ".join(notes_parts),
                    "paid_at": _now() if is_paid else None,
                    "payment_method": body.initial_payment_method if is_paid else None,
                    "created_at": _now(),
                }
                await db.invoices.insert_one(inv_doc)
                steps.append({
                    "step": "Billing — Invoice Pertama",
                    "ok": True,
                    "message": f"Invoice terbit: {_inv_num(count+1)} (Total Tagihan: Rp {total}) — Status: {inv_doc['status'].upper()}"
                })
                logger.info(f"ZTP: initial invoice created for {customer_id}")
        except Exception as e:
            invoice_ok = False
            steps.append({
                "step": "Billing — Invoice Pertama",
                "ok": False,
                "message": f"Gagal membuat tagihan/invoice otomatis: {e}"
            })
            logger.warning(f"ZTP step4 failed for {body.customer_name}: {e}")

    # ─── STEP 5: Notification (WhatsApp) ──────────────────────────────────────
    if billing_ok and body.phone:
        try:
            from services.notification_service import send_whatsapp
            bs = await db.billing_settings.find_one({}, {"_id": 0}) or {}
            wa_token = bs.get("wa_token", "")
            if wa_token:
                pkg_name     = pkg.get("name", "-") if pkg else "-"
                is_paid_val  = (body.payment_status == "sudah_bayar")
                is_cash      = body.initial_payment_method.lower() not in ("transfer", "bank_transfer", "online")

                # ── Ambil info rekening pembayaran dari company_profile ────────
                company_profile = await db.system_settings.find_one(
                    {"key": "company_profile"}, {"_id": 0}
                ) or {}
                # Fallback ke legacy field jika company_profile kosong
                if not company_profile:
                    company_profile = await db.system_settings.find_one({}, {"_id": 0}) or {}

                bank_account_raw  = (company_profile.get("bank_account") or bs.get("bank_account") or "").strip()
                bank_name         = (company_profile.get("bank_name") or "").strip()
                bank_account_name = (company_profile.get("bank_account_name") or "").strip()
                qris_url          = (company_profile.get("qris_url") or bs.get("qris_url") or "").strip()
                company_name      = (company_profile.get("company_name") or "Internet Kami").strip()

                # ── Header & data pelanggan ───────────────────────────────────
                msg = (
                    f"🎉 *Selamat Datang di {company_name}!*\n\n"
                    f"Halo *{body.customer_name}*,\n"
                    f"Pemasangan layanan internet Anda telah selesai dilakukan oleh teknisi kami.\n\n"
                    f"👤 *Akun Pelanggan*\n"
                    f"• ID Pelanggan : {client_id}\n"
                    f"• No HP        : {body.phone}\n\n"
                    f"📡 *Data Layanan & WiFi*\n"
                    f"• Paket        : {pkg_name}\n"
                    f"• Nama WiFi    : {body.ssid}\n"
                    f"• Password WiFi: {body.wifi_password}\n\n"
                )

                # ── Bagian Tagihan ─────────────────────────────────────────────
                if inv_doc:
                    final_total       = inv_doc.get("total", 0)
                    final_amount      = inv_doc.get("amount", 0)
                    final_unique_code = inv_doc.get("unique_code", 0)
                    inv_number        = inv_doc.get("invoice_number", "-")
                    due_date_str      = inv_doc.get("due_date", "-")

                    if is_paid_val:
                        # ── SUDAH BAYAR: konfirmasi & terima kasih ────────────
                        msg += (
                            f"✅ *Tagihan Awal — LUNAS*\n"
                            f"• No. Invoice  : {inv_number}\n"
                            f"• Total Tagihan: *Rp {final_total:,}*\n"
                            f"• Metode Bayar : {'Tunai' if is_cash else 'Transfer'}\n\n"
                            f"Terima kasih atas pembayaran Anda! 🙏\n"
                            f"Internet Anda sudah aktif dan siap digunakan.\n"
                        )
                    else:
                        # ── BELUM BAYAR: instruksi pembayaran lengkap ─────────
                        msg += (
                            f"💳 *Tagihan Awal — BELUM LUNAS*\n"
                            f"• No. Invoice  : {inv_number}\n"
                            f"• Nominal Paket: Rp {final_amount:,}\n"
                        )
                        if final_unique_code > 0:
                            msg += (
                                f"• Kode Unik    : Rp {final_unique_code:,}\n"
                                f"• *Total Transfer: Rp {final_total:,}*\n"
                                f"  _(Harap transfer tepat sesuai nominal di atas)_\n"
                            )
                        else:
                            msg += f"• *Total Bayar : Rp {final_total:,}*\n"
                        msg += f"• Jatuh Tempo  : {due_date_str}\n\n"

                        # ── Info rekening / QRIS ──────────────────────────────
                        if bank_account_raw or bank_name:
                            msg += f"🏦 *Cara Pembayaran Transfer*\n"
                            if bank_name:
                                msg += f"• Bank         : {bank_name}\n"
                            if bank_account_raw:
                                msg += f"• No. Rekening : *{bank_account_raw}*\n"
                            if bank_account_name:
                                msg += f"• Atas Nama    : {bank_account_name}\n"
                            msg += "\n"

                        if qris_url:
                            msg += (
                                f"📱 *Atau Bayar via QRIS*\n"
                                f"Scan QRIS: {qris_url}\n\n"
                            )

                        msg += (
                            f"⚠️ *Penting:* Internet Anda saat ini dalam status *ISOLIR* "
                            f"dan akan aktif otomatis setelah pembayaran dikonfirmasi.\n"
                        )
                else:
                    # Tidak ada invoice (gratis / bebas biaya awal)
                    msg += f"✅ *Status*: Bebas biaya pemasangan awal. Internet Anda langsung aktif!\n"

                msg += f"\nSalam,\n*Tim {company_name}*"

                ok = await send_whatsapp(body.phone, msg, wa_token)
                if ok:
                    steps.append({
                        "step": "WhatsApp Notification",
                        "ok": True,
                        "message": (
                            f"Pesan {'tagihan & instruksi bayar' if not is_paid_val and inv_doc else 'selamat datang'} "
                            f"berhasil dikirim ke {body.phone}"
                        )
                    })
                    logger.info(f"ZTP: WA sent to {body.phone} for {customer_id} (paid={is_paid_val})")
                else:
                    steps.append({
                        "step": "WhatsApp Notification",
                        "ok": False,
                        "message": "Gagal mengirim WhatsApp (Fonnte API merespon error)"
                    })
            else:
                steps.append({
                    "step": "WhatsApp Notification",
                    "ok": False,
                    "message": "Token Fonnte tidak dikonfigurasi di Pengaturan Billing"
                })
        except Exception as e:
            steps.append({
                "step": "WhatsApp Notification",
                "ok": False,
                "message": f"Kesalahan internal saat memproses WA: {e}"
            })

    # ─── Audit Log ────────────────────────────────────────────────────────────
    try:
        from routers.audit import log_action
        username = user.get("username", "") if isinstance(user, dict) else getattr(user, "username", "")
        user_id  = user.get("id", "")     if isinstance(user, dict) else getattr(user, "id", "")
        ok_count = sum(1 for s in steps if s.get("ok"))
        await log_action(
            action="CREATE",
            resource="ztp_customer",
            resource_id=device_id,
            details=(
                f"ZTP Aktivasi '{body.customer_name}' (PPPoE: {body.pppoe_username}) "
                f"pada ONT {device_id} — {ok_count}/{len(steps)} step berhasil"
            ),
            username=username,
            user_id=user_id,
        )
    except Exception:
        pass

    # ─── Response ─────────────────────────────────────────────────────────────
    all_ok = mt_ok and genieacs_ok and billing_ok and invoice_ok
    failed_steps = [s["step"] for s in steps if not s["ok"]]

    return {
        "success":     all_ok,
        "steps":       steps,
        "customer_id": customer_id if billing_ok else None,
        "client_id":   client_id if billing_ok else None,
        "summary": (
            f"Aktivasi pelanggan '{body.customer_name}' berhasil penuh (3/3 step OK)."
            if all_ok else
            f"Aktivasi selesai dengan {len(failed_steps)} kegagalan: {', '.join(failed_steps)}. "
            "Data yang berhasil sudah tersimpan — silakan coba ulang step yang gagal secara manual."
        )
    }


def _valid_rx(v: str) -> bool:
    """
    Return True jika nilai RX power bermakna (bukan kosong / nol / N/A).
    Alasan: GenieACS kadang mengirim "0", "0.0", integer 0, "-0.0", atau "N/A"
    untuk perangkat yang belum punya data PON — harus di-skip agar fallback
    ke path alternatif.
    """
    if not v or not v.strip():
        return False
    s = v.strip().lower()
    if s in ("n/a", "na", "null", "none", "-"):
        return False
    try:
        return float(s) != 0.0
    except ValueError:
        return bool(s)


def _normalize_devices(devices: list) -> list:
    """Extract key fields from raw GenieACS device objects for list view."""
    from datetime import datetime, timezone, timedelta
    cutoff = datetime.now(timezone.utc) - timedelta(minutes=15)
    result = []
    for d in devices:
        last_inform = d.get("_lastInform", "")
        is_online = False
        if last_inform:
            try:
                dt = datetime.fromisoformat(last_inform.replace("Z", "+00:00"))
                is_online = dt > cutoff
            except Exception:
                pass

        d_igd = d.get("InternetGatewayDevice") or {}
        d_dev = d.get("Device") or {}

        dev_info = d_igd.get("DeviceInfo") or d_dev.get("DeviceInfo") or {}
        device_id = d.get("_id", "")

        # Extract management IP from ConnectionRequestURL (misal: http://192.168.1.100:7547/)
        management_ip = ""
        dev_id_info = d.get("_deviceId", {})
        if isinstance(dev_id_info, dict):
            conn_url = dev_id_info.get("_ConnectionRequestURL", "") or ""
            if conn_url:
                import re
                m = re.search(r'https?://([^:/]+)', conn_url)
                if m:
                    management_ip = m.group(1)
        # Fallback: cek dari ManagementServer.ConnectionRequestURL
        if not management_ip:
            for root in [d_igd, d_dev]:
                mgmt = root.get("ManagementServer", {})
                if isinstance(mgmt, dict):
                    url = _val(mgmt, "ConnectionRequestURL")
                    if url:
                        import re
                        m = re.search(r'https?://([^:/]+)', url)
                        if m:
                            management_ip = m.group(1)
                            break

        # 1. Gather WAN Connections for PPPoE/IP
        conns = []
        for root in [d_igd, d_dev]:
            wan_obj = root.get("WANDevice", {})
            if isinstance(wan_obj, dict):
                for wd in wan_obj.values():
                    if isinstance(wd, dict):
                        wcd_obj = wd.get("WANConnectionDevice", {})
                        if isinstance(wcd_obj, dict):
                            for wcd in wcd_obj.values():
                                if isinstance(wcd, dict):
                                    for ctype in ["WANPPPConnection", "WANIPConnection"]:
                                        cobj = wcd.get(ctype, {})
                                        if isinstance(cobj, dict):
                                            for c in cobj.values():
                                                if isinstance(c, dict): conns.append(c)
            # TR-181 IPs / PPPs
            for ctype in ["PPP", "IP"]:
                intf_obj = root.get(ctype, {}).get("Interface", {})
                if isinstance(intf_obj, dict):
                    for c in intf_obj.values():
                        if isinstance(c, dict): conns.append(c)

        pppoe_username = ""
        pppoe_ip = ""
        for c in conns:
            usr = _val(c, "Username")
            ip = _val(c, "ExternalIPAddress") or _val(c, "IPAddress")
            if usr and not pppoe_username: pppoe_username = usr
            if ip and ip != "0.0.0.0" and not ip.startswith("10.") and not pppoe_ip: 
                pppoe_ip = ip
            if ip and ip != "0.0.0.0" and not pppoe_ip: # fallback
                pppoe_ip = ip

        # 2. Gather LAN/WiFi for SSID, Password, and Active Devices
        ssid = ""
        wifi_password = ""
        active_devices = ""
        for root in [d_igd, d_dev]:
            lan_obj = root.get("LANDevice", {})
            if isinstance(lan_obj, dict):
                for ld in lan_obj.values():
                    if isinstance(ld, dict):
                        wlan_obj = ld.get("WLANConfiguration", {})
                        if isinstance(wlan_obj, dict):
                            for wlan in wlan_obj.values():
                                if isinstance(wlan, dict):
                                    s = _val(wlan, "SSID")
                                    if s and not ssid: ssid = s
                                    # Extract PreSharedKey
                                    psk_obj = wlan.get("PreSharedKey", {})
                                    if isinstance(psk_obj, dict):
                                        for psk in psk_obj.values():
                                            if isinstance(psk, dict):
                                                p = _val(psk, "PreSharedKey")
                                                if p and not wifi_password: 
                                                    wifi_password = p
                        hosts_obj = ld.get("Hosts", {})
                        if isinstance(hosts_obj, dict):
                            h = _val(hosts_obj, "HostNumberOfEntries")
                            if h and h != "0" and not active_devices: active_devices = h
                            
                            h_list = hosts_obj.get("Host", {})
                            if isinstance(h_list, dict):
                                act = 0
                                for k, v in h_list.items():
                                    if isinstance(v, dict):
                                        active_val = _val(v, "Active").lower()
                                        if not active_val or active_val in ("1", "true"):
                                            act += 1
                                
                                if act > 0 and not active_devices: 
                                    active_devices = str(act)
                                elif not active_devices and len(h_list) > 0:
                                    active_devices = str(len([k for k, v in h_list.items() if isinstance(v, dict)]))
        if not active_devices:
            active_devices = "0"

        # Product Class — from DeviceInfo, fallback parse from device ID (OUI-ProductClass-Serial)
        product_class = _val(dev_info, "ProductClass")
        if not product_class and device_id:
            parts = device_id.split("-")
            if len(parts) >= 2:
                product_class = parts[1]

        # Redaman ONT — try VirtualParameters first, then vendor-specific IGD paths
        rx_power = ""
        device_id = d.get("_id", "")

        vp = d.get("VirtualParameters") or {}
        for vp_key in [
            "Optic Rx Power", "Optic RX Power", "Optic RxPower", "RX Power", "Rx Power",
            "RXPower", "RxPower", "OpticRxPower", "opticRxPower", "optic_rx_power",
            "OpticalRxPower", "rxPower", "rx_power", "EponRxPower", "eponRxPower",
            "PonRxPower", "GponRxPower", "RxSignal", "RxOpticalPower", "optical_rx_power", "TransmitPower"
        ]:
            v = _val(vp, vp_key)
            if _valid_rx(v):
                rx_power = v
                break

        if not rx_power:
            # 2. Check WANDevice for ZTE / CT-COM configs
            for root in [d_igd, d_dev]:
                wan_obj = root.get("WANDevice", {})
                if isinstance(wan_obj, dict):
                    for wd in wan_obj.values():
                        if isinstance(wd, dict):
                            for cfg_key in [
                                "X_ZTE-COM_WANPONInterfaceConfig", "X_ZTE-COM_WANEPONInterfaceConfig", "X_ZTE-COM_WANGPONInterfaceConfig",
                                "X_CT-COM_GponInterfaceConfig", "X_CT-COM_EponInterfaceConfig", "X_CT-COM_WANPONInterfaceConfig"
                            ]:
                                cfg_obj = wd.get(cfg_key, {})
                                if isinstance(cfg_obj, dict):
                                    v = _val(cfg_obj, "RXPower") or _val(cfg_obj, "RxPower") or _val(cfg_obj, "Rx_Power") or _val(cfg_obj, "RxOpticalPower")
                                    if _valid_rx(v): rx_power = v; break
                        if rx_power: break
                if rx_power: break

        if not rx_power:
            # 3. Nested ZTE paths langsung di IGD root (older firmware)
            for parent_key, child_key in [
                ("X_ZTE-COM_ONU_PonPower",     "RxPower"), ("X_ZTE-COM_ONU_PonPower",     "Rx_Power"),
                ("X_ZTE-COM_GponOnu",          "RxPower"), ("X_ZTE-COM_GponOnu",          "RxOpticalPower"),
                ("X_ZTE-COM_OntOptics",        "RxPower"), ("X_ZTE-COM_EponOnu",          "RxPower"),
                ("X_ZTE-COM_GPON",             "RxPower"), ("X_FIBERHOME-COM_GponStatus", "RxPower"),
                ("X_CT-COM_GponOntPower",      "RxPower"),
            ]:
                parent = d_igd.get(parent_key, {})
                if isinstance(parent, dict):
                    v = _val(parent, child_key)
                    if _valid_rx(v): rx_power = v; break

        if not rx_power:
            # 4. Check Optical interface (TR-181)
            optical_obj = d_dev.get("Optical", {})
            if isinstance(optical_obj, dict):
                interface_obj = optical_obj.get("Interface", {})
                if isinstance(interface_obj, dict):
                    for intf in interface_obj.values():
                        if isinstance(intf, dict):
                            stats = intf.get("Stats", {})
                            if isinstance(stats, dict):
                                v = _val(stats, "OpticalSignalLevel")
                                if _valid_rx(v): rx_power = v; break
                        if rx_power: break

        # Parse Temperature
        ont_temp = ""
        for vp_key in ["ONTTemperature", "Temperature", "Temp", "OpticalTemperature"]:
            v = _val(vp, vp_key)
            if v and v not in ("0", "0.0", "", "N/A"):
                ont_temp = v
                break
        if not ont_temp:
            for root in [d_igd, d_dev]:
                temp_obj = root.get("DeviceInfo", {}).get("TemperatureStatus", {}).get("TemperatureSensor", {}).get("1", {})
                if isinstance(temp_obj, dict):
                    v = _val(temp_obj, "Value")
                    if v and v not in ("0", "0.0", "", "N/A"):
                        ont_temp = v
                        break
        
        # Parse Uptime safety (Dynamic Calculation)
        base_uptime = _val(dev_info, "UpTime") or _val(dev_info, "Uptime")
        uptime = base_uptime

        if base_uptime and str(base_uptime).isdigit() and last_inform and is_online:
            try:
                dt_inform = datetime.fromisoformat(last_inform.replace("Z", "+00:00"))
                elapsed = int((datetime.now(timezone.utc) - dt_inform).total_seconds())
                if elapsed > 0:
                    uptime = str(int(base_uptime) + elapsed)
            except Exception:
                pass
        result.append({
            "id": device_id,
            "manufacturer": _val(dev_info, "Manufacturer"),
            "model": _val(dev_info, "ModelName"),
            "product_class": product_class,
            "serial": _val(dev_info, "SerialNumber"),
            "firmware": _val(dev_info, "SoftwareVersion"),
            "uptime": uptime,
            "ont_temp": ont_temp,
            "ip": pppoe_ip,
            "management_ip": management_ip,   # IP dari DHCP management/TR-069 connection
            "pppoe_username": pppoe_username,
            "pppoe_ip": pppoe_ip,
            "ssid": ssid,
            "wifi_password": wifi_password,
            "active_devices": active_devices,
            "rx_power": rx_power,   # redaman ONT
            "last_inform": last_inform,
            "online": is_online,
            "registered": d.get("_registered", ""),
        })
    return result


def _val(obj: dict, key: str) -> str:
    """
    Extract ._value from GenieACS parameter dict.
    Handles 3 cases GenieACS mengirim data:
      1. {"_value": -23.5, "_type": "xsd:int"}  → ambil _value
      2. Nilai langsung (str/int/float) tanpa wrapper dict
      3. Key tidak ada atau obj kosong → return ""
    """
    if not obj or key not in obj:
        return ""
    item = obj[key]
    if isinstance(item, dict):
        v = item.get("_value")
        if v is None:
            return ""
        return str(v).strip()
    # Nilai langsung (bukan dict)
    if isinstance(item, (int, float)):
        return str(item)
    return str(item).strip()


# ── Debug Endpoint ──────────────────────────────────────────────────────────────

@router.get("/devices/{device_id:path}/debug")
async def debug_device(device_id: str, user=Depends(require_admin)):
    """
    Return raw data struktur device untuk diagnosa path RXPower.
    Cek: VirtualParameters, WANDevice.1 (ZTE/CT-COM PON path), IGD root keys.
    """
    try:
        raw = await asyncio.to_thread(svc.get_device, device_id)
        if isinstance(raw, list):
            raw = raw[0] if raw else {}

        igd     = raw.get("InternetGatewayDevice") or raw.get("Device") or {}
        vp      = raw.get("VirtualParameters", {}) or {}
        wan1    = igd.get("WANDevice", {}).get("1", {}) if isinstance(igd.get("WANDevice"), dict) else {}

        # ── VirtualParameters lengkap ──────────────────────────────────────────
        vp_values = {}
        for k, v in vp.items():
            vp_values[k] = v.get("_value") if isinstance(v, dict) else v

        # ── WANDevice.1 top-level keys ─────────────────────────────────────────
        wan1_keys = list(wan1.keys()) if isinstance(wan1, dict) else []

        # ── Cari semua key PON yang mengandung RXPower / RxPower ──────────────
        pon_configs = {}
        pon_keywords = ["PON", "GPON", "EPON", "ONU", "OLT", "Optic", "Fiber"]
        for k in wan1_keys:
            if any(kw.upper() in k.upper() for kw in pon_keywords) or k.startswith("X_"):
                obj = wan1.get(k, {})
                if isinstance(obj, dict):
                    pon_configs[f"WANDevice.1.{k}"] = {
                        sk: sv.get("_value") if isinstance(sv, dict) else sv
                        for sk, sv in obj.items()
                    }

        # ── IGD root level vendor keys ─────────────────────────────────────────
        igd_vendor = {}
        for k in igd.keys():
            if k.startswith("X_") or any(kw.upper() in k.upper() for kw in pon_keywords):
                obj = igd.get(k, {})
                if isinstance(obj, dict):
                    igd_vendor[k] = {
                        sk: sv.get("_value") if isinstance(sv, dict) else sv
                        for sk, sv in list(obj.items())[:30]
                    }

        # ── Coba extract rx_power pakai logika normalizer ──────────────────────
        [norm] = _normalize_devices([raw])
        rx_found = norm.get("rx_power", "")

        return {
            "device_id": device_id,
            "rx_power_extracted": rx_found,   # hasil dari normalizer — apakah berhasil?
            "raw_top_keys": list(raw.keys()),
            "igd_top_keys": list(igd.keys()),
            "wan1_top_keys": wan1_keys,
            "virtual_parameters": vp_values,       # semua VP + nilainya
            "pon_configs_in_wan1": pon_configs,    # KUNCI: ZTE/CT-COM PON di WANDevice.1
            "igd_vendor_keys": igd_vendor,         # fallback: vendor key di IGD root
        }
    except Exception as e:
        _err(e, "Debug failed")


# ── Health Check ──────────────────────────────────────────────────────────────

@router.get("/health")
async def health_check(user=Depends(get_current_user)):
    """Test connectivity to GenieACS server. Returns {connected, url, latency_ms, error}."""
    try:
        result = await asyncio.to_thread(svc.check_health)
        return result
    except Exception as e:
        return {"connected": False, "url": "", "latency_ms": 0, "error": str(e)}


# ── Background Sync Loop ────────────────────────────────────────────────────────

async def genieacs_sync_loop():
    """
    Background daemon: Sinkronisasi data dari GenieACS ke mongodb (CPE Snapshot).
    Menggunakan chunk 50 devices per siklus tarikan.
    """
    import os as _os
    from pymongo import ReplaceOne
    from core.db import get_db
    db = get_db()
    logger.info("GenieACS sync loop daemon initialized.")
    await asyncio.sleep(15) # delay startup
    
    while True:
        try:
            cfg = await db.system_settings.find_one({"_id": "genieacs_config"})
            url = ""
            interval_mins = 30
            if cfg:
                url = cfg.get("url")
                interval_mins = int(cfg.get("sync_interval_mins", 30))
            else:
                url = _os.environ.get("GENIEACS_URL", "")
                try:
                    interval_mins = int(_os.environ.get("GENIEACS_SYNC_INTERVAL_MINS", 30))
                except:
                    interval_mins = 30
                    
            if not url or interval_mins <= 0:
                await asyncio.sleep(60)
                continue
                
            chunk_size = 50
            skip = 0
            has_more = True
            synced_count = 0
            
            while has_more:
                raw_devices = await asyncio.to_thread(svc.get_devices, chunk_size, skip, "", "")
                
                if not raw_devices:
                    has_more = False
                    break
                    
                # Normalize exactly like the UI, this fetches all our 8 params
                norm_devices = _normalize_devices(raw_devices)
                
                if norm_devices:
                    operations = []
                    for nd in norm_devices:
                        # Mark timestamp
                        nd["last_sync_time"] = _now()
                        operations.append(
                            ReplaceOne({"id": nd["id"]}, nd, upsert=True)
                        )
                    if operations:
                        await db.genieacs_devices.bulk_write(operations)
                        synced_count += len(operations)
                
                if len(raw_devices) < chunk_size:
                    has_more = False
                else:
                    skip += chunk_size
                    await asyncio.sleep(2) # Give GenieACS 2s breath between chunks
            
            if synced_count > 0:
                logger.info(f"GenieACS Sync Loop completed: {synced_count} devices synced. Sleeping for {interval_mins} mins.")
                
            await asyncio.sleep(interval_mins * 60)
        except Exception as e:
            logger.error(f"GenieACS Sync Loop failed: {e}")
            await asyncio.sleep(60)
