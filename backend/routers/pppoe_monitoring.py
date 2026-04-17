from fastapi import APIRouter, Depends, HTTPException, Query
from core.db import get_db
from core.auth import get_current_user, require_write, check_device_access
import logging
import time

router = APIRouter(tags=["pppoe-monitoring"])
logger = logging.getLogger(__name__)

# Cache traffic untuk menghitung BPS (Bandwidth)
# Format: { router_id: { interface_name: { "rx_byte": int, "tx_byte": int, "ts": float } } }
_TRAFFIC_CACHE = {}


def _normalize_session(raw: dict, dev: dict, ifaces_map: dict, router_id: str) -> dict:
    """
    Normalisasi field dari MikroTik /ppp/active ke format yang diharapkan frontend.
    Menambahkan data total bytes (rx_byte, tx_byte) dari /interface
    Menghitung bps berdasarkan _TRAFFIC_CACHE.
    """
    name = raw.get("name", "")
    
    # Cari interface pppoe
    # Interface name biasanya <pppoe-username>
    iface_name = f"<pppoe-{name}>"
    iface = ifaces_map.get(iface_name, {})
    
    # Ambil byte aktual dari interface kalau ada
    rx_byte = int(iface.get("rx-byte", raw.get("rx-byte", 0)) or 0)
    tx_byte = int(iface.get("tx-byte", raw.get("tx-byte", 0)) or 0)
    
    # Hitung bps
    now = time.time()
    rx_bps = 0
    tx_bps = 0
    
    if router_id not in _TRAFFIC_CACHE:
        _TRAFFIC_CACHE[router_id] = {}
        
    prev = _TRAFFIC_CACHE[router_id].get(iface_name)
    if prev:
        dt = now - prev["ts"]
        if dt > 0:
            rx_diff = rx_byte - prev["rx_byte"]
            tx_diff = tx_byte - prev["tx_byte"]
            # Cegah negatif (counter reset saat reconect)
            if rx_diff >= 0: rx_bps = int((rx_diff * 8) / dt)
            if tx_diff >= 0: tx_bps = int((tx_diff * 8) / dt)

    # Simpan state untuk tick selanjutnya
    _TRAFFIC_CACHE[router_id][iface_name] = {
        "rx_byte": rx_byte,
        "tx_byte": tx_byte,
        "ts": now
    }

    return {
        # Identitas user
        "name":          name,
        "customer_name": name,                   # akan di-enrich dari billing DB jika ada
        "is_radius":     raw.get("radius", "false") not in (False, "false", "no", None, ""),
        "password":      "",                     # tidak tersedia di /ppp/active, harus dari secret
        # Jaringan
        "address":       raw.get("address", ""),
        "caller_id":     raw.get("caller-id", ""),
        # Uptime
        "uptime":        raw.get("uptime", ""),
        # Bytes (total data)
        "tx_byte":       tx_byte,
        "rx_byte":       rx_byte,
        # Bandwidth realtime (bps)
        "tx_bps":        tx_bps,
        "rx_bps":        rx_bps,
        # Info router
        "router_id":     router_id,
        "router_name":   dev.get("name", "MikroTik"),
        # MikroTik internal id (untuk kick)
        "mt_id":         raw.get(".id", ""),
    }


@router.get("/pppoe-monitoring-routers")
async def get_monitoring_routers(user=Depends(get_current_user)):
    """
    Kembalikan daftar device MikroTik yang terdaftar di sistem.
    Digunakan frontend untuk mengisi dropdown router.
    """
    from core.auth import get_user_allowed_devices
    db = get_db()
    devices = await db.devices.find(
        {},
        {"id": 1, "name": 1, "api_mode": 1, "status": 1, "_id": 0}
    ).to_list(100)

    # ── RBAC: filter berdasarkan allowed_devices user ──────────────────────
    scope = get_user_allowed_devices(user)  # None = admin, list = allowed
    if scope is not None:
        devices = [d for d in devices if d.get("id") in scope]
    return devices


