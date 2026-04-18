"""
Billing router: kelola paket berlangganan dan invoice tagihan pelanggan.
Endpoint prefix: /billing
"""
import uuid
from datetime import datetime, timezone, date
from typing import Optional
import httpx
import asyncio
import logging
import json
from fastapi import APIRouter, HTTPException, Depends, Query, BackgroundTasks
from pydantic import BaseModel
from core.db import get_db
from core.auth import (
    get_current_user, require_admin, require_write, require_enterprise,
    check_device_access, get_user_allowed_devices, build_device_filter
)

router = APIRouter(
    prefix="/billing",
    tags=["billing"],
    dependencies=[Depends(require_enterprise)],  # Semua endpoint billing → Enterprise only
)

# Webhook router: Public (no auth/session required, secured via HMAC signature)
webhook_router = APIRouter(
    prefix="/webhook",
    tags=["billing"],
)



def _now():
    return datetime.now(timezone.utc).isoformat()


def _invoice_num(seq: int) -> str:
    d = date.today()
    return f"INV-{d.year}-{d.month:02d}-{seq:04d}"


def _rupiah(amount: int) -> str:
    return f"Rp {amount:,.0f}".replace(",", ".")

def _dtfmt(dt_str: str) -> str:
    if not dt_str: return ""
    p = dt_str[:10].split("-")
    return f"{p[2]}/{p[1]}/{p[0]}" if len(p) == 3 else dt_str


logger = logging.getLogger(__name__)

# ── Helper: Kode Unik Anti-Collision ─────────────────────────────────────────

async def _generate_unique_code(db, customer_id: str, amount: int, month_prefix: str) -> int:
    """
    Generate kode unik 100-999 yang DIJAMIN tidak bentrok dengan invoice
    unpaid pelanggan lain di bulan yang sama (max 50 percobaan).
    """
    import random
    for _ in range(50):
        code = random.randint(100, 999)
        total_candidate = amount + code
        conflict = await db.invoices.find_one({
            "total": total_candidate,
            "status": {"$in": ["unpaid", "overdue"]},
            "period_start": {"$regex": f"^{month_prefix}"},
            "customer_id": {"$ne": customer_id},
        })
        if not conflict:
            return code
    return random.randint(100, 999)  # fallback darurat


# ── Helper: Aksi Terpusat Setelah Invoice Lunas ───────────────────────────────

async def _after_paid_actions(invoice_id: str, db) -> str:
    """
    Aksi terpusat setelah invoice ditandai LUNAS:
      1. Cek tunggakan lain — jika masih ada, user tetap diisolir
      2. Enable user di MikroTik (PPPoE / Hotspot)
      3. Reset flag mt_disabled di DB
      4. Restore nama WiFi (SSID) via GenieACS jika sebelumnya diubah saat isolir

    Dipanggil dari: mark_paid(), moota_webhook() — satu titik kontrol.
    Return: pesan status string.
    """
    try:
        from mikrotik_api import get_api_client
        inv = await db.invoices.find_one({"id": invoice_id})
        if not inv:
            return ""
        customer = await db.customers.find_one({"id": inv.get("customer_id", "")})
        if not customer:
            return ""

        # Cek tunggakan overdue lain milik pelanggan yang sama
        other_overdue = await db.invoices.find_one({
            "customer_id": customer["id"],
            "status": "overdue",
            "id": {"$ne": invoice_id},
        })
        if other_overdue:
            logger.info(
                f"[AfterPaid] Invoice {invoice_id}: user '{customer.get('username')}' "
                f"tetap diisolir — masih ada tagihan overdue lain."
            )
            return " | User tetap diisolir karena masih memiliki tagihan tunggakan lain"

        mt_msg = ""

        # 1. Enable user di MikroTik
        device = await db.devices.find_one({"id": customer.get("device_id", "")})
        if device:
            try:
                mt = get_api_client(device)
                username = customer.get("username", "")
                svc = customer.get("service_type", "pppoe")
                auth_method = customer.get("auth_method", "local")
                if auth_method == "radius" and svc == "pppoe":
                    mt_msg = f" | User '{username}' (RADIUS) otomatis aktif setelah lunas"
                    logger.info(f"[AfterPaid] User '{username}' menggunakan RADIUS, skip enable di MikroTik.")
                else:
                    if svc == "pppoe":
                        await mt.enable_pppoe_user(username)
                    else:
                        await mt.enable_hotspot_user(username)
                    mt_msg = f" | User '{username}' di-enable di MikroTik"
                    logger.info(f"[AfterPaid] User '{username}' berhasil di-enable.")
            except Exception as e:
                mt_msg = f" | Gagal enable MikroTik: {e}"
                logger.error(f"[AfterPaid] Gagal enable user '{customer.get('username')}': {e}")

        # 2. Reset flag mt_disabled
        await db.invoices.update_one(
            {"id": invoice_id},
            {"$set": {"mt_disabled": False}}
        )

        # 3. Restore SSID via GenieACS jika sebelumnya diubah saat isolir
        if inv.get("original_ssid") and inv.get("genieacs_device_id"):
            try:
                from services import genieacs_service as genie_svc
                await asyncio.to_thread(
                    genie_svc.set_parameter,
                    inv["genieacs_device_id"],
                    "InternetGatewayDevice.LANDevice.1.WLANConfiguration.1.SSID",
                    inv["original_ssid"],
                )
                # Hapus snapshot SSID setelah berhasil dikembalikan
                await db.invoices.update_one(
                    {"id": invoice_id},
                    {"$unset": {"original_ssid": "", "genieacs_device_id": ""}}
                )
                mt_msg += " | Nama WiFi (SSID) dikembalikan"
                logger.info(f"[AfterPaid] SSID '{inv['original_ssid']}' berhasil dikembalikan via GenieACS.")
            except Exception as ge:
                logger.error(f"[AfterPaid] Gagal restore SSID ({inv.get('genieacs_device_id')}): {ge}")
                mt_msg += " | Gagal mengembalikan nama WiFi"

        return mt_msg

    except Exception as e:
        logger.error(f"[AfterPaid] Error pada _after_paid_actions({invoice_id}): {e}")
        return f" | Error pasca bayar: {e}"


# ══════════════════════════════════════════════════════════════════════════════
# SETTINGS
# ══════════════════════════════════════════════════════════════════════════════

class BillingSettingsUpdate(BaseModel):
    device_id: Optional[str] = "GLOBAL"
    wa_gateway_type: Optional[str] = None
    wa_api_url: Optional[str] = None
    wa_token: Optional[str] = None
    wa_delay_ms: Optional[int] = None
    wa_template_unpaid: Optional[str] = None
    wa_template_h1: Optional[str] = None
    wa_template_isolir: Optional[str] = None
    wa_template_paid: Optional[str] = None
    fcm_template_h3: Optional[str] = None
    fcm_template_h2: Optional[str] = None
    fcm_template_h1: Optional[str] = None
    fcm_template_due: Optional[str] = None
    fcm_template_overdue: Optional[str] = None
    fcm_template_paid: Optional[str] = None
    fcm_template_network_error: Optional[str] = None
    auto_isolir_enabled: Optional[bool] = None
    auto_isolir_method: Optional[str] = None
    auto_isolir_time: Optional[str] = None
    auto_isolir_grace_days: Optional[int] = None
    moota_webhook_secret: Optional[str] = None
    # ── Payment Gateway Settings ──────────────────────────────────────
    payment_gateway_enabled: Optional[bool] = None
    default_payment_provider: Optional[str] = None  # xendit | bca | bri
    # Xendit
    xendit_secret_key: Optional[str] = None
    xendit_webhook_token: Optional[str] = None
    xendit_va_bank: Optional[str] = None              # BNI | BCA | BRI | MANDIRI | PERMATA
    xendit_enabled: Optional[bool] = None
    # BCA SNAP
    bca_client_id: Optional[str] = None
    bca_client_secret: Optional[str] = None
    bca_company_code: Optional[str] = None
    bca_api_key: Optional[str] = None
    bca_api_secret: Optional[str] = None
    bca_enabled: Optional[bool] = None
    # BRI BRIVA
    bri_client_id: Optional[str] = None
    bri_client_secret: Optional[str] = None
    bri_institution_code: Optional[str] = None
    bri_enabled: Optional[bool] = None

async def fetch_billing_settings(db, device_id: Optional[str] = None) -> dict:
    if device_id and device_id != "GLOBAL":
        s = await db.billing_settings.find_one({"device_id": device_id}, {"_id": 0})
        if s: return s
    s_global = await db.billing_settings.find_one({"$or": [{"device_id": "GLOBAL"}, {"device_id": {"$exists": False}}]}, {"_id": 0})
    return s_global or {}

@router.get("/settings")
async def get_billing_settings(device_id: Optional[str] = "GLOBAL", user=Depends(get_current_user)):
    db = get_db()
    
    if device_id and device_id != "GLOBAL":
        s = await db.billing_settings.find_one({"device_id": device_id}, {"_id": 0})
        if s: return s

    s_global = await db.billing_settings.find_one({"$or": [{"device_id": "GLOBAL"}, {"device_id": {"$exists": False}}]}, {"_id": 0})
    if not s_global:
        s_global = {
            "device_id": "GLOBAL",
            "wa_gateway_type": "fonnte",
            "wa_api_url": "https://api.fonnte.com/send",
            "wa_token": "",
            "wa_delay_ms": 10000,
            "wa_template_unpaid": "Yth. *{customer_name}*,\n\nTagihan internet Anda sebesar *{total}* untuk paket {package_name} periode {period} telah terbit. Nomor invoice: {invoice_number}.\nJatuh tempo pada: *{due_date}*.\n\nMohon segera melakukan pembayaran. Abaikan pesan ini jika sudah mengkonfirmasi pembayaran.",
            "wa_template_h1": "Yth. *{customer_name}*,\n\n⚠️ Pengingat: Tagihan internet Anda sebesar *{total}* (Invoice: {invoice_number}, Paket: {package_name}) jatuh tempo *BESOK* pada {due_date}.\n\nSegera lakukan pembayaran untuk menghindari pemutusan layanan. Terima kasih.",
            "wa_template_isolir": "Yth. *{customer_name}*,\n\nMohon maaf, layanan internet Anda untuk paket {package_name} (Invoice: {invoice_number}) telah kami *ISOLIR* (putus sementara) karena melewati batas waktu pembayaran.\nTotal tagihan: *{total}* (Jatuh tempo: {due_date}).\n\nSilakan lakukan pembayaran agar layanan dapat segera aktif kembali. Terima kasih.",
            "wa_template_paid": "Yth. *{customer_name}*,\n\nPembayaran tagihan internet Anda sebesar *{total}* (Invoice: {invoice_number}) telah kami terima via {payment_method}.\n\nTerima kasih dan selamat menikmati layanan kami.",
            "fcm_template_h3": "Tagihan internet Anda {total} jatuh tempo dalam 3 hari pada {due_date}.",
            "fcm_template_h2": "Tagihan internet Anda {total} jatuh tempo dalam 2 hari pada {due_date}.",
            "fcm_template_h1": "Besok adalah batas akhir pembayaran tagihan internet Anda sebesar {total}.",
            "fcm_template_due": "HARI INI jatuh tempo pembayaran internet {total}. Mohon segera dilunasi.",
            "fcm_template_overdue": "Layanan Anda telah TERISOLIR karena melewati batas waktu pembayaran. Segera lunasi {total}.",
            "fcm_template_paid": "Terima kasih {customer_name}! Pembayaran tagihan #{invoice_number} berhasil.",
            "fcm_template_network_error": "Yth {customer_name}, terdapat gangguan jaringan pada sistem kami. Mohon maaf atas ketidaknyamanan ini.",
            "auto_isolir_enabled": False,
            "auto_isolir_method": "whatsapp",
            "auto_isolir_time": "00:05",
            "auto_isolir_grace_days": 1,
            "moota_webhook_secret": "",
        }
        await db.billing_settings.insert_one(s_global)
        s_global.pop("_id", None)
    return s_global

@router.put("/settings")
async def update_billing_settings(data: BillingSettingsUpdate, user=Depends(require_admin)):
    db = get_db()
    update_data = {k: v for k, v in data.dict().items() if v is not None}
    if not update_data:
        raise HTTPException(400, "Tidak ada data yang dikirim")
    
    dev_id = update_data.get("device_id", "GLOBAL")
    
    # 1. Search existing
    query = {"device_id": dev_id}
    if dev_id == "GLOBAL":
        query = {"$or": [{"device_id": "GLOBAL"}, {"device_id": {"$exists": False}}]}
        
    doc = await db.billing_settings.find_one(query)
    
    if doc:
        filter_query = {"_id": doc["_id"]}
        await db.billing_settings.update_one(filter_query, {"$set": update_data})
    else:
        update_data["device_id"] = dev_id
        await db.billing_settings.insert_one(update_data)
        
    res = await db.billing_settings.find_one({"device_id": dev_id}, {"_id": 0})
    if not res and dev_id == "GLOBAL":
        res = await db.billing_settings.find_one({"device_id": {"$exists": False}}, {"_id": 0})
    return res or {}

# ══════════════════════════════════════════════════════════════════════════════
# PACKAGES
# ══════════════════════════════════════════════════════════════════════════════

class PackageCreate(BaseModel):
    name: str
    price: int                       # harga dalam rupiah
    speed_up: str = ""               # misal "20M"
    speed_down: str = ""
    service_type: str = "pppoe"      # "pppoe" | "hotspot" | "both"
    uptime_limit: Optional[str] = None # Hotspot: e.g. "1h", "2h", "1d"
    validity: str = ""               # masa aktif (khusus hotspot)
    billing_cycle: int = 30          # hari
    active: bool = True
    device_id: Optional[str] = None  # Jika diisi → buat profile di MikroTik secara otomatis
    
    # ── Dynamic Bandwidth (Day/Night) ──
    day_night_enabled: bool = False
    night_rate_limit: Optional[str] = None
    night_start: str = "22:00"
    night_end: str = "06:00"
    
    # ── FUP ──
    fup_enabled: bool = False
    fup_limit_gb: int = 0
    fup_rate_limit: Optional[str] = None
    
    # ── Speed Booster ──
    boost_rate_limit: Optional[str] = None
    boost_duration_hours: int = 24
    
    # ── Early Bird Promo ──
    enable_early_promo: bool = False
    promo_amount: int = 0


class PackageUpdate(BaseModel):
    name: Optional[str] = None
    price: Optional[int] = None
    speed_up: Optional[str] = None
    speed_down: Optional[str] = None
    service_type: Optional[str] = None
    uptime_limit: Optional[str] = None
    validity: Optional[str] = None
    billing_cycle: Optional[int] = None
    active: Optional[bool] = None
    
    # ── Dynamic Bandwidth (Day/Night) ──
    day_night_enabled: Optional[bool] = None
    night_rate_limit: Optional[str] = None
    night_start: Optional[str] = None
    night_end: Optional[str] = None
    
    # ── FUP ──
    fup_enabled: Optional[bool] = None
    fup_limit_gb: Optional[int] = None
    fup_rate_limit: Optional[str] = None
    
    # ── Speed Booster ──
    boost_rate_limit: Optional[str] = None
    boost_duration_hours: Optional[int] = None
    
    # ── Early Bird Promo ──
    enable_early_promo: Optional[bool] = None
    promo_amount: Optional[int] = None


