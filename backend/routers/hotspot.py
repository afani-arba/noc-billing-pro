"""
Hotspot router: voucher management, sales tracking, RADIUS status, dan settings.
Endpoint prefix: /hotspot-*  (langsung di root /api)
"""
import uuid
import logging
import csv
import io
from datetime import datetime, timezone, timedelta
from typing import Optional, List
from fastapi import APIRouter, HTTPException, Depends, Query, UploadFile, File
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from core.db import get_db
from core.auth import (
    get_current_user, require_admin, require_write, require_enterprise,
    check_device_access, get_user_allowed_devices
)

router = APIRouter(tags=["hotspot"])

logger = logging.getLogger(__name__)


def _now():
    return datetime.now(timezone.utc).isoformat()


# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•
# HOTSPOT SETTINGS
# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•

class HotspotSettingsUpdate(BaseModel):
    wa_number: Optional[str] = None
    welcome_message: Optional[str] = None
    payment_enabled: Optional[bool] = None
    bank_name: Optional[str] = None
    bank_number: Optional[str] = None
    bank_account_name: Optional[str] = None
    packages: Optional[list] = None
    footer_text: Optional[str] = None
    portal_logo_url: Optional[str] = None
    portal_title: Optional[str] = None
    auto_wa_enabled: Optional[bool] = None
    # ── Payment Gateway Hotspot ──────────────────────────────────────────
    xendit_enabled: Optional[bool] = None
    xendit_secret_key: Optional[str] = None
    xendit_webhook_token: Optional[str] = None
    xendit_va_bank: Optional[str] = None
    midtrans_enabled: Optional[bool] = None
    midtrans_server_key: Optional[str] = None
    midtrans_client_key: Optional[str] = None
    midtrans_is_production: Optional[bool] = None
    active_payment_providers: Optional[list] = None  # ["xendit", "midtrans", "manual"]


@router.get("/hotspot-settings", dependencies=[Depends(require_enterprise)])
async def get_hotspot_settings(user=Depends(get_current_user)):
    db = get_db()
    settings = await db.hotspot_settings.find_one({}, {"_id": 0})
    if not settings:
        settings = {
            "wa_number": "",
            "welcome_message": "Selamat datang di Hotspot kami!",
            "payment_enabled": False,
            "bank_name": "",
            "bank_number": "",
            "bank_account_name": "",
            "packages": [],
            "footer_text": "",
            "portal_title": "Hotspot Login",
            "auto_wa_enabled": False,
        }
        await db.hotspot_settings.insert_one(settings)
    settings.pop("_id", None)
    return settings


@router.post("/hotspot-settings", dependencies=[Depends(require_enterprise)])
async def save_hotspot_settings(data: HotspotSettingsUpdate, user=Depends(require_write)):
    db = get_db()
    update_data = {k: v for k, v in data.dict().items() if v is not None}
    if not update_data:
        raise HTTPException(400, "Tidak ada data yang dikirim")
    await db.hotspot_settings.update_one({}, {"$set": update_data}, upsert=True)
    settings = await db.hotspot_settings.find_one({}, {"_id": 0})
    return settings or {}


# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•
# HOTSPOT VOUCHERS
# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•

class VoucherUpdate(BaseModel):
    password: Optional[str] = None
    profile: Optional[str] = None
    validity: Optional[str] = None
    price: Optional[float] = None


class VoucherTransfer(BaseModel):
    new_device_id: str