@router.get("/pppoe-active-monitoring")
async def get_pppoe_active(
    router_id: str = Query(None),
    user=Depends(get_current_user)
):
    """
    Ambil sesi PPPoE aktif secara real-time langsung dari MikroTik.
    Query param:
      router_id  — wajib diisi; ID device dari tabel devices.
    """
    if not router_id:
        return []

    # ── RBAC: cek apakah user memiliki akses ke router ini ────────────────
    if not check_device_access(user, router_id):
        raise HTTPException(403, "Anda tidak memiliki hak akses untuk memantau router ini")

    db = get_db()
    device = await db.devices.find_one({"id": router_id})
    if not device:
        raise HTTPException(404, f"Device dengan id '{router_id}' tidak ditemukan")

    try:
        from mikrotik_api import get_api_client
        mt = get_api_client(device)
        
        # 1. Ambil list active
        raw_list = await mt.list_pppoe_active()
        if not isinstance(raw_list, list):
            raw_list = []

        # 2. Ambil list interface untuk mendapatkan rx-byte dan tx-byte
        # Coba cara paling ringan dulu
        ifaces_map = {}
        if raw_list:
            try:
                ifaces = await mt._async_req("GET", "interface") \
                         if hasattr(mt, "_async_req") \
                         else await mt._async_req("GET", "/interface/print") # asumsi api protocol tidak digunakan, diganti to_thread kalau mikrotiklegacy
            except Exception:
                try:
                    import asyncio
                    ifaces = await asyncio.to_thread(mt._list_resource, "/interface")
                except Exception as e:
                    logger.debug(f"[pppoe-monitoring] Gagal fetch /interface: {e}")
                    ifaces = []

            for i in (ifaces if isinstance(ifaces, list) else []):
                ifaces_map[i.get("name", "")] = i
        
        # 3. Normalize semua entri (termasuk BPS)
        result = [_normalize_session(r, device, ifaces_map, router_id) for r in raw_list]

        # 4. Cleanup cache untuk username yang sudah disconnect 
        if router_id in _TRAFFIC_CACHE:
            active_names = {f"<pppoe-{r['name']}>" for r in raw_list}
            keys_to_del = [k for k in _TRAFFIC_CACHE[router_id] if k not in active_names]
            for k in keys_to_del:
                del _TRAFFIC_CACHE[router_id][k]

        # 5. Enrich password dari ppp/secret jika tersedia
        try:
            secrets = await mt.list_pppoe_secrets()
            if isinstance(secrets, list):
                secret_map = {s.get("name", ""): s for s in secrets}
                for session in result:
                    secret = secret_map.get(session["name"])
                    if secret:
                        session["password"] = secret.get("password", "")
        except Exception as e:
            logger.debug(f"[pppoe-monitoring] Gagal ambil secrets untuk enrich password {device.get('name')}: {e}")

        logger.info(f"[pppoe-monitoring] {device.get('name')}: {len(result)} sesi aktif")
        return result

    except Exception as e:
        logger.error(f"[pppoe-monitoring] Gagal query {str(e)}")
        raise HTTPException(500, f"Gagal mengambil data PPPoE dari router: {str(e)}")


from pydantic import BaseModel

class KickRequest(BaseModel):
    username: str
    router_id: str


@router.post("/pppoe-kick")
async def kick_pppoe_user(req: KickRequest, user=Depends(require_write)):
    """Putus (kick) koneksi PPPoE aktif berdasarkan username."""
    db = get_db()
    device = await db.devices.find_one({"id": req.router_id})
    if not device:
        raise HTTPException(404, "Router tidak ditemukan")

    try:
        from mikrotik_api import get_api_client
        mt = get_api_client(device)

        removed = await mt.remove_pppoe_active_session(req.username)
        if removed == 0:
            actives = await mt.list_pppoe_active()
            removed = 0
            for s in (actives or []):
                if s.get("name") == req.username:
                    mt_id = s.get(".id", "")
                    if mt_id:
                        try:
                            await mt._async_req("DELETE", f"ppp/active/{mt_id}") \
                                if hasattr(mt, "_async_req") else None
                            removed += 1
                        except Exception:
                            pass

        return {
            "status": "success",
            "message": f"Koneksi '{req.username}' berhasil diputus ({removed} sesi)",
            "removed": removed,
        }
    except Exception as e:
        logger.error(f"[pppoe-kick] Gagal kick '{req.username}': {e}")
        raise HTTPException(500, str(e))


@router.get("/pppoe-users")
async def get_pppoe_users(device_id: str, user=Depends(get_current_user)):
    db = get_db()
    device = await db.devices.find_one({"id": device_id})
    if not device:
        raise HTTPException(404, "Device tidak ditemukan")

    try:
        from mikrotik_api import get_api_client
        mt = get_api_client(device)
        return await mt.list_pppoe_secrets()
    except Exception as e:
        logger.error(f"[pppoe-users] Gagal: {e}")
        raise HTTPException(500, str(e))


@router.get("/pppoe-settings")
async def get_pppoe_settings(user=Depends(get_current_user)):
    db = get_db()
    settings = await db.settings.find_one({"_id": "pppoe_settings"})
    return settings or {}


class PppoeSettingsUpdate(BaseModel):
    pppoe_pool_name: str
    pppoe_profile_name: str
    pppoe_local_address: str
    dns1: str
    dns2: str


@router.post("/pppoe-setup-pool")
async def setup_pppoe_pool(req: PppoeSettingsUpdate, user=Depends(require_write)):
    db = get_db()
    await db.settings.update_one(
        {"_id": "pppoe_settings"},
        {"$set": req.model_dump()},
        upsert=True
    )
    return {"status": "success", "message": "Konfigurasi PPPoE berhasil disimpan."}