@router.get("/packages")
async def list_packages(
    service_type: str = Query(""),
    device_id: str = Query(""),       # opsional filter per-router
    user=Depends(get_current_user)
):
    db = get_db()
    q = {}
    if service_type:
        q["service_type"] = service_type

    # ── RBAC: filter berdasarkan allowed_devices user ──────────────────────
    scope = get_user_allowed_devices(user)  # None = admin (semua), [] = kosong
    if scope is None:
        # Admin → pakai filter device_id dari query param jika ada
        if device_id:
            q["$or"] = [
                {"device_id": device_id},
                {"source_device_id": device_id},
            ]
    else:
        # Non-admin: batasi hanya device yang diizinkan,
        # lalu intersect dengan device_id param jika ada
        allowed = scope
        if device_id:
            allowed = [d for d in scope if d == device_id]
        if not allowed:
            return []   # tidak ada device yang diizinkan
        q["$or"] = [
            {"device_id": {"$in": allowed}},
            {"source_device_id": {"$in": allowed}},
        ]

    pkgs = await db.billing_packages.find(q, {"_id": 0}).to_list(1000)
    return pkgs


async def _push_profile_to_mikrotik(device: dict, profile_name: str, speed_up: str, speed_down: str):
    """Background task: push PPP profile ke MikroTik secara diam-diam setelah paket manual dibuat."""
    from mikrotik_api import get_api_client
    try:
        mt = get_api_client(device)

        # Susun rate-limit: format MikroTik = "download/upload" (mis: "20M/20M")
        rate_limit = ""
        sd = (speed_down or "").strip()
        su = (speed_up or "").strip()
        if sd and su:
            rate_limit = f"{sd}/{su}"
        elif sd:
            rate_limit = sd
        elif su:
            rate_limit = su

        # Cek apakah profile sudah ada agar tidak duplikat
        try:
            existing = await mt.list_pppoe_profiles()
            if any(p.get("name") == profile_name for p in existing):
                logger.info(f"[auto-profile] Profile '{profile_name}' sudah ada di {device.get('name', '')}, skip.")
                return
        except Exception:
            pass  # Jika gagal cek, tetap lanjut coba buat

        api_mode = device.get("api_mode", "api")
        if api_mode == "rest":
            # RouterOS 7+ REST API: PUT /rest/ppp/profile
            payload = {"name": profile_name}
            if rate_limit:
                payload["rate-limit"] = rate_limit
            await mt._async_req("PUT", "ppp/profile", payload)
        else:
            # RouterOS 6 Legacy API: gunakan _add_resource
            data = {"name": profile_name}
            if rate_limit:
                data["rate-limit"] = rate_limit
            await asyncio.to_thread(mt._add_resource, "/ppp/profile", data)

        logger.info(f"[auto-profile] ✅ PPP profile '{profile_name}' berhasil dibuat di {device.get('name', device.get('host', ''))}")
    except Exception as e:
        logger.warning(f"[auto-profile] ⚠️ Gagal push profile '{profile_name}' ke MikroTik {device.get('name','')}: {e}")



@router.post("/packages", status_code=201)
async def create_package(data: PackageCreate, background_tasks: BackgroundTasks, user=Depends(require_write)):
    db = get_db()

    # ── RBAC: pastikan user boleh membuat paket untuk device ini ────────────
    if data.device_id and not check_device_access(user, data.device_id):
        raise HTTPException(403, "Anda tidak memiliki hak akses untuk membuat paket pada router ini")

    device = None
    device_name = ""
    if data.device_id:
        device = await db.devices.find_one({"id": data.device_id})
        if not device:
            raise HTTPException(404, f"Device dengan id '{data.device_id}' tidak ditemukan")
        device_name = device.get("name", device.get("host", data.device_id))

    doc = {
        "id": str(uuid.uuid4()),
        **data.dict(),
        # Simpan device_id sebagai tenant key utama dan juga di source_device_id untuk backward compat
        "device_id": data.device_id or "",
        "source_device_id": data.device_id or "",
        "source_device_name": device_name,
        "profile_name": data.name,
        "created_at": _now(),
    }
    # Backward compatibility: pastikan 'type' juga ada
    if "service_type" in doc and "type" not in doc:
        doc["type"] = doc["service_type"]

    await db.billing_packages.insert_one(doc)
    doc.pop("_id", None)

    # Silently push profile to MikroTik in background (fire-and-forget)
    if device and data.service_type in ("pppoe", "both"):
        background_tasks.add_task(
            _push_profile_to_mikrotik,
            device, data.name, data.speed_up, data.speed_down
        )

    return doc


@router.put("/packages/{pkg_id}")
async def update_package(pkg_id: str, data: PackageUpdate, background_tasks: BackgroundTasks, user=Depends(require_write)):
    db = get_db()

    # ── RBAC: cek kepemilikan device dari paket ini ──────────────────────────
    existing_pkg = await db.billing_packages.find_one({"id": pkg_id}, {"_id": 0})
    if not existing_pkg:
        raise HTTPException(404, "Paket tidak ditemukan")
    pkg_device_id = existing_pkg.get("device_id") or existing_pkg.get("source_device_id", "")
    if pkg_device_id and not check_device_access(user, pkg_device_id):
        raise HTTPException(403, "Anda tidak memiliki hak akses untuk mengubah paket pada router ini")

    update = {k: v for k, v in data.dict().items() if v is not None}
    if "service_type" in update:
        update["type"] = update["service_type"]

    if not update:
        raise HTTPException(400, "Tidak ada perubahan")
    result = await db.billing_packages.update_one({"id": pkg_id}, {"$set": update})
    if result.matched_count == 0:
        raise HTTPException(404, "Paket tidak ditemukan")

    # ── Segera reset current_rate_limit & sync BW ke semua pelanggan AKTIF paket ini ──
    # Ini memastikan jika Night Mode / Booster / FUP dinonaktifkan atau speed diubah,
    # limit langsung kembali ke benar tanpa menunggu 5 menit scheduler.
    # PENTING: Tidak ada kick — perubahan dikirim via CoA (tanpa putus koneksi) atau
    # tersimpan di DB untuk berlaku saat reconnect berikutnya.
    async def _trigger_bw_sync_for_package(p_id: str):
        try:
            # Reset current_rate_limit HANYA untuk user aktif agar scheduler re-evaluasi
            res = await db.customers.update_many(
                {"package_id": p_id, "active": True},
                {"$set": {"current_rate_limit": None}}
            )
            logger.info(f"[PkgUpdate] Reset current_rate_limit untuk {res.modified_count} pelanggan aktif paket {p_id}")
            # Jalankan sync sekarang (global untuk paket ini, no kick)
            from services.bandwidth_scheduler import run_day_night_and_booster_sync
            await run_day_night_and_booster_sync()
            logger.info(f"[PkgUpdate] BW sync selesai untuk paket {p_id} (tanpa putus koneksi)")
        except Exception as e:
            logger.error(f"[PkgUpdate] Gagal trigger BW sync paket {p_id}: {e}")

    background_tasks.add_task(_trigger_bw_sync_for_package, pkg_id)

    return {"message": "Paket diupdate"}


@router.delete("/packages/{pkg_id}")
async def delete_package(pkg_id: str, user=Depends(require_admin)):
    db = get_db()

    # ── RBAC: admin non-super hanya bisa hapus paket dari routernya sendiri ─
    existing_pkg = await db.billing_packages.find_one({"id": pkg_id}, {"_id": 0})
    if not existing_pkg:
        raise HTTPException(404, "Paket tidak ditemukan")
    pkg_device_id = existing_pkg.get("device_id") or existing_pkg.get("source_device_id", "")
    if pkg_device_id and not check_device_access(user, pkg_device_id):
        raise HTTPException(403, "Anda tidak memiliki hak akses untuk menghapus paket pada router ini")

    result = await db.billing_packages.delete_one({"id": pkg_id})
    if result.deleted_count == 0:
        raise HTTPException(404, "Paket tidak ditemukan")
    return {"message": "Paket dihapus"}


@router.post("/packages/sync-from-mikrotik")
async def sync_packages_from_mikrotik(
    device_id: str = Query(..., description="ID device MikroTik"),
    user=Depends(require_admin),
):
    """
    Ambil semua profile PPPoE + Hotspot dari device MikroTik.
    Jika profile belum ada di billing_packages → buat baru dengan price=0.
    Jika sudah ada → biarkan (harga tidak diubah).
    Return: daftar paket yang baru ditambahkan dan yang sudah ada.
    """
    db = get_db()
    device = await db.devices.find_one({"id": device_id})
    if not device:
        raise HTTPException(404, "Device tidak ditemukan")

    from mikrotik_api import get_api_client
    try:
        mt = get_api_client(device)
    except Exception as e:
        raise HTTPException(503, f"Gagal inisialisasi MikroTik client: {e}")

    # Ambil profile dari MikroTik
    pppoe_profiles, hotspot_profiles = [], []
    try:
        pppoe_profiles = await mt.list_pppoe_profiles() or []
    except Exception as e:
        pppoe_profiles = []

    try:
        hotspot_profiles = await mt.list_hotspot_profiles() or []
    except Exception as e:
        hotspot_profiles = []

    added, existing = [], []
    device_name = device.get("name", device.get("host", device_id))

    # Proses PPPoE profiles
    for p in pppoe_profiles:
        pname = p.get("name", "")
        if not pname or pname == "default":
            continue
        existing_pkg = await db.billing_packages.find_one({
            "profile_name": pname,
            "service_type": "pppoe",
            "source_device_id": device_id,
        })
        if existing_pkg:
            existing.append(pname)
            continue
        doc = {
            "id": str(uuid.uuid4()),
            "name": pname,
            "profile_name": pname,
            "source_device_id": device_id,
            "source_device_name": device_name,
            "service_type": "pppoe",
            "type": "pppoe", # Backward compatibility for TR-069 search
            "price": 0,
            "speed_up": p.get("rate-limit", "").split("/")[1] if "/" in p.get("rate-limit", "") else "",
            "speed_down": p.get("rate-limit", "").split("/")[0] if "/" in p.get("rate-limit", "") else "",
            "billing_cycle": 30,
            "active": True,
            "synced_at": _now(),
            "created_at": _now(),
        }
        await db.billing_packages.insert_one(doc)
        doc.pop("_id", None)
        added.append(pname)

    # Proses Hotspot profiles
    for p in hotspot_profiles:
        pname = p.get("name", "")
        if not pname or pname == "default":
            continue
        existing_pkg = await db.billing_packages.find_one({
            "profile_name": pname,
            "service_type": "hotspot",
            "source_device_id": device_id,
        })
        if existing_pkg:
            existing.append(f"{pname} (hs)")
            continue
        doc = {
            "id": str(uuid.uuid4()),
            "name": f"{pname} (Hotspot)",
            "profile_name": pname,
            "source_device_id": device_id,
            "source_device_name": device_name,
            "service_type": "hotspot",
            "type": "hotspot", # Backward compatibility
            "price": 0,
            "speed_up": p.get("rate-limit", "").split("/")[1] if "/" in p.get("rate-limit", "") else "",
            "speed_down": p.get("rate-limit", "").split("/")[0] if "/" in p.get("rate-limit", "") else "",
            "billing_cycle": 30,
            "active": True,
            "synced_at": _now(),
            "created_at": _now(),
        }
        await db.billing_packages.insert_one(doc)
        doc.pop("_id", None)
        added.append(f"{pname} (Hotspot)")

    return {
        "message": f"Sync selesai: {len(added)} paket baru, {len(existing)} sudah ada",
        "added": added,
        "existing": existing,
        "total_pppoe": len(pppoe_profiles),
        "total_hotspot": len(hotspot_profiles),
    }


@router.patch("/packages/{pkg_id}/price")
async def update_package_price(pkg_id: str, data: dict, user=Depends(require_write)):
    """Update harga paket (dipakai admin untuk set harga setelah sync dari MikroTik)."""
    db = get_db()
    price = data.get("price")
    active = data.get("active")
    update_set = {}
    if price is not None:
        try:
            update_set["price"] = int(price)
        except (ValueError, TypeError):
            raise HTTPException(400, "Harga tidak valid")
    if active is not None:
        update_set["active"] = bool(active)
    if not update_set:
        raise HTTPException(400, "Tidak ada perubahan")
    result = await db.billing_packages.update_one({"id": pkg_id}, {"$set": update_set})
    if result.matched_count == 0:
        raise HTTPException(404, "Paket tidak ditemukan")
    return {"message": "Harga paket diupdate"}


# ══════════════════════════════════════════════════════════════════════════════
# INVOICES

# ══════════════════════════════════════════════════════════════════════════════

class InvoiceCreate(BaseModel):
    customer_id: str
    package_id: str
    amount: int
    discount: int = 0
    period_start: str          # "2026-03-01"
    period_end: str            # "2026-03-31"
    due_date: str              # "2026-03-10"
    notes: str = ""


class PaymentUpdate(BaseModel):
    payment_method: str = "cash"   # "cash" | "transfer" | "qris"
    paid_notes: str = ""


@router.get("/stats")
async def billing_stats(
    month: int = Query(0),    # 0 = bulan ini
    year: int = Query(0),
    device_id: str = Query(""),
    user=Depends(get_current_user),
):
    """Dashboard stats: total tagihan, lunas, belum bayar, jatuh tempo."""
    db = get_db()
    today = date.today()
    m = month or today.month
    y = year or today.year

    # Filter periode bulan
    period_prefix = f"{y}-{m:02d}"
    q = {"period_start": {"$regex": f"^{period_prefix}"}}

    # ── RBAC: bangun cust_q berdasarkan allowed_devices ───────────────────
    scope = get_user_allowed_devices(user)  # None = admin (semua)
    cust_q = {"service_type": "pppoe"}
    if scope is None:
        # Admin: gunakan device_id dari param jika ada
        if device_id:
            cust_q["device_id"] = device_id
    else:
        # Non-admin: batasi ke allowed devices
        allowed = scope
        if device_id:
            allowed = [d for d in scope if d == device_id]
        if not allowed:
            return {
                "month": m, "year": y, "total_invoices": 0,
                "total_amount": 0, "paid_count": 0, "paid_amount": 0,
                "unpaid_count": 0, "unpaid_amount": 0, "overdue_count": 0,
            }
        cust_q["device_id"] = {"$in": allowed}

    customers = await db.customers.find(cust_q, {"id": 1}).to_list(None)
    q["customer_id"] = {"$in": [c["id"] for c in customers]}

    all_inv = await db.invoices.find(q, {"_id": 0}).to_list(5000)

    total_amount = sum(i.get("total", 0) for i in all_inv)
    paid = [i for i in all_inv if i.get("status") == "paid"]
    unpaid = [i for i in all_inv if i.get("status") in ("unpaid", "overdue")]
    overdue = [i for i in all_inv if i.get("status") == "overdue" or (
        i.get("status") == "unpaid" and i.get("due_date", "") < today.isoformat()
    )]

    paid_amount = sum(i.get("total", 0) for i in paid)
    unpaid_amount = sum(i.get("total", 0) for i in unpaid)

    # Update overdue status
    overdue_ids = [i["id"] for i in overdue if i.get("status") == "unpaid"]
    if overdue_ids:
        await db.invoices.update_many(
            {"id": {"$in": overdue_ids}},
            {"$set": {"status": "overdue"}}
        )

    return {
        "month": m,
        "year": y,
        "total_invoices": len(all_inv),
        "total_amount": total_amount,
        "paid_count": len(paid),
        "paid_amount": paid_amount,
        "unpaid_count": len(unpaid),
        "unpaid_amount": unpaid_amount,
        "overdue_count": len(overdue),
    }