@router.get("/hotspot-vouchers", dependencies=[Depends(require_enterprise)])
async def list_hotspot_vouchers(
    search: str = Query(""),
    device_id: str = Query(""),
    status: str = Query(""),
    limit: int = Query(500),
    user=Depends(get_current_user),
):
    db = get_db()
    q = {}

    # ——— RBAC: filter berdasarkan allowed_devices user —————————————————————————————————————————————
    scope = get_user_allowed_devices(user)  # None = admin (semua)
    if scope is None:
        if device_id:
            q["device_id"] = device_id
    else:
        allowed = scope
        if device_id:
            allowed = [d for d in scope if d == device_id]
        if not allowed:
            return []
        q["device_id"] = {"$in": allowed}

    if status:
        q["status"] = status
    if search:
        q["$or"] = [
            {"username": {"$regex": search, "$options": "i"}},
            {"profile": {"$regex": search, "$options": "i"}},
        ]

    vouchers = await db.hotspot_vouchers.find(q, {"_id": 0}).sort("created_at", -1).to_list(limit)

    # Enrich with device name
    device_ids = list({v["device_id"] for v in vouchers if v.get("device_id")})
    devices_map = {}
    if device_ids:
        devs = await db.devices.find({"id": {"$in": device_ids}}, {"_id": 0, "id": 1, "name": 1}).to_list(200)
        devices_map = {d["id"]: d.get("name", d["id"]) for d in devs}

    now_utc = datetime.now(timezone.utc)
    result = []
    for v in vouchers:
        v["router_name"] = devices_map.get(v.get("device_id", ""), v.get("device_id", "—"))

        limit_uptime  = int(v.get("limit_uptime_secs", 0))
        used_uptime   = int(v.get("used_uptime_secs", 0))
        validity_secs = int(v.get("validity_secs", 0))
        
        # ── FIX: Fallback untuk voucher yang tidak tergenerate secs-nya (misal dari Moota/Portal)
        if validity_secs <= 0 and v.get("validity"):
            validity_secs = _parse_uptime_to_secs(v.get("validity"))
            v["validity_secs"] = validity_secs

        if limit_uptime <= 0 and v.get("uptime_limit"):
            limit_uptime = _parse_uptime_to_secs(v.get("uptime_limit"))
            v["limit_uptime_secs"] = limit_uptime

        # ── Sisa Uptime (hitung mundur, BERHENTI saat offline) ──────────────
        current_sess_elapsed = 0
        last_sess_start = v.get("last_session_start")
        if last_sess_start and v.get("status") == "active":
            try:
                start_dt = datetime.fromisoformat(last_sess_start.replace("Z", "+00:00"))
                current_sess_elapsed = max(0, int((now_utc - start_dt).total_seconds()))
            except Exception:
                pass

        if limit_uptime > 0:
            total_used = used_uptime + current_sess_elapsed
            v["rem_uptime_secs"]        = max(0, limit_uptime - total_used)
            v["used_uptime_secs"]       = total_used   # OVERWRITE agar Frontend pakai ini
            v["total_used_uptime_secs"] = total_used
            v["current_sess_elapsed"]   = current_sess_elapsed
        else:
            v["rem_uptime_secs"]        = 0
            v["total_used_uptime_secs"] = used_uptime
            v["current_sess_elapsed"]   = 0

        # ── Sisa Validitas (berjalan TERUS sejak first_login) ───────────────
        first_login = v.get("first_login_time")
        
        # ALIAS untuk kompatibilitas dengan Frontend: 
        # Jika UI butuh session_start_time, berikan first_login_time
        v["session_start_time"] = first_login

        if validity_secs > 0 and first_login:
            try:
                first_dt = datetime.fromisoformat(first_login.replace("Z", "+00:00"))
                elapsed_since_first = max(0, int((now_utc - first_dt).total_seconds()))
                v["rem_validity_secs"] = max(0, validity_secs - elapsed_since_first)
            except Exception:
                v["rem_validity_secs"] = validity_secs
        elif validity_secs > 0:
            v["rem_validity_secs"] = validity_secs  # Belum pernah login
        else:
            v["rem_validity_secs"] = 0

        result.append(v)

    return result


@router.put("/hotspot-vouchers/{voucher_id}", dependencies=[Depends(require_enterprise)])
async def update_hotspot_voucher(
    voucher_id: str,
    data: VoucherUpdate,
    user=Depends(require_write),
):
    db = get_db()
    voucher = await db.hotspot_vouchers.find_one({"id": voucher_id}, {"_id": 0})
    if not voucher:
        raise HTTPException(404, "Voucher tidak ditemukan")

    # â”€â”€ RBAC â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    if not check_device_access(user, voucher.get("device_id", "")):
        raise HTTPException(403, "Anda tidak memiliki hak akses untuk mengubah voucher pada router ini")

    update = {k: v for k, v in data.dict().items() if v is not None}
    if not update:
        raise HTTPException(400, "Tidak ada perubahan")
    update["updated_at"] = _now()
    result = await db.hotspot_vouchers.update_one({"id": voucher_id}, {"$set": update})
    if result.matched_count == 0:
        raise HTTPException(404, "Voucher tidak ditemukan")

    # FULL RADIUS MODE: Tidak sync ke MikroTik — password/profile dikelola murni via RADIUS DB.
    # MikroTik akan membaca credential dari RADIUS NOC Billing secara otomatis.
    logger.info(f"[hotspot][RADIUS] Voucher '{voucher_id}' diperbarui di DB, tidak sync ke MikroTik.")

    return {"message": "Voucher diperbarui"}


