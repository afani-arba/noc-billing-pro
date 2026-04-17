from fastapi import APIRouter, Depends, HTTPException, Query
from core.db import get_db
from core.auth import get_current_user, require_write
import logging

router = APIRouter(tags=["pppoe-monitoring"])
logger = logging.getLogger(__name__)


def _normalize_session(raw: dict, dev: dict) -> dict:
    """
    Normalisasi field dari MikroTik /ppp/active ke format yang diharapkan frontend.

    MikroTik mengembalikan field dengan tanda hubung (caller-id, tx-byte, dst)
    namun kita expose ke frontend dengan underscore agar konsisten dengan Python.
    """
    return {
        # Identitas user
        "name":          raw.get("name", ""),
        "customer_name": raw.get("name", ""),   # akan di-enrich dari billing DB jika ada
        "is_radius":     raw.get("radius", "false") not in (False, "false", "no", None, ""),
        "password":      "",                     # tidak tersedia di /ppp/active, harus dari secret
        # Jaringan
        "address":       raw.get("address", ""),
        "caller_id":     raw.get("caller-id", ""),
        # Uptime
        "uptime":        raw.get("uptime", ""),
        # Bytes (total data)
        "tx_byte":       int(raw.get("tx-byte", 0) or 0),
        "rx_byte":       int(raw.get("rx-byte", 0) or 0),
        # Bandwidth realtime (bps)
        "tx_bps":        int(raw.get("tx-bps", 0) or 0),
        "rx_bps":        int(raw.get("rx-bps", 0) or 0),
        # Info router
        "router_id":     dev.get("id", ""),
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
    db = get_db()
    # Device disimpan dengan field 'device_type' bukan 'type'
    devices = await db.devices.find(
        {},
        {"id": 1, "name": 1, "api_mode": 1, "status": 1, "_id": 0}
    ).to_list(100)
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
                   Jika tidak diisi, return [] (tidak menampilkan semua device sekaligus
                   agar tidak membebani semua router).
    """
    if not router_id:
        # Bukan error, tapi memang sengaja dibatasi hanya per-device
        return []

    db = get_db()
    # Cari device berdasarkan 'id' (UUID) — tidak pakai filter type
    device = await db.devices.find_one({"id": router_id})
    if not device:
        raise HTTPException(404, f"Device dengan id '{router_id}' tidak ditemukan")

    try:
        from mikrotik_api import get_api_client
        mt = get_api_client(device)

        # list_pppoe_active() tersedia di semua class (REST & API Protocol)
        raw_list = await mt.list_pppoe_active()
        if not isinstance(raw_list, list):
            raw_list = []

        # Normalize semua entri
        result = [_normalize_session(r, device) for r in raw_list]

        # Enrich password dari ppp/secret jika tersedia (best-effort, tidak block jika gagal)
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
        logger.error(f"[pppoe-monitoring] Gagal query {device.get('name')}: {e}")
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

        # remove_pppoe_active_session tersedia di semua class
        removed = await mt.remove_pppoe_active_session(req.username)
        if removed == 0:
            # Coba alternatif: cari dengan list dan delete manual
            actives = await mt.list_pppoe_active()
            removed = 0
            for s in (actives or []):
                if s.get("name") == req.username:
                    mt_id = s.get(".id", "")
                    if mt_id:
                        try:
                            from mikrotik_api import get_api_client as _gac
                            # Panggil via client yang sama
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