@router.get("/invoices")
async def list_invoices(
    month: int = Query(0),
    year: int = Query(0),
    status: str = Query(""),           # "" | "paid" | "unpaid" | "overdue"
    search: str = Query(""),
    customer_id: str = Query(""),
    device_id: str = Query(""),
    service_type: str = Query("pppoe"), # Default ke pppoe untuk billing utama
    page: int = Query(1),
    limit: int = Query(0),
    user=Depends(get_current_user),
):
    db = get_db()
    today = date.today()
    m = month or today.month
    y = year or today.year
    period_prefix = f"{y}-{m:02d}"

    q = {"period_start": {"$regex": f"^{period_prefix}"}}
    if status:
        if "," in status:
            q["status"] = {"$in": status.split(",")}
        else:
            q["status"] = status
    if customer_id:
        q["customer_id"] = customer_id

    # ── RBAC: bangun filter customer berdasarkan allowed_devices ─────────────
    scope = get_user_allowed_devices(user)  # None = admin, [] = kosong
    cust_q = {}
    if scope is None:
        # Admin: gunakan device_id param jika ada
        if device_id:
            cust_q["device_id"] = device_id
    else:
        allowed = scope
        if device_id:
            allowed = [d for d in scope if d == device_id]
        if not allowed:
            return {"data": [], "total": 0, "page": page, "limit": limit, "pages": 1}
        cust_q["device_id"] = {"$in": allowed}

    if service_type:
        cust_q["$or"] = [
            {"service_type": service_type},
            {"type": service_type}
        ]

    if cust_q and not customer_id:
        cust_ids = await db.customers.find(cust_q, {"id": 1}).to_list(None)
        q["customer_id"] = {"$in": [c["id"] for c in cust_ids]}
    elif cust_q and customer_id:
        # Masih perlu filter service_type jika ada
        if service_type:
            q["$and"] = [{"$or": cust_q.get("$or", [])}]

    invoices = await db.invoices.find(q, {"_id": 0}).sort("due_date", 1).to_list(5000)

    # Enrich dengan data customer dan package
    customer_ids = list({i["customer_id"] for i in invoices})
    pkg_ids = list({i["package_id"] for i in invoices})

    customers = {c["id"]: c for c in await db.customers.find(
        {"id": {"$in": customer_ids}}, {"_id": 0}
    ).to_list(1000)}

    packages = {p["id"]: p for p in await db.billing_packages.find(
        {"id": {"$in": pkg_ids}}, {"_id": 0}
    ).to_list(200)}

    result_filtered = []
    for inv in invoices:
        customer = customers.get(inv["customer_id"], {})
        pkg = packages.get(inv["package_id"], {})
        inv["customer_name"] = customer.get("name", "—")
        inv["customer_username"] = customer.get("username", "—")
        inv["customer_phone"] = customer.get("phone", "")
        inv["customer_address"] = customer.get("address", "")
        inv["package_name"] = pkg.get("name", "—")
        # Tambahkan info service_type agar UI bisa labeli Voucher vs PPPoE
        inv["customer_service_type"] = customer.get("service_type") or customer.get("type") or "pppoe"
        inv["invoice_source"] = inv.get("source", "")

        # Auto-update overdue
        if inv["status"] == "unpaid" and inv.get("due_date", "") < today.isoformat():
            inv["status"] = "overdue"
            await db.invoices.update_one({"id": inv["id"]}, {"$set": {"status": "overdue"}})

        if search:
            s = search.lower()
            if not (s in inv.get("customer_name", "").lower()
                    or s in inv.get("customer_username", "").lower()
                    or s in inv.get("invoice_number", "").lower()):
                continue
        result_filtered.append(inv)

    total_count = len(result_filtered)
    # Apply pagination if limit is set
    if limit and limit > 0:
        skip_n = (page - 1) * limit
        paginated = result_filtered[skip_n: skip_n + limit]
    else:
        paginated = result_filtered

    return {
        "data": paginated,
        "total": total_count,
        "page": page,
        "limit": limit,
        "pages": max(1, (total_count + limit - 1) // limit) if limit else 1,
    }


# ── CSV Export ────────────────────────────────────────────────────────────────

import csv
import io
from fastapi.responses import StreamingResponse

@router.get("/invoices/export-csv")
async def export_invoices_csv(
    month: int = Query(0),
    year: int = Query(0),
    status: str = Query(""),
    device_id: str = Query(""),
    user=Depends(get_current_user),
):
    """Export daftar invoice bulan tertentu ke file CSV."""
    db = get_db()
    today = date.today()
    m = month or today.month
    y = year or today.year
    period_prefix = f"{y}-{m:02d}"

    q = {"period_start": {"$regex": f"^{period_prefix}"}}
    if status:
        q["status"] = status
    if device_id:
        custs = await db.customers.find({"device_id": device_id}, {"id": 1}).to_list(None)
        q["customer_id"] = {"$in": [c["id"] for c in custs]}

    invoices = await db.invoices.find(q, {"_id": 0}).sort("due_date", 1).to_list(10000)

    customer_ids = list({i["customer_id"] for i in invoices})
    pkg_ids = list({i["package_id"] for i in invoices})
    customers_map = {c["id"]: c for c in await db.customers.find(
        {"id": {"$in": customer_ids}}, {"_id": 0}).to_list(2000)}
    packages_map = {p["id"]: p for p in await db.billing_packages.find(
        {"id": {"$in": pkg_ids}}, {"_id": 0}).to_list(200)}

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["No. Invoice", "Nama Pelanggan", "Username", "Telepon",
                     "Paket", "Periode", "Jatuh Tempo", "Tagihan", "Diskon",
                     "Kode Unik", "Total", "Status", "Metode Bayar", "Tgl Bayar"])

    for inv in invoices:
        c = customers_map.get(inv["customer_id"], {})
        p = packages_map.get(inv["package_id"], {})
        writer.writerow([
            inv.get("invoice_number", ""),
            c.get("name", "—"),
            c.get("username", "—"),
            c.get("phone", ""),
            p.get("name", "—"),
            f"{inv.get('period_start', '')} s/d {inv.get('period_end', '')}",
            inv.get("due_date", ""),
            inv.get("amount", 0),
            inv.get("discount", 0),
            inv.get("unique_code", 0),
            inv.get("total", 0),
            inv.get("status", ""),
            inv.get("payment_method") or "",
            (inv.get("paid_at") or "")[:10],
        ])

    output.seek(0)
    filename = f"invoice_{y}-{m:02d}.csv"
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )


# ── Customer Payment History ──────────────────────────────────────────────────

@router.get("/customers/{customer_id}/history")
async def customer_invoice_history(
    customer_id: str,
    limit: int = Query(24),
    user=Depends(get_current_user),
):
    """Semua riwayat tagihan seorang pelanggan, diurutkan terbaru dulu."""
    db = get_db()
    customer = await db.customers.find_one({"id": customer_id}, {"_id": 0})
    if not customer:
        raise HTTPException(404, "Customer tidak ditemukan")

    invoices = await db.invoices.find(
        {"customer_id": customer_id}, {"_id": 0}
    ).sort("period_start", -1).to_list(limit)

    pkg_ids = list({i["package_id"] for i in invoices})
    packages_map = {p["id"]: p for p in await db.billing_packages.find(
        {"id": {"$in": pkg_ids}}, {"_id": 0}).to_list(50)}

    for inv in invoices:
        p = packages_map.get(inv["package_id"], {})
        inv["package_name"] = p.get("name", "—")

    total_paid = sum(i["total"] for i in invoices if i.get("status") == "paid")
    total_outstanding = sum(i["total"] for i in invoices if i.get("status") in ("unpaid", "overdue"))

    return {
        "customer": customer,
        "invoices": invoices,
        "summary": {
            "total_invoices": len(invoices),
            "total_paid": total_paid,
            "total_outstanding": total_outstanding,
            "paid_count": sum(1 for i in invoices if i.get("status") == "paid"),
            "overdue_count": sum(1 for i in invoices if i.get("status") == "overdue"),
        }
    }


# ── Financial Report ──────────────────────────────────────────────────────────

@router.get("/financial-report")
async def financial_report(
    month: int = Query(0),
    year: int = Query(0),
    device_id: str = Query(""),
    service_type: str = Query("pppoe"), # Kunci pppoe untuk laporan billing utama
    user=Depends(get_current_user),
):
    """Laporan keuangan bulanan lengkap: pendapatan, outstanding, daftar nunggak, top paket."""
    db = get_db()
    today = date.today()
    m = month or today.month
    y = year or today.year
    period_prefix = f"{y}-{m:02d}"

    q = {"period_start": {"$regex": f"^{period_prefix}"}}

    # ── RBAC: bangun filter berdasarkan allowed_devices ──────────────────
    scope = get_user_allowed_devices(user)
    custs_q_for_inv = {}
    if scope is None:
        if device_id:
            custs_q_for_inv["device_id"] = device_id
    else:
        allowed = scope
        if device_id:
            allowed = [d for d in scope if d == device_id]
        if not allowed:
            # Kembalikan laporan kosong jika tidak ada akses
            import calendar as cal_mod
            _, last_day = cal_mod.monthrange(y, m)
            return {
                "period": {"month": m, "year": y, "label": f"{cal_mod.month_name[m]} {y}"},
                "summary": {"total_invoices": 0, "total_billed": 0, "total_billed_all": 0,
                            "total_projected": 0, "total_collected": 0, "total_outstanding": 0,
                            "paid_count": 0, "unpaid_count": 0, "overdue_count": 0,
                            "collection_rate": 0, "active_customers_count": 0,
                            "orphan_invoice_count": 0, "orphan_invoice_total": 0},
                "payment_details": [], "method_breakdown": {},
                "top_packages": [], "overdue_list": [], "daily_breakdown": []
            }
        custs_q_for_inv["device_id"] = {"$in": allowed}

    if custs_q_for_inv:
        custs_for_inv = await db.customers.find(custs_q_for_inv, {"id": 1}).to_list(None)
        q["customer_id"] = {"$in": [c["id"] for c in custs_for_inv]}

    invoices = await db.invoices.find(q, {"_id": 0}).to_list(10000)

    customer_ids = list({i["customer_id"] for i in invoices})
    pkg_ids = list({i["package_id"] for i in invoices})
    custs_map = {c["id"]: c for c in await db.customers.find(
        {"id": {"$in": customer_ids}}, {"_id": 0}).to_list(2000)}
    pkgs_map = {p["id"]: p for p in await db.billing_packages.find(
        {"id": {"$in": pkg_ids}}, {"_id": 0}).to_list(200)}

    paid_inv = [i for i in invoices if i.get("status") == "paid"]
    unpaid_inv = [i for i in invoices if i.get("status") == "unpaid"]
    overdue_inv = [i for i in invoices if i.get("status") == "overdue"]

    # 1. Proyeksi Penagihan -> Potensi pendapatan dari user aktif saat ini
    custs_q = {"service_type": "pppoe"} 
    if device_id:
        custs_q["device_id"] = device_id
    
    active_customers = await db.customers.find(custs_q, {"id": 1, "package_id": 1, "installation_fee": 1}).to_list(10000)
    active_customer_ids = {c["id"] for c in active_customers}
    active_pkg_ids = list({c["package_id"] for c in active_customers if c.get("package_id")})
    active_pkgs_map = {p["id"]: p for p in await db.billing_packages.find({"id": {"$in": active_pkg_ids}}).to_list(1000)}
    
    # Total Proyeksi = Sum (Harga Paket + Biaya Pasang) per user aktif
    total_projected = sum(
        (active_pkgs_map[c["package_id"]].get("price", 0) if c.get("package_id") in active_pkgs_map else 0)
        + c.get("installation_fee", 0)
        for c in active_customers
    )

    # 2. Realisasi Penagihan -> Berdasarkan invoice yang telah terbuat
    # Filter out orphan invoices (customer sudah dihapus dari sistem)
    valid_invoices = [i for i in invoices if i["customer_id"] in active_customer_ids]
    orphan_invoices = [i for i in invoices if i["customer_id"] not in active_customer_ids]
    
    actual_total_billed = sum(i.get("total", 0) for i in valid_invoices)  # Hanya invoice dari customer aktif
    actual_total_billed_all = sum(i.get("total", 0) for i in invoices)  # Semua invoice (termasuk orphan)
    total_collected = sum(i.get("total", 0) for i in paid_inv if i["customer_id"] in active_customer_ids)
    total_outstanding = sum(i.get("total", 0) for i in overdue_inv if i["customer_id"] in active_customer_ids)
    
    # Collection Rate = Diterima / (Seluruh Tagihan Terbit)
    collection_rate = round(total_collected / actual_total_billed * 100, 1) if actual_total_billed else 0

    # 3. Daftar Tunggakan -> Semua overdue di bulan tsb
    overdue_detail = []
    for inv in sorted(overdue_inv, key=lambda x: x.get("total", 0), reverse=True):
        c = custs_map.get(inv["customer_id"], {})
        p = pkgs_map.get(inv["package_id"], {})
        status_billing = "Overdue"
        status_mikrotik = "Isolir" if inv.get("mt_disabled") else ("Aktif" if c.get("active") else "Nonaktif")
        
        overdue_detail.append({
            "invoice_id": inv["id"],
            "invoice_number": inv.get("invoice_number"),
            "customer_name": c.get("name", "—"),
            "customer_username": c.get("username", "—"),
            "customer_phone": c.get("phone", ""),
            "package_name": p.get("name", "—"),
            "total": inv.get("total", 0),
            "due_date": inv.get("due_date", ""),
            "status_billing": status_billing,
            "status_mikrotik": status_mikrotik,
        })

    # 4. Detail Metode Pembayaran List
    payment_details = []
    for inv in sorted(paid_inv, key=lambda x: x.get("paid_at", ""), reverse=True):
        c = custs_map.get(inv["customer_id"], {})
        p = pkgs_map.get(inv["package_id"], {})
        payment_details.append({
            "invoice_number": inv.get("invoice_number"),
            "customer_name": c.get("name", "—"),
            "package_name": p.get("name", "—"),
            "payment_method": inv.get("payment_method") or "cash",
            "paid_at": inv.get("paid_at", ""),
            "total": inv.get("total", 0)
        })

    # Top packages by revenue
    pkg_revenue = {}
    for inv in paid_inv:
        pid = inv.get("package_id", "")
        pkg_revenue[pid] = pkg_revenue.get(pid, 0) + inv.get("total", 0)
    top_packages = sorted(
        [{"name": pkgs_map.get(pid, {}).get("name", "—"), "revenue": rev}
         for pid, rev in pkg_revenue.items()],
        key=lambda x: x["revenue"], reverse=True
    )[:5]

    # Daily breakdown for chart
    import calendar as cal_mod
    _, last_day = cal_mod.monthrange(y, m)
    daily_breakdown = []
    
    for day in range(1, last_day + 1):
        day_str = f"{y}-{m:02d}-{day:02d}"
        day_paid = [i for i in paid_inv if str(i.get("paid_at", "")).startswith(day_str)]
        daily_breakdown.append({
            "day": day,
            "total": sum(i.get("total", 0) for i in day_paid)
        })

    month_name = cal_mod.month_name[m]

    return {
        "period": {"month": m, "year": y, "label": f"{month_name} {y}"},
        "summary": {
            "total_invoices": len(invoices),
            "total_billed": actual_total_billed,        # Tagihan dari customer aktif saja
            "total_billed_all": actual_total_billed_all,# Semua invoice termasuk orphan
            "total_projected": total_projected,         # Proyeksi dari customer aktif (paket x jumlah user)
            "total_collected": total_collected,
            "total_outstanding": total_outstanding,
            "paid_count": len([i for i in paid_inv if i["customer_id"] in active_customer_ids]),
            "unpaid_count": len([i for i in unpaid_inv if i["customer_id"] in active_customer_ids]),
            "overdue_count": len([i for i in overdue_inv if i["customer_id"] in active_customer_ids]),
            "collection_rate": round(total_collected / actual_total_billed * 100, 1) if actual_total_billed else 0,
            "active_customers_count": len(active_customers),  # Jumlah pelanggan aktif saat ini
            "orphan_invoice_count": len(orphan_invoices),     # Invoice dari pelanggan yang sudah dihapus
            "orphan_invoice_total": sum(i.get("total", 0) for i in orphan_invoices),  # Total nilai orphan
        },
        "payment_details": payment_details,
        "method_breakdown": {}, 
        "top_packages": top_packages,
        "overdue_list": overdue_detail,
        "daily_breakdown": daily_breakdown
    }