@router.put("/hotspot-vouchers/{voucher_id}/toggle-status", dependencies=[Depends(require_enterprise)])
async def toggle_hotspot_voucher_status(voucher_id: str, user=Depends(require_write)):
    db = get_db()
    voucher = await db.hotspot_vouchers.find_one({"id": voucher_id}, {"_id": 0})
    if not voucher:
        raise HTTPException(404, "Voucher tidak ditemukan")

    # â”€â”€ RBAC â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    if not check_device_access(user, voucher.get("device_id", "")):
        raise HTTPException(403, "Anda tidak memiliki hak akses untuk mengubah status voucher pada router ini")

    current_status = voucher.get("status", "new")
    new_status = "disabled" if current_status != "disabled" else "new"
    await db.hotspot_vouchers.update_one(
        {"id": voucher_id},
        {"$set": {"status": new_status, "updated_at": _now()}}
    )

    # FULL RADIUS MODE: Tidak perlu disable/enable di MikroTik secara langsung.
    # RADIUS NOC Billing otomatis menolak login jika status='disabled'.
    logger.info(f"[hotspot][RADIUS] Voucher '{voucher.get('username')}' status â†’ {new_status} (DB only, tidak sync ke MikroTik).")

    return {"status": new_status, "message": f"Voucher {'dinonaktifkan' if new_status == 'disabled' else 'diaktifkan'}"}


@router.post("/hotspot-vouchers/{voucher_id}/transfer", dependencies=[Depends(require_enterprise)])
async def transfer_hotspot_voucher(
    voucher_id: str,
    data: VoucherTransfer,
    user=Depends(require_write),
):
    db = get_db()
    voucher = await db.hotspot_vouchers.find_one({"id": voucher_id}, {"_id": 0})
    if not voucher:
        raise HTTPException(404, "Voucher tidak ditemukan")

    target_device = await db.devices.find_one({"id": data.new_device_id})
    if not target_device:
        raise HTTPException(404, "Router tujuan tidak ditemukan")

    # FULL RADIUS MODE: Transfer hanya mengupdate device_id di DB.
    # Tidak perlu create/delete user di MikroTik karena autentikasi via RADIUS NOC Billing.
    new_router_name = target_device.get("name", data.new_device_id)
    await db.hotspot_vouchers.update_one(
        {"id": voucher_id},
        {"$set": {
            "device_id":   data.new_device_id,
            "router_name": new_router_name,
            "updated_at":  _now()
        }}
    )

    logger.info(f"[hotspot][RADIUS] Voucher '{voucher.get('username')}' dipindah ke router '{new_router_name}' (DB only).")
    return {"message": f"Voucher berhasil dipindah ke {new_router_name}"}


@router.delete("/hotspot-vouchers/{voucher_id}", dependencies=[Depends(require_enterprise)])
async def delete_hotspot_voucher(voucher_id: str, user=Depends(require_write)):
    db = get_db()
    voucher = await db.hotspot_vouchers.find_one({"id": voucher_id}, {"_id": 0})
    if not voucher:
        raise HTTPException(404, "Voucher tidak ditemukan")

    # â”€â”€ RBAC â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    if not check_device_access(user, voucher.get("device_id", "")):
        raise HTTPException(403, "Anda tidak memiliki hak akses untuk menghapus voucher pada router ini")

    # FULL RADIUS MODE: Hapus HANYA dari DB — tidak perlu hapus dari MikroTik.
    # MikroTik otomatis menolak login karena user tidak lagi ada di RADIUS DB.
    await db.hotspot_vouchers.delete_one({"id": voucher_id})
    logger.info(f"[hotspot][RADIUS] Voucher '{voucher.get('username')}' dihapus dari DB (tidak sync ke MikroTik).")
    return {"message": "Voucher dihapus"}


# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•
# HOTSPOT SALES
# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•

@router.get("/hotspot-sales", dependencies=[Depends(require_enterprise)])
async def list_hotspot_sales(
    limit: int = Query(500),
    device_id: str = Query(""),
    user=Depends(get_current_user),
):
    db = get_db()
    q = {}

    # â”€â”€ RBAC: filter berdasarkan allowed_devices user â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    scope = get_user_allowed_devices(user)
    if scope is None:
        if device_id:
            q["device_id"] = device_id
    else:
        allowed = scope
        if device_id:
            allowed = [d for d in scope if d == device_id]
        if not allowed:
            return []
        q["device_id"] = {"$in": allowed}

    sales = await db.hotspot_sales.find(q, {"_id": 0}).sort("created_at", -1).to_list(limit)
    return sales


# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•
# HOTSPOT PROFILES (from MikroTik)
# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•

@router.get("/hotspot-profiles", dependencies=[Depends(require_enterprise)])
async def list_hotspot_profiles(
    device_id: str = Query(..., description="ID device MikroTik"),
    user=Depends(get_current_user),
):
    db = get_db()
    device = await db.devices.find_one({"id": device_id})
    if not device:
        raise HTTPException(404, "Device tidak ditemukan")

    try:
        from mikrotik_api import get_api_client
        mt = get_api_client(device)
        profiles = await mt.list_hotspot_profiles()
        return profiles or []
    except Exception as e:
        logger.warning(f"[hotspot-profiles] Gagal ambil dari MikroTik {device.get('name')}: {e}")
        return []


@router.get("/hotspot-server-profiles", dependencies=[Depends(require_enterprise)])
async def list_hotspot_server_profiles_api(
    device_id: str = Query(..., description="ID device MikroTik"),
    user=Depends(get_current_user),
):
    db = get_db()
    device = await db.devices.find_one({"id": device_id})
    if not device:
         raise HTTPException(404, "Device tidak ditemukan")
    try:
        from mikrotik_api import get_api_client
        mt = get_api_client(device)
        if hasattr(mt, "list_hotspot_server_profiles"):
             profiles = await mt.list_hotspot_server_profiles()
             return profiles or []
        return []
    except Exception as e:
        logger.warning(f"[hotspot-server-profiles] Gagal ambil dari MikroTik {device.get('name')}: {e}")
        return []

@router.get("/pppoe-profiles", dependencies=[Depends(require_enterprise)])
async def list_pppoe_profiles_api(
    device_id: str = Query(..., description="ID device MikroTik"),
    user=Depends(get_current_user),
):
    db = get_db()
    device = await db.devices.find_one({"id": device_id})
    if not device:
        raise HTTPException(404, "Device tidak ditemukan")
    try:
        from mikrotik_api import get_api_client
        mt = get_api_client(device)
        if hasattr(mt, "list_pppoe_profiles"):
             profiles = await mt.list_pppoe_profiles()
             return profiles or []
        return []
    except Exception as e:
        logger.warning(f"[pppoe-profiles] Gagal ambil dari MikroTik {device.get('name')}: {e}")
        return []

class PushRadiusRequest(BaseModel):
    device_id: str
    radius_ip: str
    secret: str
    server_profile: str = "hsprof1"
    pppoe_profile: str = ""

@router.post("/hotspot-push-radius", dependencies=[Depends(require_enterprise)])
async def push_hotspot_radius_config(req: PushRadiusRequest, user=Depends(require_write)):
    db = get_db()
    device = await db.devices.find_one({"id": req.device_id})
    if not device:
        raise HTTPException(404, "Device tidak ditemukan")

    try:
        from mikrotik_api import get_api_client
        mt = get_api_client(device)
        result = await mt.setup_hotspot_radius(req.radius_ip, req.secret, req.server_profile, req.pppoe_profile)

        # Update db flag if success
        if result.get("success"):
            await db.devices.update_one(
                {"id": req.device_id},
                {"$set": {
                    "hotspot_radius_enabled": True,
                    "radius_secret": req.secret,
                    "radius_host": req.radius_ip
                }}
            )

        return result
    except Exception as e:
        raise HTTPException(500, f"Gagal push RADIUS: {e}")

# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•
# HOTSPOT RADIUS STATUS
# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•

@router.get("/hotspot-radius-status", dependencies=[Depends(require_enterprise)])
async def hotspot_radius_status(
    device_id: str = Query(..., description="ID device MikroTik"),
    user=Depends(get_current_user),
):
    db = get_db()
    device = await db.devices.find_one({"id": device_id})
    if not device:
        raise HTTPException(404, "Device tidak ditemukan")

    try:
        from mikrotik_api import get_api_client
        mt = get_api_client(device)
        # Try to check if RADIUS is configured on hotspot server
        if hasattr(mt, "get_hotspot_server"):
            servers = await mt.get_hotspot_server() or []
            radius_enabled = any(s.get("use-radius") == "yes" or s.get("use_radius") for s in servers)
        else:
            # Fallback: check if device has radius_enabled flag in DB
            radius_enabled = device.get("hotspot_radius_enabled", False)
    except Exception as e:
        logger.warning(f"[hotspot-radius] Gagal cek RADIUS dari {device.get('name')}: {e}")
        radius_enabled = device.get("hotspot_radius_enabled", False)

    return {
        "device_id": device_id,
        "device_name": device.get("name", device_id),
        "radius_enabled": radius_enabled,
    }


# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•
# HOTSPOT USERS (batch create / generator)
# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•

class HotspotUserBatch(BaseModel):
    users: List[dict]


@router.post("/hotspot-users/batch", dependencies=[Depends(require_enterprise)])
async def batch_create_hotspot_users(
    data: HotspotUserBatch,
    device_id: str = Query(..., description="ID device MikroTik"),
    user=Depends(require_write),
):
    """
    Buat voucher Hotspot secara massal.
    FULL RADIUS MODE: Voucher HANYA disimpan ke database NOC Billing.
    MikroTik mengautentikasi user melalui RADIUS — tidak ada user yang dikirim ke router.
    """
    db = get_db()

    # â”€â”€ RBAC â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    if not check_device_access(user, device_id):
        raise HTTPException(403, "Anda tidak memiliki hak akses untuk membuat voucher pada router ini")

    device = await db.devices.find_one({"id": device_id})
    if not device:
        raise HTTPException(404, "Device tidak ditemukan")

    device_name = device.get("name", device_id)
    created = []
    failed = []

    for u in data.users:
        username = u.get("name") or u.get("username", "")
        password = u.get("password", username)
        profile  = u.get("profile", "default")
        comment  = u.get("comment", "")
        price    = float(u.get("price", 0))
        uptime_limit = u.get("uptime_limit", "")
        validity     = u.get("validity", "")

        try:
            # â”€â”€ FULL RADIUS: Simpan HANYA ke database, tidak kirim ke MikroTik â”€â”€
            voucher_doc = {
                "id":               str(uuid.uuid4()),
                "username":         username,
                "password":         password,
                "profile":          profile,
                "device_id":        device_id,
                "router_name":      device_name,
                "status":           "new",
                "price":            price,
                "uptime_limit":     uptime_limit,
                "validity":         validity,
                "comment":          comment,
                "session_start_time": None,
                "used_uptime_secs": 0,
                "limit_uptime_secs": _parse_uptime_to_secs(uptime_limit),
                "validity_secs":     _parse_uptime_to_secs(validity),
                "created_at":       _now(),
                "updated_at":       _now(),
            }
            await db.hotspot_vouchers.insert_one(voucher_doc)
            voucher_doc.pop("_id", None)
            created.append(username)
            logger.info(f"[hotspot-batch][RADIUS] Voucher '{username}' dicatat di DB — tidak dikirim ke MikroTik.")
        except Exception as e:
            logger.error(f"[hotspot-batch] Gagal simpan {username}: {e}")
            failed.append({"username": username, "error": str(e)})

    return {
        "message": f"{len(created)} voucher berhasil, {len(failed)} gagal",
        "created": created,
        "failed":  failed,
        "total":   len(data.users),
    }


def _parse_uptime_to_secs(uptime_str: str) -> int:
    """Parse '1h', '2h30m', '1d', '30m' â†’ seconds."""
    if not uptime_str:
        return 0
    import re
    total = 0
    for val, unit in re.findall(r"(\d+)\s*([wdhms])", uptime_str.lower()):
        v = int(val)
        multipliers = {"w": 604800, "d": 86400, "h": 3600, "m": 60, "s": 1}
        total += v * multipliers.get(unit, 0)
    return total


# ══════════════════════════════════════════════════════════════════════════════
# HOTSPOT ANALYTICS — Dashboard agregasi revenue & voucher stats
# ══════════════════════════════════════════════════════════════════════════════