@router.get("/hotspot-financial-report")
async def hotspot_financial_report(
    month: int = Query(0),
    year: int = Query(0),
    device_id: str = Query(""),
    user=Depends(get_current_user),
):
    """Laporan keuangan khusus voucher Hotspot (Online WA vs Offline)."""
    db = get_db()
    today = date.today()
    m = month or today.month
    y = year or today.year
    period_prefix = f"{y}-{m:02d}"

    import calendar as cal_mod
    _, last_day = cal_mod.monthrange(y, m)
    start_date = f"{y}-{m:02d}-01"
    end_date = f"{y}-{m:02d}-{last_day:02d}T23:59:59"

    # Online WA Sales dari db.hotspot_invoices yg paid
    q_wa = {
        "status": "paid",
        "paid_at": {"$gte": start_date, "$lte": end_date}
    }
    wa_invoices = await db.hotspot_invoices.find(q_wa).to_list(10000)

    # Offline Sales dari db.hotspot_vouchers
    q_offline = {
        "created_at": {"$gte": start_date, "$lte": end_date}
    }
    if device_id:
        q_offline["device_id"] = device_id
        
    all_vouchers = await db.hotspot_vouchers.find(q_offline).to_list(10000)
    
    # Kecualikan voucher yang dibuat otomatis dari WA AI Bot
    wa_usernames = {inv.get("voucher_username") for inv in wa_invoices if inv.get("voucher_username")}
    
    offline_vouchers = [v for v in all_vouchers if v.get("username") not in wa_usernames]

    # Daily aggregation
    daily_sales = []
    total_wa = 0
    total_offline = 0
    
    for day in range(1, last_day + 1):
        day_str = f"{y}-{m:02d}-{day:02d}"
        
        day_wa = [inv for inv in wa_invoices if str(inv.get("paid_at", "")).startswith(day_str)]
        sum_wa = sum(float(inv.get("amount", 0)) for inv in day_wa)
        
        day_off = [v for v in offline_vouchers if str(v.get("created_at", "")).startswith(day_str)]
        sum_off = sum(float(v.get("price") or 0) for v in day_off)
        
        total_wa += sum_wa
        total_offline += sum_off
        
        daily_sales.append({
            "date": day_str,
            "day": day,
            "wa_sales": sum_wa,
            "offline_sales": sum_off,
            "total": sum_wa + sum_off
        })

    month_name = cal_mod.month_name[m]

    return {
        "period": {"month": m, "year": y, "label": f"{month_name} {y}"},
        "summary": {
            "total_wa_sales": total_wa,
            "total_offline_sales": total_offline,
            "total_revenue": total_wa + total_offline,
            "wa_count": len(wa_invoices),
            "offline_count": len(offline_vouchers),
        },
        "daily_breakdown": daily_sales,
    }

@router.get("/invoices/{invoice_id}")
async def get_invoice(invoice_id: str, user=Depends(get_current_user)):
    db = get_db()
    inv = await db.invoices.find_one({"id": invoice_id}, {"_id": 0})
    if not inv:
        raise HTTPException(404, "Invoice tidak ditemukan")

    customer = await db.customers.find_one({"id": inv["customer_id"]}, {"_id": 0}) or {}
    pkg = await db.billing_packages.find_one({"id": inv["package_id"]}, {"_id": 0}) or {}

    inv["customer"] = customer
    inv["package"] = pkg
    return inv


@router.post("/invoices", status_code=201)
async def create_invoice(data: InvoiceCreate, background_tasks: BackgroundTasks, user=Depends(require_write)):
    db = get_db()

    # Validasi customer dan package
    customer = await db.customers.find_one({"id": data.customer_id})
    if not customer:
        raise HTTPException(404, "Customer tidak ditemukan")

    # ── RBAC: cek hak akses user ke device customer ini ────────────────
    customer_device_id = customer.get("device_id", "")
    if not check_device_access(user, customer_device_id):
        raise HTTPException(403, "Anda tidak memiliki hak akses untuk membuat tagihan untuk pelanggan pada router ini")

    pkg = await db.billing_packages.find_one({"id": data.package_id})
    if not pkg:
        raise HTTPException(404, "Paket tidak ditemukan")

    # Cek duplicate (customer + periode yang sama)
    existing = await db.invoices.find_one({
        "customer_id": data.customer_id,
        "period_start": data.period_start,
    })
    if existing:
        raise HTTPException(409, "Invoice periode ini sudah ada untuk customer tersebut")

    # Nomor invoice: hitung urutan bulan ini
    today = date.today()
    period_prefix = f"{today.year}-{today.month:02d}"
    count = await db.invoices.count_documents(
        {"period_start": {"$regex": f"^{period_prefix}"}}
    )

    # Kode unik anti-collision: 100-999, dijamin tidak bentrok pelanggan lain
    unique_code = await _generate_unique_code(
        db, data.customer_id, data.amount - data.discount, period_prefix
    )
    total = data.amount - data.discount + unique_code

    doc = {
        "id": str(uuid.uuid4()),
        "invoice_number": _invoice_num(count + 1),
        "customer_id": data.customer_id,
        "customer_name": customer.get("name", ""),
        "customer_username": customer.get("username", ""),
        "package_id": data.package_id,
        # ── Tenant key: simpan device_id dari customer agar invoice terisolasi per router
        "device_id": customer_device_id,
        "amount": data.amount,
        "discount": data.discount,
        "unique_code": unique_code,
        "total": total,
        "period_start": data.period_start,
        "period_end": data.period_end,
        "due_date": data.due_date,
        "status": "unpaid",
        "notes": data.notes,
        "paid_at": None,
        "payment_method": None,
        "created_at": _now(),
    }
    await db.invoices.insert_one(doc)
    doc.pop("_id", None)

    # ── Trigger WA Notifikasi Tagihan Baru ──
    customer_phone = customer.get("phone", "")
    if customer_phone:
        background_tasks.add_task(_bg_send_whatsapp_reminders, [doc["id"]])

    return doc


@router.post("/invoices/bulk-create")
async def bulk_create_invoices(
    month: int = Query(...),
    year: int = Query(...),
    service_type: str = Query(""),    # "" = semua, "pppoe", "hotspot"
    device_id: str = Query(""),
    user=Depends(require_write),
):
    """
    Buat invoice massal untuk semua customer aktif yang belum punya tagihan bulan ini.
    Harga diambil dari paket yang ditetapkan. Customer tanpa paket dilewati.
    """
    db = get_db()
    from calendar import monthrange

    _, last_day = monthrange(year, month)
    period_start = f"{year}-{month:02d}-01"
    period_end = f"{year}-{month:02d}-{last_day:02d}"
    period_prefix = f"{year}-{month:02d}"

    q = {"active": True}
    if service_type:
        q["service_type"] = service_type

    # ── RBAC: filter customer berdasarkan allowed_devices ──────────────────
    scope = get_user_allowed_devices(user)
    if scope is None:
        if device_id:
            q["device_id"] = device_id
    else:
        allowed = scope
        if device_id:
            allowed = [d for d in scope if d == device_id]
        if not allowed:
            return {"message": "Tidak ada device yang diizinkan", "created": 0, "skipped": 0, "errors": []}
        q["device_id"] = {"$in": allowed}

    customers = await db.customers.find(q).to_list(5000)

    created = 0
    skipped = 0
    errors = []

    for c in customers:
        if not c.get("package_id"):
            skipped += 1
            continue

        existing = await db.invoices.find_one({
            "customer_id": c["id"],
            "period_start": {"$regex": f"^{period_prefix}"},
        })
        if existing:
            skipped += 1
            continue

        pkg = await db.billing_packages.find_one({"id": c["package_id"]})
        if not pkg:
            errors.append(f"{c['name']}: paket tidak ditemukan")
            skipped += 1
            continue

        due_day = min(c.get("due_day", 10), last_day)
        due_date = f"{year}-{month:02d}-{due_day:02d}"

        count = await db.invoices.count_documents(
            {"period_start": {"$regex": f"^{period_prefix}"}}
        ) + created

        # Kode unik anti-collision per pelanggan per bulan
        unique_code = await _generate_unique_code(db, c["id"], pkg["price"], period_prefix)
        total = pkg["price"] + unique_code

        doc = {
            "id": str(uuid.uuid4()),
            "invoice_number": _invoice_num(count + 1),
            "customer_id": c["id"],
            "customer_name": c.get("name", ""),
            "customer_username": c.get("username", ""),
            "package_id": c["package_id"],
            # ── Tenant key: simpan device_id dari customer ke setiap invoice ──
            "device_id": c.get("device_id", ""),
            "amount": pkg["price"],
            "discount": 0,
            "unique_code": unique_code,
            "total": total,
            "period_start": period_start,
            "period_end": period_end,
            "due_date": due_date,
            "status": "unpaid",
            "notes": "",
            "paid_at": None,
            "payment_method": None,
            "created_at": _now(),
        }
        await db.invoices.insert_one(doc)
        created += 1

    return {
        "message": f"Selesai: {created} invoice dibuat, {skipped} dilewati",
        "created": created,
        "skipped": skipped,
        "errors": errors,
    }


class InvoiceBulkReminderReq(BaseModel):
    invoice_ids: list[str]

async def _bg_send_whatsapp_paid(invoice_id: str):
    db = get_db()
    inv = await db.invoices.find_one({"id": invoice_id})
    if not inv:
        return
        
    c = await db.customers.find_one({"id": inv.get("customer_id")})
    if not c or (not c.get("phone") and not c.get("fcm_token")):
        return

    settings = await fetch_billing_settings(db, c.get("device_id") if c else None)
    wa_type = settings.get("wa_gateway_type", "fonnte")
    url = settings.get("wa_api_url", "https://api.fonnte.com/send")
    token = settings.get("wa_token", "")
    template = settings.get("wa_template_paid", "Pembayaran {invoice_number} sebesar {total} berhasil diterima via {payment_method}.")
    fcm_template = settings.get("fcm_template_paid", "Pembayaran {invoice_number} sebesar {total} telah kami terima.")



    p = await db.billing_packages.find_one({"id": inv.get("package_id")})
    
    # Format message
    msg = template.replace("{customer_name}", c.get("name", ""))
    msg = msg.replace("{invoice_number}", inv.get("invoice_number", ""))
    msg = msg.replace("{package_name}", p.get("name", "") if p else "")
    msg = msg.replace("{total}", _rupiah(inv.get("total", 0)))
    msg = msg.replace("{period}", f"{_dtfmt(inv.get('period_start', ''))} s/d {_dtfmt(inv.get('period_end', ''))}")
    msg = msg.replace("{due_date}", _dtfmt(inv.get("due_date", "")))
    pm = inv.get("payment_method", "cash")
    msg = msg.replace("{payment_method}", pm.upper())
    
    # FCM Notification
    if c.get("fcm_token"):
        fcm_msg = (fcm_template
                   .replace("{customer_name}", c.get("name", ""))
                   .replace("{invoice_number}", inv.get("invoice_number", ""))
                   .replace("{package_name}", p.get("name", "") if p else "")
                   .replace("{total}", _rupiah(inv.get("total", 0)))
                   .replace("{period}", f"{_dtfmt(inv.get('period_start', ''))} s/d {_dtfmt(inv.get('period_end', ''))}")
                   .replace("{due_date}", _dtfmt(inv.get("due_date", "")))
                   .replace("{payment_method}", pm.upper()))
        try:
            from services.firebase_service import send_push_notification
            await send_push_notification([c["fcm_token"]], "Pembayaran Berhasil Diterima", fcm_msg)
        except Exception as e:
            logger.error(f"FCM Paid notification error for {invoice_id}: {e}")

    # WA Notification (Hanya untuk non-PPPoE)
    if c.get("service_type") != "pppoe":
        phone = c.get("phone")
        if phone and url and token:
            try:
                async with httpx.AsyncClient(timeout=10) as client:
                    if wa_type == "fonnte":
                        await client.post(url, headers={"Authorization": token}, data={"target": phone, "message": msg, "countryCode": "62"})
                    elif wa_type == "wablas":
                        await client.post(url, headers={"Authorization": token}, json={"phone": phone, "message": msg})
                    else:
                        headers = {"Authorization": token} if token else {}
                        await client.post(url, headers=headers, json={"phone": phone, "message": msg})
            except Exception as e:
                logger.error(f"WA Paid notification error for {invoice_id}: {e}")

async def _bg_send_whatsapp_reminders(invoice_ids: list[str]):
    db = get_db()
    
    # Base fallback in case any settings are needed globally
    global_settings = await fetch_billing_settings(db, None)

    if not url:
        return

    for inv_id in invoice_ids:
        inv = await db.invoices.find_one({"id": inv_id})
        if not inv or inv.get("status") == "paid":
            continue
        
        c = await db.customers.find_one({"id": inv["customer_id"]})
        if not c or not c.get("phone"):
            continue
            
        # Blokir WA reminder reguler untuk PPPoE (Hanya via Portal/Isolir)
        if c.get("service_type") == "pppoe":
            continue
            
        p = await db.billing_packages.find_one({"id": inv["package_id"]})
        
        # Format message
        msg = template.replace("{customer_name}", c.get("name", ""))
        msg = msg.replace("{invoice_number}", inv.get("invoice_number", ""))
        msg = msg.replace("{package_name}", p.get("name", "") if p else "")
        msg = msg.replace("{total}", _rupiah(inv.get("total", 0)))
        msg = msg.replace("{period}", f"{_dtfmt(inv.get('period_start', ''))} s/d {_dtfmt(inv.get('period_end', ''))}")
        msg = msg.replace("{due_date}", _dtfmt(inv.get("due_date", "")))
        
        phone = c["phone"]
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                if wa_type == "fonnte":
                    await client.post(url, headers={"Authorization": token}, data={"target": phone, "message": msg, "countryCode": "62"})
                elif wa_type == "wablas":
                    await client.post(url, headers={"Authorization": token}, json={"phone": phone, "message": msg})
                else:
                    headers = {"Authorization": token} if token else {}
                    await client.post(url, headers=headers, json={"phone": phone, "message": msg})
        except Exception as e:
            logger.error(f"Bulk WA error for {inv_id}: {e}")
            
        # Update last_reminder_at
        await db.invoices.update_one({"id": inv_id}, {"$set": {"last_reminder_at": _now()}})
        
        await asyncio.sleep(delay)

@router.post("/invoices/bulk-reminder")
async def bulk_send_reminder(req: InvoiceBulkReminderReq, background_tasks: BackgroundTasks, user=Depends(require_admin)):
    if not req.invoice_ids:
        raise HTTPException(400, "Tidak ada invoice yang dipilih")
    background_tasks.add_task(_bg_send_whatsapp_reminders, req.invoice_ids)
    return {"message": f"Pengingat massal WA untuk {len(req.invoice_ids)} tagihan mulai diproses secara bertahap."}


@router.post("/invoices/{invoice_id}/send-wa")
async def send_invoice_wa(invoice_id: str, background_tasks: BackgroundTasks, user=Depends(require_write)):
    """Kirim notifikasi WhatsApp untuk satu invoice menggunakan gateway (Direct)."""
    db = get_db()
    inv = await db.invoices.find_one({"id": invoice_id})
    if not inv:
        # Juga cari di hotspot_invoices jika tidak ada di pppoe
        inv = await db.hotspot_invoices.find_one({"id": invoice_id})
        if not inv:
            raise HTTPException(404, "Invoice tidak ditemukan")

    # Jalankan task pengiriman di background agar tidak memblock UI
    background_tasks.add_task(_bg_send_whatsapp_reminders, [invoice_id])
    return {"message": "Permintaan kirim WhatsApp berhasil dibuat (Background)"}


@router.patch("/invoices/{invoice_id}/pay")
async def mark_paid(invoice_id: str, data: PaymentUpdate, background_tasks: BackgroundTasks, user=Depends(require_write)):
    """Tandai invoice sebagai lunas dan auto-enable user MikroTik jika sebelumnya di-disable."""
    db = get_db()
    inv = await db.invoices.find_one({"id": invoice_id})
    if not inv:
        raise HTTPException(404, "Invoice tidak ditemukan")
    if inv.get("status") == "paid":
        raise HTTPException(400, "Invoice sudah lunas")

    paid_at = _now()
    
    update_data = {
        "status": "paid",
        "paid_at": paid_at,
        "payment_method": data.payment_method,
        "paid_notes": data.paid_notes,
    }

    # Hapus kode unik jika bayar menggunakan cash
    if data.payment_method == "cash":
        amount = inv.get("amount", 0)
        discount = inv.get("discount", 0)
        update_data["unique_code"] = 0
        update_data["total"] = amount - discount

    await db.invoices.update_one(
        {"id": invoice_id},
        {"$set": update_data}
    )

    # Auto re-aktivasi terpusat via helper — enable MikroTik + restore SSID
    mt_msg = await _after_paid_actions(invoice_id, db)

    # ── Trigger WA Lunas ──
    background_tasks.add_task(_bg_send_whatsapp_paid, invoice_id)

    return {"message": f"Invoice ditandai lunas{mt_msg}", "paid_at": paid_at}


# ══════════════════════════════════════════════════════════════════════════════
# PAYMENT GATEWAY — Buat VA / QRIS / E-Wallet
# ══════════════════════════════════════════════════════════════════════════════

class CreatePaymentRequest(BaseModel):
    provider: str                   # "xendit" | "bca" | "bri"
    payment_type: str = "virtual_account"  # "virtual_account" | "qris" | "ewallet"
    bank_code: Optional[str] = None       # Untuk VA Xendit: BNI, BCA, BRI, MANDIRI
    ewallet_type: Optional[str] = None   # GOPAY | OVO | DANA | SHOPEEPAY


@router.post("/invoices/{invoice_id}/create-payment")
async def create_payment_for_invoice(
    invoice_id: str,
    data: CreatePaymentRequest,
    user=Depends(require_write),
):
    """
    Buat instruksi pembayaran (VA/QRIS/E-Wallet) untuk invoice yang belum lunas.
    Hasil berupa nomor VA atau QR string yang ditampilkan di UI.
    """
    db = get_db()
    inv = await db.invoices.find_one({"id": invoice_id})
    if not inv:
        raise HTTPException(404, "Invoice tidak ditemukan")
    if inv.get("status") == "paid":
        raise HTTPException(400, "Invoice sudah lunas")

    customer = await db.customers.find_one({"id": inv.get("customer_id", "")}) or {}
    settings = await fetch_billing_settings(db, customer.get("device_id"))

    if not settings.get("payment_gateway_enabled"):
        raise HTTPException(503, "Payment gateway belum diaktifkan. Aktifkan di menu Pengaturan Billing.")

    try:
        from services.payment_gateway import create_payment, PaymentGatewayError
        result = await create_payment(
            provider=data.provider,
            payment_type=data.payment_type,
            invoice=inv,
            customer=customer,
            settings=settings,
            bank_code=data.bank_code,
            ewallet_type=data.ewallet_type,
        )
    except Exception as pg_err:
        logger.error(f"[PayGW] create_payment error: {pg_err}")
        raise HTTPException(502, f"Gagal membuat instruksi bayar: {pg_err}")

    # Simpan payment_info ke invoice agar bisa di-polling
    await db.invoices.update_one(
        {"id": invoice_id},
        {"$set": {
            "payment_info": result,
            "payment_provider": data.provider,
            "payment_type": data.payment_type,
        }}
    )

    logger.info(
        f"[PayGW] Invoice {inv.get('invoice_number')} — "
        f"{data.provider.upper()} {data.payment_type} created"
    )
    return {
        "message": "Instruksi pembayaran berhasil dibuat",
        "payment_info": result,
        "invoice_number": inv.get("invoice_number"),
        "amount": inv.get("total", 0),
    }


@router.get("/invoices/{invoice_id}/payment-status")
async def check_payment_status(
    invoice_id: str,
    user=Depends(get_current_user),
):
    """Polling status pembayaran VA/QRIS dari provider (untuk auto-update UI)."""
    db = get_db()
    inv = await db.invoices.find_one({"id": invoice_id}, {"_id": 0})
    if not inv:
        raise HTTPException(404, "Invoice tidak ditemukan")
    return {
        "invoice_id": invoice_id,
        "invoice_number": inv.get("invoice_number", ""),
        "status": inv.get("status", "unpaid"),
        "payment_provider": inv.get("payment_provider", ""),
        "payment_type": inv.get("payment_type", ""),
        "payment_info": inv.get("payment_info", {}),
    }


@router.patch("/invoices/{invoice_id}/unpay")
async def mark_unpaid(invoice_id: str, user=Depends(require_admin)):
    """Batalkan pembayaran (rollback ke unpaid)."""
    db = get_db()
    await db.invoices.update_one(
        {"id": invoice_id},
        {"$set": {"status": "unpaid", "paid_at": None, "payment_method": None}}
    )
    return {"message": "Status invoice dikembalikan ke belum bayar"}



@router.delete("/invoices/{invoice_id}")
async def delete_invoice(invoice_id: str, user=Depends(require_admin)):
    db = get_db()
    result = await db.invoices.delete_one({"id": invoice_id})
    if result.deleted_count == 0:
        raise HTTPException(404, "Invoice tidak ditemukan")
    return {"message": "Invoice dihapus"}


# ── Janji Bayar (Promise to Pay) ──────────────────────────────────────────────

class PromiseDateRequest(BaseModel):
    promise_date: Optional[str] = None   # ISO date "YYYY-MM-DD", None = hapus janji


@router.patch("/invoices/{invoice_id}/promise-date")
async def set_promise_date(
    invoice_id: str,
    data: PromiseDateRequest,
    user=Depends(require_write),
):
    """
    Atur 'Janji Bayar' — custom grace period per invoice.
    Jika promise_date diset ke tanggal di masa depan, auto-isolir akan di-skip
    sampai tanggal tersebut terlampaui.
    Kirim promise_date: null untuk menghapus janji bayar.
    """
    db = get_db()
    inv = await db.invoices.find_one({"id": invoice_id})
    if not inv:
        raise HTTPException(404, "Invoice tidak ditemukan")
    if inv.get("status") == "paid":
        raise HTTPException(400, "Invoice sudah lunas, tidak perlu Janji Bayar")

    # Validasi format tanggal jika diisi
    if data.promise_date:
        try:
            from datetime import date as _date
            pd = _date.fromisoformat(data.promise_date)
            # FIX B4: Gunakan <= agar hari ini juga ditolak (janji bayar hari ini tidak efektif)
            if pd <= _date.today():
                raise HTTPException(400, "Tanggal Janji Bayar harus di masa depan (minimal besok)")
        except ValueError:
            raise HTTPException(400, "Format tanggal tidak valid (gunakan YYYY-MM-DD)")

    update_val = data.promise_date  # bisa str atau None

    await db.invoices.update_one(
        {"id": invoice_id},
        {
            "$set": {
                "promise_date": update_val,
                "promise_set_by": user.get("username", ""),
                "promise_set_at": _now(),
            }
        }
    )

    if update_val:
        msg = f"Janji Bayar ditetapkan: {update_val}"
        logger.info(
            f"[Billing] Invoice {inv.get('invoice_number')} — Janji Bayar hingga {update_val} "
            f"(oleh {user.get('username','')})"
        )
    else:
        msg = "Janji Bayar dihapus"
        logger.info(
            f"[Billing] Invoice {inv.get('invoice_number')} — Janji Bayar dihapus "
            f"(oleh {user.get('username','')})"
        )

    return {"message": msg, "promise_date": update_val}


# MOOTA WEBHOOK (Auto-Billing Checkout)
# ══════════════════════════════════════════════════════════════════════════════
import traceback
import hashlib
import hmac
from fastapi import Request

@webhook_router.post("/moota")
async def moota_webhook(payload: list[dict], request: Request, background_tasks: BackgroundTasks):
    """
    Endpoint untuk menerima payload mutasi dari Moota.
    Format Moota Payload (Array of Dict):
    [
      { "id": "123", "amount": 150021, "type": "CR", "description": "TRANSFER MASUK", ... }
    ]
    Setiap mutasi tipe 'CR' akan dicari invoice-nya berdasarkan nominal 'amount' yang sama persis (total harga + kode unik).
    """
    db = get_db()
    
    # 0. Verifikasi HMAC Signature (Jika dikonfigurasi)
    settings = await fetch_billing_settings(db, None)
    webhook_secret = settings.get("moota_webhook_secret", "").strip()
    
    if webhook_secret:
        signature = request.headers.get("signature") or request.headers.get("Signature") or request.headers.get("x-moota-signature")
        if not signature:
            logger.warning("[Moota Webhook] Ditolak: Missing signature header")
            raise HTTPException(status_code=403, detail="Missing signature header")
            
        raw_body = await request.body()
        expected_mac = hmac.new(webhook_secret.encode('utf-8'), raw_body, hashlib.sha256).hexdigest()
        
        if not hmac.compare_digest(expected_mac, signature):
            logger.warning(f"[Moota Webhook] Ditolak: HMAC mismatch. Expected: {expected_mac}, Got: {signature}")
            raise HTTPException(status_code=403, detail="Invalid HMAC signature")

    processed = 0
    matched = 0
    
    # 1. Pastikan payload berupa list (standar Moota API v2)
    for mutasi in payload:
        if mutasi.get("type") != "CR":  # Hanya proses mutasi masuk (Credit)
            continue
            
        processed += 1
        amount = mutasi.get("amount")
        if not amount:
            continue
            
        # 2. Cari Invoice yang totalnya persis sama — cek KEDUA collection (PPPoE & Voucher)
        try:
            amount_int = int(float(amount))
            q_match = {"total": amount_int, "status": {"$in": ["unpaid", "overdue"]}}

            # Cari di kedua database
            inv_pppoe = await db.invoices.find_one(q_match, sort=[("created_at", -1)])
            inv_hotspot = await db.hotspot_invoices.find_one(q_match, sort=[("created_at", -1)])

            inv = None
            inv_collection = ""

            # Jika nominal total bentrok (ada di PPPoE dan Hotspot), ambil yang paking baru dibuat
            if inv_pppoe and inv_hotspot:
                if inv_hotspot.get("created_at", "") > inv_pppoe.get("created_at", ""):
                    inv = inv_hotspot
                    inv_collection = "hotspot_invoices"
                else:
                    inv = inv_pppoe
                    inv_collection = "invoices"
            elif inv_hotspot:
                inv = inv_hotspot
                inv_collection = "hotspot_invoices"
            elif inv_pppoe:
                inv = inv_pppoe
                inv_collection = "invoices"

            if not inv:
                logger.info(f"[Moota Webhook] Mutasi CR Rp{amount_int} tidak cocok dengan invoice manapun (PPPoE maupun Voucher).")
                continue

            matched += 1
            invoice_id = inv["id"]
            paid_at = _now()

            # 3. Update Invoice Jadi Lunas di collection yang tepat
            target_collection = db.invoices if inv_collection == "invoices" else db.hotspot_invoices
            await target_collection.update_one(
                {"id": invoice_id},
                {"$set": {
                    "status": "paid",
                    "paid_at": paid_at,
                    "payment_method": "transfer_moota",
                    "paid_notes": f"Auto-paid by Moota mutasi ID {mutasi.get('id')}",
                    "moota_mutasi_id": mutasi.get("id"),
                }}
            )
            logger.info(f"[Moota Webhook] Invoice {inv['invoice_number']} LUNAS by Moota (Rp{amount_int})")

            # 4. Tindak lanjut setelah lunas — berbeda antara PPPoE dan Voucher WA
            if inv_collection == "hotspot_invoices":
                # ── VOUCHER HOTSPOT: Kirim kode voucher via WA & Create di MikroTik ──
                phone = inv.get("customer_phone", "")
                cust_name = inv.get("customer_name", "Pelanggan")
                vc_user = inv.get("voucher_username", "")
                vc_pass = inv.get("voucher_password", "")
                pkg_name = inv.get("package_name", "")

                pkg = await db.billing_packages.find_one({"id": inv.get("package_id")})
                if vc_user:
                    # Coba ambil dari snapshot invoice dulu (lebih baru/konsisten)
                    # Jika tidak ada, baru ambil dari master package
                    profile = (
                        inv.get("profile_name") or 
                        (pkg.get("profile_name") if pkg else None) or
                        (pkg.get("profile") if pkg else None) or
                        (pkg.get("hotspot_profile") if pkg else None) or
                        "default"
                    )
                    # Pastikan profile tidak kosong string
                    if not profile or str(profile).strip() == "":
                        profile = "default"
                    
                    limit_uptime = (
                        inv.get("uptime_limit") or 
                        (pkg.get("uptime_limit") if pkg else None) or 
                        (pkg.get("validity_seconds") if pkg else None) or 
                        ""
                    )
                    
                    p_name = inv.get("package_name") or (pkg.get("name") if pkg else "Unknown")
                    logger.info(f"[Moota Webhook] Voucher {vc_user} menggunakan profile='{profile}' (Snapshot/Pkg: {p_name})")


                    
                    hs_data = {
                        "server": "all",
                        "name": vc_user,
                        "password": vc_pass,
                        "profile": profile,
                        "comment": f"Voucher: {cust_name} ({phone})" if phone else f"Voucher Captive Portal: {pkg_name}"
                    }
                    if limit_uptime:
                        hs_data["limit-uptime"] = limit_uptime

                    # ── Voucher disimpan di NOC Sentinel SAJA (hotspot_vouchers) ──────────
                    # TIDAK dikirim ke MikroTik — autentikasi via RADIUS NOC Sentinel.
                    # Ini memastikan profile yang digunakan PERSIS sesuai paket yang dipilih
                    # dan tidak membebani router dengan operasi API tambahan.
                    import uuid
                    new_vid = str(uuid.uuid4())
                    # device_id diambil dari invoice (Captive Portal) atau kosong (WA Bot)
                    first_dev_id = inv.get("device_id") or ""
                    order_source  = inv.get("source", "online")
                    ip_addr = "online-payment"

                    logger.info(
                        f"[Moota Webhook] Voucher {vc_user} (profile='{profile}') "
                        f"dicatat di NOC Sentinel — TIDAK push ke MikroTik."
                    )

                    # Insert ke hotspot_vouchers (dashboard & RADIUS lookup)
                    try:
                        v_price    = (pkg.get("price",    0)  if pkg else None) or inv.get("amount",       0)
                        v_validity = (pkg.get("validity", "") if pkg else None) or inv.get("validity",     "")
                        v_pkgname  = (pkg.get("name",     "") if pkg else None) or inv.get("package_name", "")

                        await db.hotspot_vouchers.insert_one({
                            "id":           new_vid,
                            "username":     vc_user,
                            "password":     vc_pass,
                            "profile":      profile,
                            "server":       "all",
                            "price":        v_price,
                            "validity":     v_validity,
                            "uptime_limit": limit_uptime,
                            "package_name": v_pkgname,
                            "status":       "new",
                            "device_id":    first_dev_id,
                            "source":       order_source,
                            "created_at":   _now(),
                        })

                        await db.hotspot_sales.insert_one({
                            "id":         str(uuid.uuid4()),
                            "voucher_id": new_vid,
                            "username":   vc_user,
                            "price":      float(inv.get("amount", 0) or (pkg.get("price", 0) if pkg else 0)),
                            "created_at": _now(),
                            "device_ip":  ip_addr,
                            "source": (
                                "Captive Portal / Moota"
                                if order_source == "captive_portal"
                                else "WA AI Bot / Moota"
                            ),
                        })
                        logger.info(f"[Moota Webhook] Voucher & Sales disimpan untuk {vc_user}.")
                    except Exception as e:
                        logger.error(f"[Moota Webhook] Gagal simpan hotspot_vouchers/sales: {e}")

                if phone and vc_user:
                    settings = await fetch_billing_settings(db, device_id)
                    wa_url = settings.get("wa_api_url", "https://api.fonnte.com/send")
                    wa_token = settings.get("wa_token", "")
                    wa_type = settings.get("wa_gateway_type", "fonnte")

                    msg = (
                        f"✅ *Pembayaran Voucher Berhasil!*\n\n"
                        f"Yth. *{cust_name}*,\n"
                        f"Pembayaran sebesar *{_rupiah(amount_int)}* telah kami terima.\n\n"
                        f"🎫 *Kode Voucher Hotspot Anda:*\n"
                        f"Username : `{vc_user}`\n"
                        f"Password : `{vc_pass}`\n"
                        f"Paket     : {pkg_name}\n\n"
                        f"Cara pakai:\n"
                        f"1. Sambungkan ke WiFi hotspot\n"
                        f"2. Buka browser, akan muncul halaman login\n"
                        f"3. Masukkan username & password di atas\n\n"
                        f"Selamat menikmati! 🌐"
                    )

                    if wa_url and wa_token:
                        async def send_voucher_wa(ph=phone, m=msg, wu=wa_url, wt=wa_token, wtp=wa_type):
                            try:
                                async with httpx.AsyncClient(timeout=10) as client:
                                    if wtp == "fonnte":
                                        await client.post(wu, headers={"Authorization": wt},
                                                          data={"target": ph, "message": m, "countryCode": "62"})
                                    else:
                                        await client.post(wu, headers={"Authorization": wt},
                                                          json={"phone": ph, "message": m})
                                logger.info(f"[Moota Webhook] Kode voucher {vc_user} dikirim ke {ph}")
                            except Exception as wa_err:
                                logger.error(f"[Moota Webhook] Gagal kirim voucher WA: {wa_err}")

                        asyncio.create_task(send_voucher_wa())
                            
                    # Tandai voucher sudah dikirim
                    await db.hotspot_invoices.update_one(
                        {"id": invoice_id},
                        {"$set": {"voucher_sent": True, "updated_at": _now()}}
                    )
                    logger.info(f"[Moota Webhook] Voucher {vc_user}/{vc_pass} → {phone}")

            else:
                # ── PPPoE: Enable MikroTik + Restore SSID + Kirim WA (via helper terpusat) ──
                await _after_paid_actions(invoice_id, db)
                # Kirim WA lunas menggunakan template yang sudah dikonfigurasi admin
                background_tasks.add_task(_bg_send_whatsapp_paid, invoice_id)
                logger.info(
                    f"[Moota Webhook] PPPoE invoice {inv.get('invoice_number')} — "
                    f"re-aktivasi & notifikasi WA dijadwalkan."
                )

        except Exception as e:
            logger.error(f"[Moota Webhook] Error processing mutasi {mutasi.get('id')}: {traceback.format_exc()}")
            
    return {"message": f"Webhook processed. Total received: {len(payload)}, CR filtered: {processed}, matched invoices: {matched}"}