@router.get("/hotspot-analytics", dependencies=[Depends(require_enterprise)])
async def get_hotspot_analytics(
    device_id: str = Query(""),
    user=Depends(get_current_user),
):
    """Aggregasi analytics: revenue hari ini/bulan/total, trend 7 hari, top paket, per-lokasi."""
    db = get_db()
    now_utc = datetime.now(timezone.utc)
    today_start = now_utc.replace(hour=0, minute=0, second=0, microsecond=0).isoformat()
    month_start = now_utc.replace(day=1, hour=0, minute=0, second=0, microsecond=0).isoformat()

    voucher_q: dict = {}
    sales_q: dict = {}
    scope = get_user_allowed_devices(user)
    if scope is None:
        if device_id:
            voucher_q["device_id"] = device_id
            sales_q["device_id"] = device_id
    else:
        allowed = [d for d in scope if d == device_id] if device_id else scope
        if not allowed:
            return _empty_analytics()
        voucher_q["device_id"] = {"$in": allowed}
        sales_q["device_id"] = {"$in": allowed}

    all_vouchers = await db.hotspot_vouchers.find(
        voucher_q, {"_id": 0, "status": 1, "price": 1, "profile": 1, "device_id": 1}
    ).to_list(20000)

    all_sales = await db.hotspot_sales.find(
        sales_q, {"_id": 0, "price": 1, "created_at": 1, "device_id": 1}
    ).to_list(20000)

    today_sales = [s for s in all_sales if (s.get("created_at") or "") >= today_start]
    month_sales = [s for s in all_sales if (s.get("created_at") or "") >= month_start]
    rev_today   = sum(float(s.get("price", 0)) for s in today_sales)
    rev_month   = sum(float(s.get("price", 0)) for s in month_sales)
    rev_total   = sum(float(s.get("price", 0)) for s in all_sales)

    trend = []
    for i in range(6, -1, -1):
        day = now_utc - timedelta(days=i)
        day_str = day.strftime("%Y-%m-%d")
        day_s = [s for s in all_sales if (s.get("created_at") or "")[:10] == day_str]
        trend.append({
            "date": day_str, "label": day.strftime("%d/%m"),
            "count": len(day_s), "revenue": sum(float(s.get("price", 0)) for s in day_s),
        })

    from collections import Counter
    top_packages = [
        {"name": p, "count": c}
        for p, c in Counter(v.get("profile", "unknown") for v in all_vouchers if v.get("profile")).most_common(5)
    ]

    device_ids = list({v.get("device_id") for v in all_vouchers if v.get("device_id")})
    devices_map: dict = {}
    if device_ids:
        devs = await db.devices.find({"id": {"$in": device_ids}}, {"_id": 0, "id": 1, "name": 1}).to_list(200)
        devices_map = {d["id"]: d.get("name", d["id"]) for d in devs}

    loc: dict = {}
    for v in all_vouchers:
        did = v.get("device_id", "unknown")
        if did not in loc:
            loc[did] = {"device_id": did, "device_name": devices_map.get(did, did),
                        "total": 0, "active": 0, "expired": 0, "new": 0, "disabled": 0, "revenue_month": 0.0}
        loc[did]["total"] += 1
        st = v.get("status", "new")
        if st in loc[did]:
            loc[did][st] += 1
    for s in month_sales:
        did = s.get("device_id", "unknown")
        if did in loc:
            loc[did]["revenue_month"] += float(s.get("price", 0))

    return {
        "vouchers": {
            "total": len(all_vouchers),
            "active":   sum(1 for v in all_vouchers if v.get("status") == "active"),
            "expired":  sum(1 for v in all_vouchers if v.get("status") == "expired"),
            "new":      sum(1 for v in all_vouchers if v.get("status") == "new"),
            "disabled": sum(1 for v in all_vouchers if v.get("status") == "disabled"),
        },
        "revenue": {
            "today": rev_today, "month": rev_month, "total": rev_total,
            "today_count": len(today_sales), "month_count": len(month_sales), "total_count": len(all_sales),
        },
        "trend": trend,
        "top_packages": top_packages,
        "locations": list(loc.values()),
    }


def _empty_analytics() -> dict:
    return {
        "vouchers": {"total": 0, "active": 0, "expired": 0, "new": 0, "disabled": 0},
        "revenue": {"today": 0, "month": 0, "total": 0, "today_count": 0, "month_count": 0, "total_count": 0},
        "trend": [], "top_packages": [], "locations": [],
    }


# ══════════════════════════════════════════════════════════════════════════════
# BANDWIDTH PER VOUCHER — dari radius_accounting / hotspot_sessions di DB
# ══════════════════════════════════════════════════════════════════════════════