# ══════════════════════════════════════════════════════════════════════════════
# XENDIT WEBHOOK — Virtual Account, QRIS, E-Wallet Callbacks
# ══════════════════════════════════════════════════════════════════════════════

@webhook_router.post("/xendit")
async def xendit_webhook(request: Request, background_tasks: BackgroundTasks):
    """
    Endpoint callback dari Xendit (VA paid / QRIS paid / E-wallet settled).
    Xendit mengirim header: x-callback-token untuk verifikasi.
    external_id format: INV-YYYY-MM-NNNN-<timestamp>
    """
    db = get_db()
    settings = await fetch_billing_settings(db, None)
    webhook_token = settings.get("xendit_webhook_token", "").strip()

    # 1. Verifikasi x-callback-token
    if webhook_token:
        token_header = request.headers.get("x-callback-token", "")
        if not hmac.compare_digest(webhook_token, token_header):
            logger.warning("[Xendit Webhook] Ditolak: x-callback-token tidak valid")
            raise HTTPException(status_code=403, detail="Invalid callback token")

    raw_body = await request.body()
    try:
        payload = json.loads(raw_body)
    except Exception:
        raise HTTPException(400, "Invalid JSON payload")

    event_type = payload.get("event") or ""
    status = (payload.get("status") or "").upper()
    external_id = (
        payload.get("external_id")
        or payload.get("reference_id")
        or ""
    )
    amount = payload.get("amount") or payload.get("paid_amount") or 0

    # Hanya proses event PAID/SETTLED
    if status not in ("PAID", "SETTLED", "COMPLETED"):
        logger.info(f"[Xendit] Ignored: status={status}, external_id={external_id}")
        return {"message": "ignored"}

    # Cari invoice berdasarkan external_id (prefixed dengan invoice_number)
    # Format external_id: "INV-2026-04-0001-1234567890"
    invoice_number_part = external_id.rsplit("-", 1)[0] if "-" in external_id else external_id

    inv = await db.invoices.find_one({
        "invoice_number": invoice_number_part,
        "status": {"$in": ["unpaid", "overdue"]},
    })

    # Fallback: cari by payment_info.external_id
    if not inv:
        inv = await db.invoices.find_one({
            "payment_info.external_id": external_id,
            "status": {"$in": ["unpaid", "overdue"]},
        })

    if not inv:
        # Coba hotspot_invoices
        inv = await db.hotspot_invoices.find_one({
            "payment_info.external_id": external_id,
            "status": {"$in": ["unpaid", "overdue"]},
        })
        if inv:
            # Hotspot invoice paid
            await db.hotspot_invoices.update_one(
                {"id": inv["id"]},
                {"$set": {
                    "status": "paid",
                    "paid_at": _now(),
                    "payment_method": "xendit",
                    "paid_notes": f"Auto-paid via Xendit (ext_id: {external_id})",
                }}
            )
            background_tasks.add_task(_bg_send_whatsapp_paid, inv["id"])
            logger.info(f"[Xendit] Hotspot invoice {inv.get('id')} LUNAS via Xendit")
            return {"message": "ok"}

        logger.warning(f"[Xendit] Tidak ada invoice untuk external_id: {external_id}")
        return {"message": "invoice not found"}

    invoice_id = inv["id"]
    await db.invoices.update_one(
        {"id": invoice_id},
        {"$set": {
            "status": "paid",
            "paid_at": _now(),
            "payment_method": "xendit",
            "paid_notes": f"Auto-paid via Xendit (ext_id: {external_id}, amount: {amount})",
        }}
    )
    await _after_paid_actions(invoice_id, db)
    background_tasks.add_task(_bg_send_whatsapp_paid, invoice_id)
    logger.info(f"[Xendit] Invoice {inv.get('invoice_number')} LUNAS via Xendit (Rp{amount})")
    return {"message": "ok"}


# ══════════════════════════════════════════════════════════════════════════════
# BCA SNAP WEBHOOK — Virtual Account BCA Callback
# ══════════════════════════════════════════════════════════════════════════════

@webhook_router.post("/bca")
async def bca_webhook(request: Request, background_tasks: BackgroundTasks):
    """
    Endpoint callback dari BCA SNAP API saat VA dibayar.
    BCA mengirim: FreeText1 = invoice_number, Amount = jumlah pembayaran.
    """
    db = get_db()
    settings = await fetch_billing_settings(db, None)

    raw_body = await request.body()

    # Verifikasi BCA signature (opsional — aktifkan jika api_secret dikonfigurasi)
    bca_api_secret = settings.get("bca_api_secret", "").strip()
    if bca_api_secret:
        sig_header = request.headers.get("X-BCA-Signature", "")
        timestamp = request.headers.get("X-BCA-Timestamp", "")
        body_hash = hashlib.sha256(raw_body).hexdigest().lower()
        string_to_sign = f"POST:/banking/v2/corporates/va/payments:{body_hash}:{timestamp}"
        expected_sig = hmac.new(
            bca_api_secret.encode(), string_to_sign.encode(), hashlib.sha256
        ).hexdigest()
        if not hmac.compare_digest(expected_sig, sig_header):
            logger.warning("[BCA Webhook] Signature tidak valid")
            raise HTTPException(403, "Invalid BCA signature")

    try:
        payload = json.loads(raw_body)
    except Exception:
        raise HTTPException(400, "Invalid JSON payload")

    # BCA payload: {"FreeText1": "INV-2026-04-0001", "Amount": "150000", "CompanyCode": "..."}
    invoice_number = payload.get("FreeText1", "").strip()
    amount_str = payload.get("Amount", "0")
    try:
        amount = int(float(amount_str))
    except Exception:
        amount = 0

    if not invoice_number:
        return {"message": "no invoice number in payload"}

    inv = await db.invoices.find_one({
        "invoice_number": invoice_number,
        "status": {"$in": ["unpaid", "overdue"]},
    })
    if not inv:
        logger.warning(f"[BCA] Tidak ada invoice: {invoice_number}")
        return {"message": "invoice not found"}

    invoice_id = inv["id"]
    await db.invoices.update_one(
        {"id": invoice_id},
        {"$set": {
            "status": "paid",
            "paid_at": _now(),
            "payment_method": "bca_va",
            "paid_notes": f"Auto-paid via BCA VA (amount: {amount})",
        }}
    )
    await _after_paid_actions(invoice_id, db)
    background_tasks.add_task(_bg_send_whatsapp_paid, invoice_id)
    logger.info(f"[BCA] Invoice {invoice_number} LUNAS via BCA VA (Rp{amount})")
    return {"message": "ok", "transactionStatus": "00"}


# ══════════════════════════════════════════════════════════════════════════════
# BRI BRIVA WEBHOOK — Virtual Account BRI Callback
# ══════════════════════════════════════════════════════════════════════════════

@webhook_router.post("/bri")
async def bri_webhook(request: Request, background_tasks: BackgroundTasks):
    """
    Endpoint callback dari BRI BRIVA API saat VA dibayar.
    BRI mengirim: keterangan = invoice_number, amount = jumlah bayar.
    """
    db = get_db()
    settings = await fetch_billing_settings(db, None)

    raw_body = await request.body()

    # Verifikasi BRI HMAC signature
    bri_client_secret = settings.get("bri_client_secret", "").strip()
    if bri_client_secret:
        sig_header = request.headers.get("BRI-Signature", "")
        timestamp = request.headers.get("BRI-Timestamp", "")
        body_hash = hashlib.sha256(raw_body).hexdigest()
        path = "/v1/briva/callback"
        string_to_sign = f"POST:{path}:{body_hash}:{timestamp}"
        expected_sig = hmac.new(
            bri_client_secret.encode(), string_to_sign.encode(), hashlib.sha256
        ).hexdigest()
        if not hmac.compare_digest(expected_sig, sig_header):
            logger.warning("[BRI Webhook] Signature tidak valid")
            raise HTTPException(403, "Invalid BRI signature")

    try:
        payload = json.loads(raw_body)
    except Exception:
        raise HTTPException(400, "Invalid JSON payload")

    # BRI BRIVA payload: {"keterangan": "INV-2026-04-0001", "amount": "150000", ...}
    invoice_number = (
        payload.get("keterangan")
        or payload.get("description")
        or payload.get("FreeText1")
        or ""
    ).strip()
    amount_str = str(payload.get("amount", "0"))
    try:
        amount = int(float(amount_str))
    except Exception:
        amount = 0

    if not invoice_number:
        return {"message": "no invoice number in payload"}

    inv = await db.invoices.find_one({
        "invoice_number": invoice_number,
        "status": {"$in": ["unpaid", "overdue"]},
    })
    if not inv:
        logger.warning(f"[BRI] Tidak ada invoice: {invoice_number}")
        return {"message": "invoice not found"}

    invoice_id = inv["id"]
    await db.invoices.update_one(
        {"id": invoice_id},
        {"$set": {
            "status": "paid",
            "paid_at": _now(),
            "payment_method": "bri_briva",
            "paid_notes": f"Auto-paid via BRI BRIVA (amount: {amount})",
        }}
    )
    await _after_paid_actions(invoice_id, db)
    background_tasks.add_task(_bg_send_whatsapp_paid, invoice_id)
    logger.info(f"[BRI] Invoice {invoice_number} LUNAS via BRI BRIVA (Rp{amount})")
    return {"message": "00", "status": "success"}


# ══════════════════════════════════════════════════════════════════════════════
# MIKROTIK DISCONNECT / RECONNECT
# ══════════════════════════════════════════════════════════════════════════════

async def _toggle_mikrotik_user(db, invoice_id: str, action: str):
    """Helper: disable atau enable user MikroTik berdasarkan invoice."""
    inv = await db.invoices.find_one({"id": invoice_id})
    if not inv:
        raise HTTPException(404, "Invoice tidak ditemukan")
    customer = await db.customers.find_one({"id": inv["customer_id"]})
    if not customer:
        raise HTTPException(404, "Customer tidak ditemukan")
    device = await db.devices.find_one({"id": customer.get("device_id", "")})
    if not device:
        raise HTTPException(404, "Device tidak ditemukan")

    from mikrotik_api import get_api_client
    mt = get_api_client(device)
    username = customer.get("username", "")
    svc = customer.get("service_type", "pppoe")
    try:
        if action == "disable":
            if svc == "pppoe":
                await mt.disable_pppoe_user(username)
            else:
                await mt.disable_hotspot_user(username)
        else:
            if svc == "pppoe":
                await mt.enable_pppoe_user(username)
            else:
                await mt.enable_hotspot_user(username)
    except Exception as e:
        raise HTTPException(503, f"Gagal {action} user MikroTik: {e}")
    return username


@router.post("/invoices/{invoice_id}/disable-user")
async def disable_user(invoice_id: str, user=Depends(require_write)):
    """Disable user PPPoE/Hotspot di MikroTik (putus koneksi) + kick active session."""
    db = get_db()
    inv = await db.invoices.find_one({"id": invoice_id})
    if not inv:
        raise HTTPException(404, "Invoice tidak ditemukan")
    customer = await db.customers.find_one({"id": inv["customer_id"]})
    if not customer:
        raise HTTPException(404, "Customer tidak ditemukan")
    device = await db.devices.find_one({"id": customer.get("device_id", "")})
    if not device:
        raise HTTPException(404, "Device tidak ditemukan")

    from mikrotik_api import get_api_client
    mt = get_api_client(device)
    username = customer.get("username", "")
    svc = customer.get("service_type", "pppoe")
    try:
        if svc == "pppoe":
            await mt.disable_pppoe_user(username)
            try:
                await mt.remove_pppoe_active_session(username)
            except Exception:
                pass
        else:
            await mt.disable_hotspot_user(username)
            try:
                if hasattr(mt, "remove_hotspot_active_session"):
                    await mt.remove_hotspot_active_session(username)
            except Exception:
                pass
    except Exception as e:
        raise HTTPException(503, f"Gagal disable user MikroTik: {e}")

    await db.invoices.update_one({"id": invoice_id}, {"$set": {"mt_disabled": True}})
    return {"message": f"User '{username}' berhasil di-disable dan active session dihapus"}