@router.get("/hotspot-vouchers/{voucher_id}/bandwidth", dependencies=[Depends(require_enterprise)])
async def get_voucher_bandwidth(voucher_id: str, user=Depends(get_current_user)):
    """Ambil data bandwidth dari DB. Return {available:false} jika tidak ada data."""
    db = get_db()
    voucher = await db.hotspot_vouchers.find_one({"id": voucher_id}, {"_id": 0, "username": 1})
    if not voucher:
        raise HTTPException(404, "Voucher tidak ditemukan")
    username = voucher.get("username", "")

    acct = None
    for col in ["radius_accounting", "hotspot_sessions"]:
        try:
            acct = await db[col].find_one({"username": username}, {"_id": 0}, sort=[("created_at", -1)])
            if acct:
                break
        except Exception:
            pass

    if not acct:
        return {"available": False, "username": username}

    bytes_in  = int(acct.get("acct_input_octets")  or acct.get("Acct-Input-Octets")  or acct.get("bytes_in",  0))
    bytes_out = int(acct.get("acct_output_octets") or acct.get("Acct-Output-Octets") or acct.get("bytes_out", 0))
    sess_time = int(acct.get("acct_session_time")  or acct.get("Acct-Session-Time")  or acct.get("session_time", 0))

    return {
        "available": True, "username": username,
        "bytes_in": bytes_in, "bytes_out": bytes_out,
        "total_bytes": bytes_in + bytes_out,
        "mb_in": round(bytes_in / 1024 / 1024, 2),
        "mb_out": round(bytes_out / 1024 / 1024, 2),
        "session_time": sess_time,
    }


# ══════════════════════════════════════════════════════════════════════════════
# EXPORT VOUCHER — streaming CSV
# ══════════════════════════════════════════════════════════════════════════════

@router.get("/hotspot-vouchers/export", dependencies=[Depends(require_enterprise)])
async def export_hotspot_vouchers(
    device_id: str = Query(""),
    status: str = Query(""),
    user=Depends(get_current_user),
):
    """Export semua voucher ke file CSV."""
    db = get_db()
    q: dict = {}
    scope = get_user_allowed_devices(user)
    if scope is None:
        if device_id:
            q["device_id"] = device_id
    else:
        allowed = [d for d in scope if d == device_id] if device_id else scope
        if not allowed:
            q["device_id"] = {"$in": []}
        else:
            q["device_id"] = {"$in": allowed}
    if status:
        q["status"] = status

    vouchers = await db.hotspot_vouchers.find(q, {"_id": 0}).sort("created_at", -1).to_list(20000)
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(["username", "password", "profile", "price", "uptime_limit", "validity", "status", "router_name", "comment", "created_at"])
    for v in vouchers:
        writer.writerow([
            v.get("username", ""), v.get("password", ""), v.get("profile", ""),
            v.get("price", 0), v.get("uptime_limit", ""), v.get("validity", ""),
            v.get("status", ""), v.get("router_name", ""), v.get("comment", ""), v.get("created_at", ""),
        ])
    buf.seek(0)
    fname = f"vouchers_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}.csv"
    return StreamingResponse(
        iter([buf.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename={fname}"},
    )


# ══════════════════════════════════════════════════════════════════════════════
# IMPORT VOUCHER — dari file CSV (skip duplikat username per device)
# ══════════════════════════════════════════════════════════════════════════════

@router.post("/hotspot-vouchers/import", dependencies=[Depends(require_enterprise)])
async def import_hotspot_vouchers(
    device_id: str = Query(...),
    file: UploadFile = File(...),
    user=Depends(require_write),
):
    """
    Import voucher dari CSV. Kolom wajib: username.
    Opsional: password, profile, price, uptime_limit, validity, comment.
    Skip jika username sudah ada di device yang sama (tidak overwrite).
    """
    if not check_device_access(user, device_id):
        raise HTTPException(403, "Tidak memiliki akses ke router ini")
    db = get_db()
    device = await db.devices.find_one({"id": device_id})
    if not device:
        raise HTTPException(404, "Device tidak ditemukan")
    device_name = device.get("name", device_id)

    content = await file.read()
    try:
        text = content.decode("utf-8-sig")
    except UnicodeDecodeError:
        text = content.decode("latin-1")

    reader = csv.DictReader(io.StringIO(text))
    created, skipped, failed = [], [], []

    for row in reader:
        username = (row.get("username") or row.get("name") or "").strip()
        if not username:
            failed.append({"row": str(row)[:80], "error": "Username kosong"})
            continue
        existing = await db.hotspot_vouchers.find_one({"username": username, "device_id": device_id})
        if existing:
            skipped.append(username)
            continue
        try:
            password     = (row.get("password") or username).strip()
            profile      = (row.get("profile")  or "default").strip()
            price        = float(row.get("price") or 0)
            uptime_limit = (row.get("uptime_limit") or "").strip()
            validity     = (row.get("validity") or "").strip()
            comment      = (row.get("comment") or "").strip()
            doc = {
                "id": str(uuid.uuid4()), "username": username, "password": password,
                "profile": profile, "device_id": device_id, "router_name": device_name,
                "status": "new", "price": price, "uptime_limit": uptime_limit, "validity": validity,
                "comment": comment, "session_start_time": None, "used_uptime_secs": 0,
                "limit_uptime_secs": _parse_uptime_to_secs(uptime_limit),
                "validity_secs": _parse_uptime_to_secs(validity),
                "created_at": _now(), "updated_at": _now(),
            }
            await db.hotspot_vouchers.insert_one(doc)
            created.append(username)
        except Exception as e:
            failed.append({"username": username, "error": str(e)})

    return {
        "message": f"{len(created)} diimpor, {len(skipped)} dilewati (duplikat), {len(failed)} gagal",
        "created": created, "skipped": skipped, "failed": failed,
        "total": len(created) + len(skipped) + len(failed),
    }


@router.post("/hotspot-vouchers/import/mikrotik", dependencies=[Depends(require_enterprise)])
async def import_mikrotik_hotspot_vouchers(
    device_id: str = Query(...),
    user=Depends(require_write),
):
    """
    Import voucher/user langsung dari router MikroTik (Hotspot).
    Pastikan password, profile/paket, limit uptime, dan sisa uptime ikut terimport.
    """
    if not check_device_access(user, device_id):
        raise HTTPException(403, "Tidak memiliki akses ke router ini")
    db = get_db()
    device = await db.devices.find_one({"id": device_id})
    if not device:
        raise HTTPException(404, "Device tidak ditemukan")
    device_name = device.get("name", device_id)

    try:
        from mikrotik_api import get_api_client
        mt = get_api_client(device)
        hotspot_users = await mt.list_hotspot_users()
    except Exception as e:
        logger.error(f"[hotspot-import] Gagal ambil data dari MikroTik: {e}")
        raise HTTPException(500, f"Gagal terhubung ke MikroTik: {e}")

    # Buat peta profile -> price
    packages = await db.billing_packages.find(
        {"source_device_id": device_id, "type": {"$in": ["hotspot", "both"]}},
        {"_id": 0, "profile_name": 1, "price": 1}
    ).to_list(1000)
    profile_price_map = {p.get("profile_name"): p.get("price", 0) for p in packages if p.get("profile_name")}

    created, skipped, failed = [], [], []

    for u in hotspot_users:
        username = (u.get("name") or "").strip()
        if not username or username == "default-trial":
            continue
        
        existing = await db.hotspot_vouchers.find_one({"username": username, "device_id": device_id})
        if existing:
            skipped.append(username)
            continue
            
        try:
            password     = (u.get("password") or "").strip()
            profile      = (u.get("profile") or "default").strip()
            uptime_limit = (u.get("limit-uptime") or "").strip()
            uptime_used  = (u.get("uptime") or "").strip()
            comment      = (u.get("comment") or "").strip()
            
            price = profile_price_map.get(profile, 0)
            
            used_uptime_secs = _parse_uptime_to_secs(uptime_used)
            limit_uptime_secs = _parse_uptime_to_secs(uptime_limit)
            
            status = "new"
            if used_uptime_secs > 0:
                status = "active"
                if limit_uptime_secs > 0 and used_uptime_secs >= limit_uptime_secs:
                    status = "expired"

            doc = {
                "id": str(uuid.uuid4()), "username": username, "password": password,
                "profile": profile, "device_id": device_id, "router_name": device_name,
                "status": status, "price": price, "uptime_limit": uptime_limit, "validity": "",
                "comment": comment, "session_start_time": None, "used_uptime_secs": used_uptime_secs,
                "limit_uptime_secs": limit_uptime_secs,
                "validity_secs": 0,
                "created_at": _now(), "updated_at": _now(),
            }
            await db.hotspot_vouchers.insert_one(doc)
            created.append(username)
        except Exception as e:
            failed.append({"username": username, "error": str(e)})

    return {
        "message": f"Import MikroTik selesai: {len(created)} diimpor, {len(skipped)} dilewati, {len(failed)} gagal",
        "created": created, "skipped": skipped, "failed": failed,
        "total": len(created) + len(skipped) + len(failed),
    }