@router.post("/invoices/{invoice_id}/enable-user")
async def enable_user(invoice_id: str, user=Depends(require_write)):
    """Enable kembali user PPPoE/Hotspot di MikroTik."""
    db = get_db()
    username = await _toggle_mikrotik_user(db, invoice_id, "enable")
    await db.invoices.update_one({"id": invoice_id}, {"$set": {"mt_disabled": False}})
    return {"message": f"User '{username}' berhasil di-enable di MikroTik"}


@router.post("/invoices/sync-status")
async def sync_mikrotik_status(
    action: str = Query(...),  # "disable" atau "enable"
    status_filter: str = Query("overdue"),  # filter invoice: overdue, unpaid
    user=Depends(require_admin),
):
    """
    Bulk disable/enable user MikroTik berdasarkan status invoice.
    action=disable: putus semua yang overdue
    action=enable: sambungkan kembali semua yang sudah lunas
    """
    if action not in ("disable", "enable"):
        raise HTTPException(400, "action harus 'disable' atau 'enable'")

    db = get_db()
    from mikrotik_api import get_api_client

    if action == "disable":
        q = {"status": status_filter}
    else:
        # Hanya enable invoice bulan berjalan agar tidak meng-enable pelanggan yang sudah keluar
        from datetime import date as _date
        _today = _date.today()
        _period_prefix = f"{_today.year}-{_today.month:02d}"
        q = {"status": "paid", "period_start": {"$regex": f"^{_period_prefix}"}}
    invoices = await db.invoices.find(q).to_list(5000)

    success, failed, skipped = 0, 0, 0
    errors = []

    for inv in invoices:
        customer = await db.customers.find_one({"id": inv.get("customer_id", "")})
        if not customer:
            skipped += 1
            continue
        device = await db.devices.find_one({"id": customer.get("device_id", "")})
        if not device:
            skipped += 1
            continue
        # FIX B5: Skip isolir jika masih ada Janji Bayar aktif
        if action == "disable":
            _promise = inv.get("promise_date")
            if _promise:
                try:
                    _pd_val = date.fromisoformat(_promise)
                    if _pd_val >= date.today():
                        skipped += 1
                        logger.info(
                            f"[SyncStatus] Skip isolir '{customer.get('name')}' - Janji Bayar hingga {_promise}"
                        )
                        continue
                except (ValueError, TypeError):
                    pass
        try:
            mt = get_api_client(device)
            username = customer.get("username", "")
            svc = customer.get("service_type", "pppoe")
            if action == "disable":
                if svc == "pppoe":
                    await mt.disable_pppoe_user(username)
                else:
                    await mt.disable_hotspot_user(username)
                await db.invoices.update_one({"id": inv["id"]}, {"$set": {"mt_disabled": True}})
            else:
                if svc == "pppoe":
                    await mt.enable_pppoe_user(username)
                else:
                    await mt.enable_hotspot_user(username)
                await db.invoices.update_one({"id": inv["id"]}, {"$set": {"mt_disabled": False}})
            success += 1
        except Exception as e:
            failed += 1
            errors.append(f"{customer.get('name', '?')}: {e}")

    return {
        "message": f"Sync selesai: {success} berhasil, {failed} gagal, {skipped} dilewati",
        "success": success, "failed": failed, "skipped": skipped,
        "errors": errors[:20],
    }


# ══════════════════════════════════════════════════════════════════════════════
# MONTHLY SUMMARY (untuk grafik tren pendapatan)
# ══════════════════════════════════════════════════════════════════════════════

@router.get("/monthly-summary")
async def monthly_summary(
    months: int = Query(6),   # jumlah bulan ke belakang
    device_id: str = Query(""),
    user=Depends(get_current_user),
):
    """Data tren pendapatan N bulan terakhir untuk grafik bar/line chart."""
    from dateutil.relativedelta import relativedelta  # pip install python-dateutil
    db = get_db()
    today = date.today()
    result = []

    customer_ids = None
    if device_id:
        customers = await db.customers.find({"device_id": device_id}, {"id": 1}).to_list(None)
        customer_ids = [c["id"] for c in customers]

    for i in range(months - 1, -1, -1):
        d = today - relativedelta(months=i)
        prefix = f"{d.year}-{d.month:02d}"
        
        q_inv = {"period_start": {"$regex": f"^{prefix}"}}
        if customer_ids is not None:
            q_inv["customer_id"] = {"$in": customer_ids}
            
        inv_month = await db.invoices.find(
            q_inv, {"_id": 0}
        ).to_list(5000)

        paid = [x for x in inv_month if x.get("status") == "paid"]
        unpaid = [x for x in inv_month if x.get("status") in ("unpaid", "overdue")]
        result.append({
            "month": d.month,
            "year": d.year,
            "label": d.strftime("%b %Y"),
            "total": sum(x.get("total", 0) for x in inv_month),
            "paid": sum(x.get("total", 0) for x in paid),
            "unpaid": sum(x.get("total", 0) for x in unpaid),
            "count": len(inv_month),
            "paid_count": len(paid),
        })
    return result


# ── WhatsApp link helper ──────────────────────────────────────────────────────

@router.get("/invoices/{invoice_id}/whatsapp-link")
async def get_whatsapp_link(invoice_id: str, user=Depends(get_current_user)):
    """Generate link wa.me dengan template pesan tagihan."""
    import urllib.parse
    db = get_db()
    inv = await db.invoices.find_one({"id": invoice_id}, {"_id": 0})
    if not inv:
        raise HTTPException(404, "Invoice tidak ditemukan")

    customer = await db.customers.find_one({"id": inv["customer_id"]}, {"_id": 0}) or {}
    pkg = await db.billing_packages.find_one({"id": inv["package_id"]}, {"_id": 0}) or {}

    phone = customer.get("phone", "").strip().replace(" ", "").replace("-", "")
    if not phone:
        raise HTTPException(400, "Nomor telepon pelanggan belum diisi")

    # Normalize: 08xx → 628xx
    if phone.startswith("0"):
        phone = "62" + phone[1:]
    elif not phone.startswith("62"):
        phone = "62" + phone

    name = customer.get("name", "Pelanggan")
    invoice_no = inv.get("invoice_number", "")
    total = _rupiah(inv.get("total", 0))
    due = _dtfmt(inv.get("due_date", ""))
    pkg_name = pkg.get("name", "")
    period = f"{_dtfmt(inv.get('period_start',''))} s/d {_dtfmt(inv.get('period_end',''))}"

    message = (
        f"Yth. {name},\n\n"
        f"Tagihan internet Anda:\n"
        f"No. Invoice : {invoice_no}\n"
        f"Paket       : {pkg_name}\n"
        f"Periode     : {period}\n"
        f"Total       : {total}\n"
        f"Jatuh Tempo : {due}\n\n"
        f"Mohon segera melakukan pembayaran. Terima kasih 🙏"
    )

    link = f"https://wa.me/{phone}?text={urllib.parse.quote(message)}"
    return {"link": link, "phone": phone}

@webhook_router.get("/hotspot-public-config")
async def get_hotspot_public_config():
    """
    Endpoint PUBLIK untuk Captive Portal MikroTik (tanpa auth).
    [HOTFIX 2026-04-11] Baca dari hotspot_settings agar payment_enabled,
    bank_info, dan branding portal tersinkron dengan konfigurasi admin hotspot.
    Fallback ke billing_packages jika hotspot_settings.packages kosong.
    """
    db = get_db()

    # 1. Baca hotspot_settings — sumber kebenaran untuk payment & branding
    hs = await db.hotspot_settings.find_one({}, {"_id": 0}) or {}

    # WA Number: prioritas dari hotspot_settings
    wa_number = (hs.get("wa_number") or "").strip()
    if not wa_number:
        # Fallback ke billing_settings jika hotspot_settings belum punya WA
        bs = await fetch_billing_settings(db, device_id)
        wa_number = (bs.get("whatsapp") or bs.get("phone") or "6282228304543").strip()

    # 3. Payment info dari hotspot_settings
    payment_enabled = hs.get("payment_enabled", False)
    bank_info = None
    if payment_enabled:
        bank_info = {
            "bank_name":      hs.get("bank_name", ""),
            "account_number": hs.get("bank_account_number", ""),
            "account_name":   hs.get("bank_account_name", ""),
        }
        # Nonaktifkan jika rekening belum dikonfigurasi
        if not bank_info["account_number"]:
            payment_enabled = False
            bank_info = None

    # 4. Packages: Selalu ambil dari billing_packages sebagai sumber kebenaran (source of truth) untuk properti paket (seperti price dan profile)
    pkgs_cursor = db.billing_packages.find(
        {"service_type": {"$in": ["hotspot", "both"]}, "active": {"$ne": False}}
    )
    all_hotspot_pkgs = await pkgs_cursor.to_list(length=100)
    
    # Buat lookup table untuk mengisi ulang (enrich) properti yang hilang
    bp_dict = {p.get("name"): p for p in all_hotspot_pkgs if p.get("name")}

    hs_packages = hs.get("packages", [])
    packages = []
    
    # Jika frontend telah menyimpan filter paket ke hotspot_settings, gunakan urutan tersebut namun lengkapi propertinya
    if hs_packages:
        for hp in hs_packages:
            name = hp.get("name")
            if not name: continue
            bp = bp_dict.get(name) or {}
            packages.append({
                "name":         name,
                "price":        hp.get("price") if hp.get("price") is not None else bp.get("price", 0),
                "uptime_limit": hp.get("uptime_limit") or bp.get("uptime_limit", ""),
                "validity":     hp.get("validity") or bp.get("validity", ""),
                "profile":      hp.get("profile") or bp.get("profile_name") or bp.get("profile") or bp.get("hotspot_profile") or name
            })
    else:
        # Fallback semua paket aktif
        for p in all_hotspot_pkgs:
            packages.append({
                "name":         p.get("name"),
                "price":        p.get("price", 0),
                "uptime_limit": p.get("uptime_limit", ""),
                "validity":     p.get("validity", ""),
                "profile":      p.get("profile_name") or p.get("profile") or p.get("hotspot_profile") or p.get("name", "default")
            })

    return {
        "wa_number":               wa_number,
        "packages":                packages or [],
        "qris_image_url":          hs.get("qris_image_url", ""),
        "payment_enabled":         payment_enabled,
        "bank_info":               bank_info,
        "payment_timeout_minutes": hs.get("payment_timeout_minutes", 60),
        "portal_title":            hs.get("portal_title", ""),
        "portal_subtitle":         hs.get("portal_subtitle", ""),
        "portal_color":            hs.get("portal_color", ""),
    }


# ── Hotspot Voucher Orders (dari AI CS WhatsApp) ─────────────────────────────

@router.get("/voucher-orders")
async def list_voucher_orders(
    status: str = Query(""),    # "" | "unpaid" | "paid" | "overdue"
    search: str = Query(""),
    page: int = Query(1),
    limit: int = Query(20),
    user=Depends(get_current_user),
):
    """List semua pesanan voucher hotspot dari AI CS WhatsApp (collection hotspot_invoices)."""
    db = get_db()
    now_iso = datetime.now(timezone.utc).isoformat()

    # ── Catatan: cleanup invoice expire kini dihandle oleh billing_scheduler_loop ──
    # ── (run_hotspot_invoice_cleanup) — endpoint GET tidak boleh menghapus data ────

    # ── Ambil data ───────────────────────────────────────────────────────────
    q = {}
    if status:
        if "," in status:
            q["status"] = {"$in": status.split(",")}
        else:
            q["status"] = status

    orders = await db.hotspot_invoices.find(q, {"_id": 0}).sort("created_at", -1).to_list(5000)

    result = []
    for o in orders:
        if search:
            s = search.lower()
            if not (s in o.get("customer_name", "").lower()
                    or s in o.get("customer_phone", "").lower()
                    or s in o.get("invoice_number", "").lower()):
                continue
        result.append(o)

    total_count = len(result)
    skip_n = (page - 1) * limit
    paginated = result[skip_n: skip_n + limit]

    return {
        "data": paginated,
        "total": total_count,
        "page": page,
        "pages": max(1, (total_count + limit - 1) // limit),
    }


@router.patch("/voucher-orders/{order_id}/pay")
async def mark_voucher_paid(order_id: str, data: dict, background_tasks: BackgroundTasks, user=Depends(get_current_user)):
    """Tandai voucher order sebagai lunas secara manual (hanya jika masih unpaid)."""
    db = get_db()
    now = _now()
    method = data.get("payment_method", "cash")

    # Cek apakah invoice masih valid (unpaid) — tolak jika sudah expired/overdue
    inv = await db.hotspot_invoices.find_one({"id": order_id}, {"_id": 0, "status": 1, "due_date": 1})
    if not inv:
        raise HTTPException(404, "Voucher order tidak ditemukan")
    if inv.get("status") == "paid":
        raise HTTPException(400, "Invoice ini sudah lunas")
    if inv.get("status") == "overdue" or inv.get("due_date", "") < now:
        # Invoice kedaluwarsa — hapus saja daripada dilunasi
        await db.hotspot_invoices.delete_one({"id": order_id})
        raise HTTPException(400, "Invoice ini sudah kedaluwarsa dan telah dihapus")

    res = await db.hotspot_invoices.update_one(
        {"id": order_id},
        {"$set": {"status": "paid", "paid_at": now, "payment_method": method, "updated_at": now}}
    )
    if res.matched_count == 0:
        raise HTTPException(404, "Voucher order tidak ditemukan")
        
    # Kirim WA notifikasi voucher lunas
    background_tasks.add_task(_bg_send_whatsapp_paid, order_id)
        
    return {"message": "Voucher order ditandai lunas, memproses Notifikasi & Voucher."}



@router.delete("/voucher-orders/{order_id}")
async def delete_voucher_order(order_id: str, user=Depends(get_current_user)):
    """Hapus voucher order."""
    db = get_db()
    res = await db.hotspot_invoices.delete_one({"id": order_id})
    if res.deleted_count == 0:
        raise HTTPException(404, "Voucher order tidak ditemukan")
    return {"message": "Voucher order dihapus"}


# ══════════════════════════════════════════════════════════════════════════════
# UPGRADE PAKET + PRORATA
# ══════════════════════════════════════════════════════════════════════════════

class PackageUpgradeRequest(BaseModel):
    new_package_id: str
    create_adjustment_invoice: bool = True   # Buat invoice adjustment jika ada selisih?


@router.post("/customers/{customer_id}/upgrade-package")
async def upgrade_customer_package(
    customer_id: str,
    data: PackageUpgradeRequest,
    background_tasks: BackgroundTasks,
    user=Depends(require_write),
):
    """
    Upgrade/downgrade paket pelanggan PPPoE di tengah periode aktif.

    Alur:
      1. Hitung sisa hari dalam periode aktif
      2. Hitung selisih harga (prorata)
      3. Buat invoice adjustment jika ada selisih (opsional)
      4. Update package_id pelanggan di DB
      5. Sinkronkan profile MikroTik
    """
    import calendar as cal_mod
    db = get_db()

    customer = await db.customers.find_one({"id": customer_id})
    if not customer:
        raise HTTPException(404, "Customer tidak ditemukan")
    if customer.get("service_type", "pppoe") != "pppoe":
        raise HTTPException(400, "Upgrade paket hanya untuk pelanggan PPPoE")

    old_pkg_id = customer.get("package_id", "")
    if old_pkg_id == data.new_package_id:
        raise HTTPException(400, "Paket tujuan sama dengan paket aktif")

    old_pkg = await db.billing_packages.find_one({"id": old_pkg_id}) if old_pkg_id else None
    new_pkg = await db.billing_packages.find_one({"id": data.new_package_id})
    if not new_pkg:
        raise HTTPException(404, "Paket tujuan tidak ditemukan")

    # ── Cari invoice aktif bulan ini ──────────────────────────────────────────
    today = date.today()
    period_prefix = f"{today.year}-{today.month:02d}"
    active_inv = await db.invoices.find_one({
        "customer_id": customer_id,
        "period_start": {"$regex": f"^{period_prefix}"},
    })

    adjustment_invoice = None

    if data.create_adjustment_invoice and active_inv and old_pkg:
        # Hitung sisa hari dalam bulan berjalan
        _, days_in_month = cal_mod.monthrange(today.year, today.month)
        remaining_days = days_in_month - today.day + 1

        old_daily = old_pkg.get("price", 0) / days_in_month
        new_daily = new_pkg.get("price", 0) / days_in_month
        diff_amount = round((new_daily - old_daily) * remaining_days)

        if abs(diff_amount) >= 100:   # Minimal selisih Rp 100 agar worth dibuat
            adj_count = await db.invoices.count_documents({
                "period_start": {"$regex": f"^{period_prefix}"}
            })
            unique_code = await _generate_unique_code(db, customer_id, abs(diff_amount), period_prefix)
            adj_total = abs(diff_amount) + unique_code

            period_end_day = days_in_month
            adj_doc = {
                "id": str(uuid.uuid4()),
                "invoice_number": _invoice_num(adj_count + 1) + "-ADJ",
                "customer_id": customer_id,
                "package_id": data.new_package_id,
                "amount": abs(diff_amount),
                "discount": 0,
                "unique_code": unique_code,
                "total": adj_total if diff_amount > 0 else -abs(diff_amount),
                "period_start": today.isoformat(),
                "period_end": f"{today.year}-{today.month:02d}-{period_end_day:02d}",
                "due_date": f"{today.year}-{today.month:02d}-{period_end_day:02d}",
                "status": "unpaid" if diff_amount > 0 else "paid",
                "notes": (
                    f"Adjustment upgrade paket: {old_pkg.get('name','?')} → {new_pkg.get('name','?')} "
                    f"({remaining_days} hari sisa)"
                ),
                "paid_at": _now() if diff_amount <= 0 else None,
                "payment_method": "adjustment" if diff_amount <= 0 else None,
                "created_at": _now(),
                "is_adjustment": True,
            }
            await db.invoices.insert_one(adj_doc)
            adj_doc.pop("_id", None)
            adjustment_invoice = adj_doc

            if diff_amount > 0:
                # Kirim WA tagihan adjustment
                background_tasks.add_task(_bg_send_whatsapp_reminders, [adj_doc["id"]])

    # ── Update customer package_id ─────────────────────────────────────────────
    await db.customers.update_one(
        {"id": customer_id},
        {"$set": {"package_id": data.new_package_id, "updated_at": _now()}}
    )

    # ── Sinkronkan profile MikroTik ───────────────────────────────────────────
    mt_msg = ""
    try:
        from mikrotik_api import get_api_client
        device = await db.devices.find_one({"id": customer.get("device_id", "")})
        if device:
            mt = get_api_client(device)
            username = customer.get("username", "")
            new_profile = new_pkg.get("profile_name") or new_pkg.get("name", "")
            # Cari PPPoE secret di MikroTik
            secrets = await mt.list_pppoe_secrets()
            secret_entry = next((s for s in secrets if s.get("name") == username), None)
            if secret_entry:
                await mt.update_pppoe_secret(secret_entry[".id"], {"profile": new_profile})
                # Kick active session agar profile baru langsung berlaku
                try:
                    await mt.remove_pppoe_active_session(username)
                except Exception:
                    pass
                mt_msg = f" | Profile MikroTik diperbarui ke '{new_profile}' dan sesi di-refresh"
    except Exception as e:
        mt_msg = f" | Gagal update MikroTik: {e}"
        logger.error(f"[UpgradePackage] Gagal sinkronisasi MikroTik untuk {customer_id}: {e}")

    logger.info(
        f"[UpgradePackage] Customer '{customer.get('name')}' upgrade: "
        f"{old_pkg.get('name','?') if old_pkg else '?'} → {new_pkg.get('name')}"
    )

    return {
        "message": f"Paket berhasil diubah ke '{new_pkg.get('name')}'{mt_msg}",
        "old_package": old_pkg.get("name") if old_pkg else None,
        "new_package": new_pkg.get("name"),
        "adjustment_invoice": adjustment_invoice,
    }


# ── Dynamic Bandwidth Endpoints ───────────────────────────────────────────────

class SpeedBoosterRequest(BaseModel):
    duration_hours: int = 0  # 0 = use default from package

@router.post("/customers/{customer_id}/speed-booster")
async def activate_speed_booster(customer_id: str, req: SpeedBoosterRequest, background_tasks: BackgroundTasks, user=Depends(require_write)):
    """
    Aktifkan speed booster on-demand untuk pelanggan via Admin atau bot WhatsApp.
    
    Aturan:
    - Booster dan Night Mode SALING EKSKLUSIF — tidak bisa jalan bersamaan
    - Jika Night Mode sedang berlaku, Booster ditolak
    - Perubahan bandwidth dikirim via CoA TANPA memutuskan koneksi user
    - Sync hanya untuk pelanggan ini saja (targeted), tidak mempengaruhi pelanggan lain
    - Setelah durasi habis, rate otomatis kembali ke normal (scheduler menangani)
    """
    db = get_db()
    c = await db.customers.find_one({"id": customer_id})
    if not c:
        raise HTTPException(404, "Pelanggan tidak ditemukan")
    if not c.get("active"):
        raise HTTPException(400, "Pelanggan sedang tidak aktif/terisolir")

    pkg = await db.billing_packages.find_one({"id": c.get("package_id")})
    if not pkg or not pkg.get("boost_rate_limit"):
        raise HTTPException(400, "Paket pelanggan ini tidak mendukung Speed Booster")

    # ── Cek Mutual Exclusivity: Night Mode vs Booster ──
    # Jika Night Mode sedang berlaku, Booster TIDAK bisa diaktifkan
    if pkg.get("day_night_enabled"):
        from datetime import datetime as _dt
        now_time_str = _dt.now().strftime("%H:%M")
        n_start = pkg.get("night_start", "22:00")
        n_end   = pkg.get("night_end",   "06:00")
        is_night = False
        if n_start > n_end:
            # Overnight (misal 22:00 - 06:00)
            is_night = now_time_str >= n_start or now_time_str < n_end
        else:
            is_night = n_start <= now_time_str < n_end
        if is_night:
            raise HTTPException(400,
                f"Night Mode sedang aktif ({n_start}\u2013{n_end}). "
                "Booster tidak dapat dijalankan bersamaan dengan Night Mode. "
                "Aktifkan Booster di luar jam Night Mode."
            )

    dur = req.duration_hours if req.duration_hours > 0 else int(pkg.get("boost_duration_hours", 24))
    from datetime import timedelta
    exp_at = (datetime.now(timezone.utc) + timedelta(hours=dur)).isoformat()
    boost_rate = pkg.get("boost_rate_limit", "")

    # Simpan status booster + reset current_rate_limit agar scheduler re-evaluasi
    await db.customers.update_one(
        {"id": customer_id},
        {"$set": {
            "booster_active": True,
            "booster_expires_at": exp_at,
            "boost_rate_limit": boost_rate,  # Cache di customer untuk scheduler
            "current_rate_limit": None,       # Force re-evaluasi
        }}
    )

    logger.info(f"[Booster] User '{c.get('username')}' mengaktifkan speed booster {boost_rate} selama {dur} jam")

    # ── Trigger immediate BW sync HANYA untuk pelanggan ini (targeted, no global sync) ──
    # CoA dikirim tanpa putus koneksi. Tidak mempengaruhi pelanggan lain.
    async def _trigger_booster_sync(cust_id: str):
        try:
            from services.bandwidth_scheduler import run_day_night_and_booster_sync
            await run_day_night_and_booster_sync(customer_id=cust_id)
            logger.info(f"[Booster] BW sync targeted selesai untuk pelanggan {cust_id}")
        except Exception as e:
            logger.error(f"[Booster] Gagal trigger BW sync: {e}")

    background_tasks.add_task(_trigger_booster_sync, customer_id)

    return {
        "message": f"Speed Booster diaktifkan selama {dur} jam. Kecepatan akan naik ke {boost_rate} dalam hitungan detik (tanpa putus koneksi).",
        "expires_at": exp_at,
        "boost_rate": boost_rate,
    }


@router.get("/customers/{customer_id}/bandwidth-status")
async def get_bandwidth_status(customer_id: str, user=Depends(get_current_user)):
    """Cek status bandwidth saat ini: FUP limit, usage, dan mode yang aktif (Day/Night/Booster)."""
    db = get_db()
    c = await db.customers.find_one({"id": customer_id})
    if not c:
        raise HTTPException(404, "Pelanggan tidak ditemukan")
        
    pkg = await db.billing_packages.find_one({"id": c.get("package_id")})
    if not pkg:
        return {"error": "Paket tidak ditemukan"}
        
    used_bytes = c.get("fup_bytes_used", 0)
    used_gb = used_bytes / 1_000_000_000
    
    status = {
        "current_rate_limit": c.get("current_rate_limit", f"{pkg.get('speed_up', '')}/{pkg.get('speed_down', '')}"),
        "fup": {
            "enabled": pkg.get("fup_enabled", False),
            "active": c.get("fup_active", False),
            "limit_gb": pkg.get("fup_limit_gb", 0),
            "used_gb": round(used_gb, 2),
            "rate_limit": pkg.get("fup_rate_limit")
        },
        "night_mode": {
            "enabled": pkg.get("day_night_enabled", False),
            "start": pkg.get("night_start"),
            "end": pkg.get("night_end"),
            "rate_limit": pkg.get("night_rate_limit")
        },
        "booster": {
            "active": c.get("booster_active", False),
            "expires_at": c.get("booster_expires_at"),
            "rate_limit": pkg.get("boost_rate_limit")
        }
    }
    
    return status


# ══════════════════════════════════════════════════════════════════════════════
# PUSH NOTIFICATION — Siaran Manual ke Semua Pelanggan
# ══════════════════════════════════════════════════════════════════════════════

@router.post("/push/network-error")
async def push_network_error_broadcast(
    background_tasks: BackgroundTasks,
    user=Depends(require_admin),
):
    """
    Kirim Push Notification 'Gangguan Jaringan' ke SEMUA pelanggan yang
    terdaftar di Aplikasi Android (memiliki FCM token).
    Template pesan diambil dari billing_settings.fcm_template_network_error.
    """
    db = get_db()

    settings = await fetch_billing_settings(db, None)
    template = settings.get(
        "fcm_template_network_error",
        "Yth {customer_name}, terdapat gangguan jaringan pada sistem kami. "
        "Mohon maaf atas ketidaknyamanan ini."
    )

    # Ambil semua pelanggan yang punya fcm_token terdaftar
    customers_with_token = await db.customers.find(
        {"fcm_token": {"$exists": True, "$ne": None, "$ne": ""}},
        {"_id": 0, "name": 1, "fcm_token": 1}
    ).to_list(5000)

    if not customers_with_token:
        # Kembalikan 200 dengan ok:false agar frontend bisa tampilkan pesan informatif
        # (bukan 422 yang terlihat sebagai error fatal)
        return {
            "ok": False,
            "message": "Belum ada pelanggan yang menginstal Aplikasi Android. "
                       "FCM token akan tersimpan otomatis setelah pelanggan login via APK."
        }

    async def _do_broadcast():
        try:
            from services.firebase_service import send_push_notification
        except ImportError:
            logger.warning("[NetworkErrorPush] firebase-admin tidak tersedia, push dibatalkan.")
            return

        sent = 0
        for c in customers_with_token:
            token = c.get("fcm_token")
            if not token:
                continue
            try:
                body = template.replace("{customer_name}", c.get("name", "Pelanggan"))
                success = await send_push_notification(
                    [token],
                    "⚠️ Pemberitahuan Gangguan Jaringan",
                    body
                )
                if success:
                    sent += 1
                # Jeda kecil agar tidak membanjiri Firebase
                await asyncio.sleep(0.05)
            except Exception as e:
                logger.warning(f"[NetworkErrorPush] Gagal kirim ke {c.get('name')}: {e}")

        logger.info(f"[NetworkErrorPush] Broadcast selesai: {sent}/{len(customers_with_token)} notifikasi terkirim.")

    background_tasks.add_task(_do_broadcast)

    return {
        "ok": True,
        "message": f"Push notification gangguan jaringan sedang dikirim ke {len(customers_with_token)} perangkat di latar belakang."
    }





# ══════════════════════════════════════════════════════════════════════════════
# PUSH NOTIFICATION — Trigger Manual Reminder (untuk testing & darurat)
# ══════════════════════════════════════════════════════════════════════════════

@router.post("/trigger-reminders")
async def trigger_reminders_manual(user=Depends(require_admin)):
    """
    Jalankan semua reminder tagihan SEKARANG tanpa menunggu jadwal otomatis.
    Berguna untuk testing atau kirim reminder darurat di luar jadwal.
    """
    from services.billing_scheduler import process_reminders, run_auto_overdue
    await run_auto_overdue()
    await process_reminders()
    return {
        "ok": True,
        "message": "Reminder H-3/H-2/H-1/Due/Overdue telah dijalankan secara manual."
    }


@router.post("/push/customer/{customer_id}")
async def push_to_customer(
    customer_id: str,
    background_tasks: BackgroundTasks,
    user=Depends(require_admin),
):
    """
    Kirim Push Notification test ke satu pelanggan spesifik.
    Berguna untuk verifikasi FCM token pelanggan tertentu.
    """
    db = get_db()
    customer = await db.customers.find_one({"id": customer_id}, {"_id": 0, "name": 1, "fcm_token": 1})
    if not customer:
        raise HTTPException(404, "Pelanggan tidak ditemukan")

    fcm_token = customer.get("fcm_token")
    if not fcm_token:
        return {
            "ok": False,
            "message": f"Pelanggan '{customer.get('name')}' belum terdaftar di Aplikasi Android (tidak ada FCM token)."
        }

    async def _send():
        try:
            from services.firebase_service import send_push_notification
            success = await send_push_notification(
                [fcm_token],
                "🔔 Test Notifikasi NOC Sentinel",
                f"Halo {customer.get('name', 'Pelanggan')}, notifikasi push dari NOC Sentinel berhasil diterima!"
            )
            status = "berhasil" if success else "GAGAL (token mungkin tidak valid)"
            logger.info(f"[PushTest] Notifikasi test ke '{customer.get('name')}': {status}")
        except Exception as e:
            logger.error(f"[PushTest] Error: {e}")

    background_tasks.add_task(_send)
    return {
        "ok": True,
        "customer": customer.get("name"),
        "message": f"Push notification test sedang dikirim ke '{customer.get('name')}'."
    }
