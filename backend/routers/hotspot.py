"""
Hotspot users router: list, create, update, delete via MikroTik API.
"""
from fastapi import APIRouter, HTTPException, Depends, BackgroundTasks
from pydantic import BaseModel
from typing import Optional
from datetime import datetime, timezone
from core.db import get_db
from core.auth import get_current_user, require_admin, require_write
from mikrotik_api import get_api_client
import re
from bson import ObjectId


# Regex pembantu untuk parse waktu MikroTik (1d05:10:15, 05:10:15, 1h30m, 5m, dll)
def parse_mt_time(s: str) -> int:
    if not s or s == "0s" or s == "0": return 0
    s = s.lower().strip()
    if ":" in s:
        days = 0
        if "d" in s:
            days_part, hms_part = s.split("d")
            days = int(days_part)
            s = hms_part
        parts = s.split(":")
        if len(parts) == 3: # hh:mm:ss
            h, m, sec = map(int, parts)
            return days * 86400 + h * 3600 + m * 60 + sec
        elif len(parts) == 2: # mm:ss
            m, sec = map(int, parts)
            return days * 86400 + m * 60 + sec
    p = re.findall(r"(\d+)\s*([hmds])", s)
    if p:
        tot = 0
        for val, unit in p:
            tot += int(val) * {"h": 3600, "m": 60, "d": 86400, "s": 1}.get(unit, 0)
        return tot
    try: return int(s) # fallback as seconds
    except: return 0

def fmt_time(s: int) -> str:
    if s <= 0: return "0s"
    d, s = divmod(s, 86400)
    h, s = divmod(s, 3600)
    m, sec = divmod(s, 60)
    res = []
    if d: res.append(f"{d}d")
    if h: res.append(f"{h}h")
    if m: res.append(f"{m}m")
    if sec or not res: res.append(f"{sec}s")
    return "".join(res)

router = APIRouter(tags=["hotspot"])
from fastapi import HTTPException

async def _get_mt_api(device_id: str):
    db = get_db()
    device = await db.devices.find_one({"id": device_id})
    if not device:
        raise HTTPException(404, f"Device {device_id} not found")
    from mikrotik_api import get_api_client
    return get_api_client(device), device

class HotspotUserCreate(BaseModel):
    name: str
    password: str
    profile: str = "default"
    server: str = "all"
    comment: str = ""
    price: Optional[str] = "0"
    validity: Optional[str] = ""
    uptime_limit: Optional[str] = ""

class HotspotUserBatchCreate(BaseModel):
    users: list[HotspotUserCreate]

class HotspotUserUpdate(BaseModel):
    name: Optional[str] = None
    password: Optional[str] = None
    profile: Optional[str] = None
    server: Optional[str] = None
    comment: Optional[str] = None
    disabled: Optional[str] = None


async def _get_mt_api(device_id: str):
    db = get_db()
    device = await db.devices.find_one({"id": device_id}, {"_id": 0})
    if not device:
        raise HTTPException(404, "Device not found")
    return get_api_client(device), device


@router.get("/hotspot-users")
async def list_hotspot_users(device_id: str = "", search: str = "", user=Depends(get_current_user)):
    if not device_id:
        return []
    try:
        mt, _ = await _get_mt_api(device_id)
        users = await mt.list_hotspot_users()
        active_list = await mt.list_hotspot_active()
    except Exception as e:
        raise HTTPException(503, f"MikroTik API error: {e}")
    active_names = {a.get("user", "") for a in active_list}
    result = []
    for u in users:
        u["is_online"] = u.get("name", "") in active_names
        if search and search.lower() not in str(u).lower():
            continue
        result.append(u)
    return result

@router.get("/hotspot-vouchers")
async def list_hotspot_vouchers(device_id: str = "", search: str = "", user=Depends(get_current_user)):
    db = get_db()
    query = {}
    if device_id:
        query["device_id"] = device_id
    if search:
        query["username"] = {"$regex": search, "$options": "i"}

    vouchers = await db.hotspot_vouchers.find(query).sort("created_at", -1).to_list(1000)
    
    import asyncio
    device_map = {}
    
    # Pre-fetch required devices
    dev_ids = list({v.get("device_id") for v in vouchers if v.get("device_id") and v.get("device_id") != "all"})
    for d_id in dev_ids:
        device = await db.devices.find_one({"id": d_id})
        if device:
            device_map[d_id] = device

    # We need to run mt.list_hotspot_users() for all hit devices concurrently
    mt_users = {}  # {device_id: {username: user_dict}}
    
    async def fetch_mt(d_id, dev_rec):
        try:
            mt = get_api_client(dev_rec)
            users_list, active_list = await asyncio.gather(
                mt.list_hotspot_users(),
                mt.list_hotspot_active(),
                return_exceptions=True
            )
            
            d_users = {}
            if not isinstance(users_list, Exception) and users_list:
                for u in users_list:
                    uname = u.get("name")
                    if uname:
                        d_users[uname.lower()] = u
            
            # RADIUS users might only appear in active_list!
            if not isinstance(active_list, Exception) and active_list:
                for a in active_list:
                    uname = a.get("user") or a.get("name")
                    if uname:
                        ukey = uname.lower()
                        if ukey not in d_users:
                            d_users[ukey] = dict(a) # Copy to avoid mutating original
                            d_users[ukey]["is_radius"] = True
                        else:
                            try:
                                # Accumulate total uptime: Historical (/ip hotspot user) + Current Session (/ip hotspot active)
                                user_up = parse_mt_time(d_users[ukey].get("uptime") or "0s")
                                act_up = parse_mt_time(str(a.get("uptime") or a.get("up-time") or "0s"))
                                d_users[ukey]["uptime"] = fmt_time(user_up + act_up)
                                
                                # Accumulate Bytes
                                user_bin = int(str(d_users[ukey].get("bytes-in") or "0")) if str(d_users[ukey].get("bytes-in") or "0").isdigit() else 0
                                act_bin = int(str(a.get("bytes-in") or a.get("bytes_in") or "0")) if str(a.get("bytes-in") or a.get("bytes_in") or "0").isdigit() else 0
                                d_users[ukey]["bytes-in"] = str(user_bin + act_bin)
                                
                                user_bout = int(str(d_users[ukey].get("bytes-out") or "0")) if str(d_users[ukey].get("bytes-out") or "0").isdigit() else 0
                                act_bout = int(str(a.get("bytes-out") or a.get("bytes_out") or "0")) if str(a.get("bytes-out") or a.get("bytes_out") or "0").isdigit() else 0
                                d_users[ukey]["bytes-out"] = str(user_bout + act_bout)
                            except Exception as e:
                                # Fallback gracefully on parsing errors
                                d_users[ukey]["uptime"] = a.get("uptime") or d_users[ukey].get("uptime")
                                pass
                        
                        # Mark as online
                        d_users[ukey]["is_online"] = True
            
            mt_users[d_id] = d_users
        except Exception:
            mt_users[d_id] = {}

    if device_map:
        await asyncio.gather(*(fetch_mt(d_id, dev) for d_id, dev in device_map.items()))

    # Collect voucher IDs yang perlu di-update statusnya ke DB
    vouchers_to_update_session = []
    vouchers_to_mark_expired = []

    # Utils parse_mt_time dan fmt_time telah dipindah ke global scope di atas

    vouchers_to_update_stats = [] # [(id, used_uptime_secs)]
    
    now_utc = datetime.now(timezone.utc)

    for v in vouchers:
        v_orig_id = v["_id"] # Simpan ObjectId asli untuk update DB nanti
        v["_id"] = str(v["_id"])
        did = v.get("device_id")
        dev = device_map.get(did)
        v["router_name"] = dev.get("name", "Semua Router") if dev else "Semua Router"
        
        limit_secs = parse_mt_time(v.get("uptime_limit"))
        validity_secs = parse_mt_time(v.get("validity"))
        sst_str = v.get("session_start_time")
        
        # 1. Hitung Sisa Masa Aktif (Continuous)
        if sst_str:
            start = datetime.fromisoformat(sst_str.replace("Z", "+00:00"))
            if start.tzinfo is None: start = start.replace(tzinfo=timezone.utc)
            elapsed_act = int((now_utc - start).total_seconds())
            rem_validity = max(0, validity_secs - elapsed_act) if validity_secs > 0 else 999999999
            v["sisa_validity_db"] = fmt_time(rem_validity) if validity_secs > 0 else "Unlimited"
        else:
            v["sisa_validity_db"] = v.get("validity", "Unlimited")
            rem_validity = 999999999

        # 2. Hitung Sisa Uptime (Usage/Pause) dan Status Real-time
        used_now = v.get("used_uptime_secs", 0)
        v_uname_low = v.get("username", "").lower()
        
        # Cari data MikroTik (mtu) - Coba spesifik router dulu, lalu global jika "all"
        mtu = {}
        if did in mt_users and v_uname_low in mt_users[did]:
            mtu = mt_users[did][v_uname_low]
        elif (not did or did == "all" or did == "") and mt_users:
            for d_id_search, users_map in mt_users.items():
                if v_uname_low in users_map:
                    mtu = users_map[v_uname_low]
                    break

        # Ambil status DB asli SEBELUM logika apapun — status 'disabled' harus dihormati
        db_status = v.get("status", "new")

        if mtu:
            v["bytes_in"] = mtu.get("bytes-in") or mtu.get("bytes_in") or "0"
            v["bytes_out"] = mtu.get("bytes-out") or mtu.get("bytes_out") or "0"
            
            mt_uptime_str = mtu.get("uptime") or mtu.get("up-time") or "0s"
            mt_uptime_secs = parse_mt_time(mt_uptime_str)
            is_radius = mtu.get("is_radius", False)
            
            # Update used_now jika MikroTik melaporkan penggunaan yang lebih baru
            if is_radius:
                # mt_uptime_secs is ONLY the latest session. Total = Historical (DB) + Session (Mikrotik Active)
                prev_sess = v.get("current_session_secs", 0)
                
                # Jika uptime mikroTik lebih kecil dari prev_sess, berarti sesi baru dimulai (koneksi ulang)
                if mt_uptime_secs < prev_sess:
                    prev_sess = 0
                    
                if mt_uptime_secs > prev_sess:
                    increment = mt_uptime_secs - prev_sess
                    used_now += increment
                    vouchers_to_update_stats.append((v_orig_id, used_now, mt_uptime_secs))
            else:
                # Local Mikrotik: mt_uptime_secs is ALREADY the accumulated absolute total
                if mt_uptime_secs > used_now:
                    used_now = mt_uptime_secs
                    vouchers_to_update_stats.append((v_orig_id, used_now, 0))
            
            # PENTING: Jika status DB adalah 'disabled', JANGAN timpa dengan status MikroTik.
            # Voucher yang di-disable sementara tetap ada di MikroTik (mode disabled=yes),
            # sehingga mtu bisa ditemukan — tapi status tetap harus 'disabled'.
            if db_status == "disabled":
                v["status"] = "disabled"
            else:
                is_online = mtu.get("is_online", False)
                if is_online:
                    v["status"] = "active"
                elif used_now > 0 or sst_str:
                    v["status"] = "offline"
                else:
                    v["status"] = db_status or "new"
            
            # Tandai aktivasi pertama (session start) — hanya jika tidak disabled
            if used_now > 0 and not sst_str and db_status != "disabled":
                vouchers_to_update_session.append(v_orig_id)
                v["session_start_time"] = now_utc.isoformat()
        else:
            # Tidak ada di MikroTik (Offline / Baru)
            v["bytes_in"] = "0"
            v["bytes_out"] = "0"
            # PENTING: Jangan timpa status 'disabled' dengan 'offline' atau 'new'
            if db_status == "disabled":
                v["status"] = "disabled"
            elif used_now > 0 or sst_str:
                v["status"] = "offline"
            else:
                v["status"] = db_status or "new"

        v["uptime"] = fmt_time(used_now)

        rem_uptime = max(0, limit_secs - used_now) if limit_secs > 0 else 999999999
        v["sisa_waktu_db"] = fmt_time(rem_uptime) if limit_secs > 0 else "Unlimited"
        
        # Injeksi data numerik untuk live counter di frontend
        v["used_uptime_secs"] = used_now
        v["limit_uptime_secs"] = limit_secs
        v["validity_secs"] = validity_secs
        v["rem_validity_secs"] = rem_validity

        # 3. Check Expiry (Dual-Check)
        # PENTING: Voucher 'disabled' tidak bisa di-expired secara otomatis.
        # Admin harus mengaktifkan kembali terlebih dahulu.
        if v["status"] != "disabled":
            if (limit_secs > 0 and rem_uptime <= 0) or (validity_secs > 0 and rem_validity <= 0):
                if v["status"] != "expired":
                    v["status"] = "expired"
                    vouchers_to_mark_expired.append(v_orig_id)

    # Batch Update DB
    if vouchers_to_update_stats:
        for vid_obj, u_secs, s_secs in vouchers_to_update_stats:
            await db.hotspot_vouchers.update_one(
                {"_id": vid_obj}, 
                {"$set": {"used_uptime_secs": u_secs, "current_session_secs": s_secs}}
            )
            
    if vouchers_to_update_session:
        # PENTING: Filter hanya voucher yang bukan disabled sebelum update ke DB.
        # Hindari overwrite status 'disabled' menjadi 'active' saat DB batch update.
        await db.hotspot_vouchers.update_many(
            {"_id": {"$in": vouchers_to_update_session}, "status": {"$ne": "disabled"}},
            {"$set": {"session_start_time": now_utc.isoformat(), "status": "active"}}
        )

    if vouchers_to_mark_expired:
        await db.hotspot_vouchers.update_many(
            {"_id": {"$in": vouchers_to_mark_expired}},
            {"$set": {"status": "expired"}}
        )

    return vouchers


@router.delete("/hotspot-vouchers/{vid}")
async def delete_hotspot_voucher(vid: str, user=Depends(require_write)):
    db = get_db()
    res = await db.hotspot_vouchers.delete_one({"id": vid})
    if res.deleted_count == 0:
        raise HTTPException(404, "Voucher not found")
    return {"message": "Deleted"}

async def _bg_toggle_mikrotik(device_id: str, username: str, new_status: str):
    try:
        db = get_db()
        device = await db.devices.find_one({"id": device_id})
        if device:
            from mikrotik_api import get_api_client
            mt = get_api_client(device)
            users = await mt.list_hotspot_users()
            mtu = next((u for u in users if u.get("name") == username), None)
            if mtu:
                await mt.update_hotspot_user(mtu[".id"], {"disabled": "yes" if new_status == "disabled" else "no"})
    except Exception as e:
        print(f"Failed to toggle MikroTik voucher status (Background): {e}")

@router.put("/hotspot-vouchers/{vid}/toggle-status")
async def toggle_hotspot_voucher_status(vid: str, background_tasks: BackgroundTasks, user=Depends(require_write)):
    db = get_db()
    v = await db.hotspot_vouchers.find_one({"id": vid})
    if not v:
        raise HTTPException(404, "Voucher not found")
        
    old_status = v.get("status", "new")
    
    # Jika disabled, kembali ke active/new. Jika active/new/expired, jadi disabled.
    if old_status == "disabled":
        if v.get("session_start_time"):
            new_status = "active"
        else:
            new_status = "new"
    else:
        new_status = "disabled"

    await db.hotspot_vouchers.update_one(
        {"id": vid},
        {"$set": {"status": new_status, "updated_at": datetime.utcnow().isoformat()}}
    )
    
    # Disable on MikroTik (asynchronous!)
    if v.get("device_id") and v.get("device_id") != "all":
        background_tasks.add_task(_bg_toggle_mikrotik, v["device_id"], v["username"], new_status)
            
    return {"message": "Status toggled", "status": new_status}

class VoucherEditRequest(BaseModel):
    password: Optional[str] = None
    profile: Optional[str] = None
    validity: Optional[str] = None
    uptime_limit: Optional[str] = None

@router.put("/hotspot-vouchers/{vid}")
async def edit_hotspot_voucher(vid: str, data: VoucherEditRequest, user=Depends(require_write)):
    db = get_db()
    v = await db.hotspot_vouchers.find_one({"id": vid})
    if not v:
        raise HTTPException(404, "Voucher not found")

    # ── Update MongoDB ──────────────────────────────────────────────────────────
    # PENTING: Hanya field yang dikirim yang diupdate.
    # session_start_time TIDAK PERNAH diubah di sini (agar timer tidak reset).
    updates = {"updated_at": datetime.utcnow().isoformat()}
    if data.password:     updates["password"]     = data.password
    if data.profile:      updates["profile"]      = data.profile
    if data.validity:     updates["validity"]     = data.validity
    if data.uptime_limit: updates["uptime_limit"] = data.uptime_limit  # FIX: simpan ke DB!

    await db.hotspot_vouchers.update_one(
        {"id": vid},
        {"$set": updates}  # Tidak menyentuh session_start_time
    )

    # ── Sync ke MikroTik ──────────────────────────────────────────────────────
    if v.get("device_id") and v.get("device_id") != "all":
        try:
            device = await db.devices.find_one({"id": v["device_id"]})
            if device:
                from mikrotik_api import get_api_client
                mt = get_api_client(device)
                users = await mt.list_hotspot_users()
                mtu = next((u for u in users if u.get("name") == v["username"]), None)
                if mtu:
                    mt_updates = {}
                    if data.password:     mt_updates["password"]     = data.password
                    if data.profile:      mt_updates["profile"]      = data.profile
                    if data.uptime_limit: mt_updates["limit-uptime"] = data.uptime_limit
                    if mt_updates:
                        await mt.update_hotspot_user(mtu[".id"], mt_updates)
        except Exception as e:
            print(f"Failed to update voucher on MikroTik: {e}")

    return {"message": "Voucher updated"}

class VoucherTransferRequest(BaseModel):
    new_device_id: str

@router.post("/hotspot-vouchers/{vid}/transfer")
async def transfer_hotspot_voucher(vid: str, data: VoucherTransferRequest, user=Depends(require_admin)):
    import traceback
    db = get_db()
    v = await db.hotspot_vouchers.find_one({"id": vid})
    if not v:
        raise HTTPException(404, "Voucher not found")
    
    old_device_id = v.get("device_id")
    new_device_id = data.new_device_id
    if old_device_id == new_device_id:
        return {"message": "Sudah berada di router yang sama"}
        
    mt_new, dev_new = await _get_mt_api(new_device_id)
    
    # 1. Hapus dari Router Lama
    if old_device_id and old_device_id != "all":
        try:
            mt_old, _ = await _get_mt_api(old_device_id)
            old_users = await mt_old.list_hotspot_users()
            mtu = next((u for u in old_users if u.get("name") == v["username"]), None)
            if mtu:
                await mt_old.delete_hotspot_user(mtu[".id"])
        except Exception:
            pass # ignore, as long as we can put it on the new router
            
    # 2. Add ke Router Baru
    hs_data = {
        "server": "all",
        "name": v["username"],
        "password": v["password"],
        "profile": v.get("profile", "default"),
        "comment": v.get("comment", "Moved via API")
    }
    
    try:
        await mt_new.create_hotspot_user(hs_data)
    except Exception as e:
        # if already exists etc
        pass

    # 3. Update DB
    await db.hotspot_vouchers.update_one({"id": vid}, {"$set": {"device_id": new_device_id}})
    
    # Optional update sales IP just for consistency
    await db.hotspot_sales.update_many({"voucher_id": vid}, {"$set": {"device_ip": dev_new.get("ip_address", "unknown")}})
    
    return {"message": "Voucher transferred successfully"}


@router.post("/hotspot-users", status_code=201)
async def create_hotspot_user(device_id: str, data: HotspotUserCreate, user=Depends(require_write)):
    mt, _ = await _get_mt_api(device_id)
    body = {k: v for k, v in data.model_dump().items() if v and k not in ("price", "validity")}
    try:
        return await mt.create_hotspot_user(body)
    except Exception as e:
        raise HTTPException(503, f"MikroTik: {e}")

from datetime import datetime
import uuid

@router.post("/hotspot-users/batch", status_code=201)
async def create_hotspot_users_batch(device_id: str, data: HotspotUserBatchCreate, user=Depends(require_write)):
    """
    Buat voucher hotspot dalam batch dan simpan ke database.
    CATATAN: Tidak push ke MikroTik karena sistem menggunakan RADIUS.
    RADIUS akan membuat session otomatis saat voucher digunakan untuk login.
    """
    db = get_db()
    docs = []
    _now_str = datetime.now(timezone.utc).isoformat()
    _today = datetime.now().strftime("%Y-%m-%d")
    for u in data.users:
        doc = {
            "id": str(uuid.uuid4()),
            "username": u.name,
            "password": u.password,
            "profile": u.profile,
            "server": u.server,
            "price": u.price,
            "validity": u.validity,
            "uptime_limit": u.uptime_limit,
            "status": "new",
            "device_id": device_id,
            "created_at": _now_str,
            "comment": u.comment or ("Voucher " + _today),
        }
        docs.append(doc)
    if docs:
        try:
            await db.hotspot_vouchers.insert_many(docs)
        except Exception as e:
            raise HTTPException(500, f"Database error: {e}")
    return {"message": f"Berhasil membuat {len(docs)} voucher di Database!", "errors": None}


class ZTPPurchaseRequest(BaseModel):
    device_id: Optional[str] = "global"  # Bisa digunakan dimana saja secara default
    profile: str
    price: str
    validity: str
    server: str = "all"
    comment: str = "Purchased via ZTP"
    webhook_key: str

@router.post("/hotspot-users/ztp", status_code=201)
async def create_ztp_voucher(data: ZTPPurchaseRequest):
    """Endpoint publik untuk N8N / Payment Gateway webhook memproses ZTP."""
    db = get_db()
    settings = await db.billing_settings.find_one({}, {"_id": 0}) or {}
    ztp_key = settings.get("ztp_webhook_key", "")
    if not ztp_key or data.webhook_key != ztp_key:
        raise HTTPException(401, "Invalid ZTP Webhook Key")
        
    if data.device_id and data.device_id != "global":
        device = await db.devices.find_one({"id": data.device_id}, {"_id": 0})
        if not device:
            raise HTTPException(404, "Device not found")
            
    import random
    chars = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
    random_code = "".join(random.choice(chars) for _ in range(6))
    username = f"VC{random_code}"
    password = username
    doc = {
        "id": str(uuid.uuid4()),
        "username": username,
        "password": password,
        "profile": data.profile,
        "server": data.server,
        "price": data.price,
        "validity": data.validity,
        "comment": data.comment,
        "status": "new",
        "device_id": data.device_id,
        "created_at": datetime.now().isoformat()
    }
    await db.hotspot_vouchers.insert_one(doc)
    doc.pop("_id", None)
    return doc


# ── Sales Report ───────────────────────────────────────────────────────────────

@router.get("/hotspot-sales")
async def list_hotspot_sales(user=Depends(get_current_user)):
    """Menampilkan laporan penjualan voucher hotspot berdasarkan catatan autentikasi RADIUS."""
    db = get_db()
    sales = await db.hotspot_sales.find({}).sort("created_at", -1).to_list(1000)
    for s in sales:
        s["_id"] = str(s["_id"])
    return sales


# ── Basic CRUD ─────────────────────────────────────────────────────────────────

@router.put("/hotspot-users/{mt_id}")
async def update_hotspot_user(mt_id: str, device_id: str, data: HotspotUserUpdate, user=Depends(require_write)):
    mt, _ = await _get_mt_api(device_id)
    body = {k: v for k, v in data.model_dump().items() if v is not None}
    try:
        return await mt.update_hotspot_user(mt_id, body)
    except Exception as e:
        raise HTTPException(503, f"MikroTik: {e}")


@router.delete("/hotspot-users/{mt_id}")
async def delete_hotspot_user(mt_id: str, device_id: str, user=Depends(require_admin)):
    mt, _ = await _get_mt_api(device_id)
    try:
        return await mt.delete_hotspot_user(mt_id)
    except Exception as e:
        raise HTTPException(503, f"MikroTik: {e}")


@router.get("/hotspot-active")
async def list_hotspot_active(device_id: str, user=Depends(get_current_user)):
    mt, _ = await _get_mt_api(device_id)
    try:
        return await mt.list_hotspot_active()
    except Exception as e:
        raise HTTPException(503, f"MikroTik: {e}")


@router.get("/hotspot-profiles")
async def list_hotspot_profiles(device_id: str, user=Depends(get_current_user)):
    """List Hotspot user profiles from MikroTik."""
    if not device_id:
        return []
    try:
        mt, _ = await _get_mt_api(device_id)
        profiles = await mt.list_hotspot_profiles()
        return [
            {"name": p.get("name", ""), "rate_limit": p.get("rate-limit", p.get("rate_limit", "")),
             "shared_users": p.get("shared-users", ""), "comment": p.get("comment", "")}
            for p in profiles if p.get("name")
        ]
    except Exception as e:
        raise HTTPException(503, f"MikroTik: {e}")


@router.get("/hotspot-server-profiles")
async def list_hotspot_server_profiles(device_id: str, user=Depends(get_current_user)):
    """List Hotspot SERVER profiles (bukan user profile) beserta status use-radius dari MikroTik.
    Digunakan untuk dropdown server profile di konfigurasi RADIUS.
    Mendukung REST API (ROS 7+) dan Legacy API (ROS 6).
    """
    if not device_id:
        return []
    mt, _ = await _get_mt_api(device_id)
    import asyncio

    def _parse_profiles(raw_list):
        return [
            {
                "name": p.get("name", ""),
                "use_radius": str(p.get("use-radius", "no")).lower() in ("yes", "true"),
                "hotspot_address": p.get("hotspot-address", ""),
                "dns_name": p.get("dns-name", ""),
            }
            for p in (raw_list or []) if p.get("name")
        ]

    # Coba REST terlebih dahulu (hasattr _async_req = MikroTikRestAPI)
    if hasattr(mt, '_async_req'):
        try:
            profiles = await mt._async_req("GET", "ip/hotspot/profile")
            if isinstance(profiles, list):
                return _parse_profiles(profiles)
        except Exception:
            pass

    # Fallback ke Legacy API
    try:
        profiles = await asyncio.to_thread(mt._list_resource, "/ip/hotspot/profile")
        return _parse_profiles(profiles)
    except Exception as e:
        raise HTTPException(503, f"Gagal ambil server profiles: {e}")






@router.get("/hotspot-servers")
async def list_hotspot_servers(device_id: str, user=Depends(get_current_user)):
    """List Hotspot servers from MikroTik."""
    if not device_id:
        return []
    try:
        mt, _ = await _get_mt_api(device_id)
        servers = await mt.list_hotspot_servers()
        return [
            {"name": s.get("name", ""), "interface": s.get("interface", "")}
            for s in servers if s.get("name")
        ]
    except Exception as e:
        raise HTTPException(503, f"MikroTik: {e}")


# ── RADIUS Status & Push ───────────────────────────────────────────────────────

@router.get("/hotspot-radius-status")
async def get_radius_status(device_id: str, user=Depends(get_current_user)):
    """Cek status RADIUS di MikroTik: apakah use-radius aktif & daftar RADIUS client."""
    mt, device = await _get_mt_api(device_id)
    try:
        status = await mt.check_radius_enabled()
        return {"device_id": device_id, "device_name": device.get("name", ""), **status}
    except Exception as e:
        raise HTTPException(503, f"Gagal cek status RADIUS: {e}")


class PushRadiusRequest(BaseModel):
    device_id: str
    radius_ip: str
    secret: str
    server_profile: str = "hsprof1"

@router.post("/hotspot-push-radius")
async def push_radius_to_mikrotik(data: PushRadiusRequest, user=Depends(require_write)):
    """Push RADIUS client + aktifkan use-radius=yes di hotspot server profile."""
    mt, device = await _get_mt_api(data.device_id)
    try:
        # Save radius_secret to devices collection so the RADIUS server syncs it
        db = get_db()
        await db.devices.update_one(
            {"id": data.device_id},
            {"$set": {"radius_secret": data.secret}}
        )

        result = await mt.setup_hotspot_radius(
            radius_ip=data.radius_ip,
            secret=data.secret,
            server_profile=data.server_profile,
        )
        result["device_name"] = device.get("name", "")
        return result
    except Exception as e:
        raise HTTPException(503, f"Gagal push RADIUS config: {e}")


# ── Hotspot Settings (WA / N8N) — Terpisah dari PPPoE Billing ─────────────────

@router.get("/hotspot-settings")
async def get_hotspot_settings(user=Depends(get_current_user)):
    """Ambil pengaturan khusus Hotspot (WA template, N8N webhook, ZTP key)."""
    db = get_db()
    settings = await db.hotspot_settings.find_one({}, {"_id": 0}) or {}
    if settings.get("ztp_webhook_key"):
        settings["ztp_webhook_key_set"] = True
    return settings


class HotspotSettingsUpdate(BaseModel):
    radius_secret: Optional[str] = None
    radius_server_ip: Optional[str] = None
    ztp_webhook_key: Optional[str] = None
    n8n_webhook_url: Optional[str] = None
    n8n_voucher_api: Optional[str] = None
    wa_template_purchase: Optional[str] = None
    wa_template_voucher_sent: Optional[str] = None
    qris_image_url: Optional[str] = None
    # Kontak & Paket untuk Login Page
    wa_number: Optional[str] = None          # No WA Bot, format: 628xxxxxxxxxx
    packages: Optional[list] = None          # [{name, price, validity, profile}]
    # ── Pembayaran Captive Portal (Moota Bank Transfer) ──────────────────────
    payment_enabled: Optional[bool] = None   # Aktifkan fitur beli paket di portal
    bank_name: Optional[str] = None          # Contoh: "BCA"
    bank_account_number: Optional[str] = None # Contoh: "8520480189"
    bank_account_name: Optional[str] = None  # Contoh: "PT Arsya Barokah Abadi"
    payment_timeout_minutes: Optional[int] = None  # Default: 60 menit
    # ── Branding Portal ────────────────────────────────────────────────────────
    portal_title: Optional[str] = None       # Judul halaman login
    portal_subtitle: Optional[str] = None    # Tagline / deskripsi
    portal_color: Optional[str] = None       # Warna primer hex, misal: #6366f1

@router.post("/hotspot-settings")
async def save_hotspot_settings(data: HotspotSettingsUpdate, user=Depends(require_write)):
    """Simpan pengaturan Hotspot (WA/N8N/RADIUS/ZTP/Payment). Tidak tercampur dengan billing PPPoE."""
    db = get_db()
    update = {k: v for k, v in data.model_dump().items() if v is not None}
    if not update:
        raise HTTPException(400, "Tidak ada data yang diperbarui")
    await db.hotspot_settings.update_one({}, {"$set": update}, upsert=True)
    return {"message": "Pengaturan Hotspot disimpan", "updated_fields": list(update.keys())}


# ── Public Config (untuk Login Page — tidak perlu auth) ────────────────────────
# Endpoint ini harus masuk Walled Garden agar accessible sebelum login

DEFAULT_PACKAGES = [
    {"name": "1 Jam",    "price": "2000",  "validity": "1 Jam",   "profile": "default"},
    {"name": "3 Jam",    "price": "5000",  "validity": "3 Jam",   "profile": "default"},
    {"name": "1 Hari",   "price": "10000", "validity": "1 Hari",  "profile": "default"},
    {"name": "3 Hari",   "price": "25000", "validity": "3 Hari",  "profile": "default"},
    {"name": "1 Minggu", "price": "50000", "validity": "7 Hari",  "profile": "default"},
]

@router.get("/webhook/hotspot-public-config")
async def get_hotspot_public_config():
    """
    Endpoint PUBLIK (tanpa auth) untuk login page MikroTik.
    Kembalikan: no WA Bot + daftar paket voucher + info pembayaran Moota.
    Pastikan domain NOC Sentinel masuk ke Walled Garden MikroTik.
    """
    db = get_db()
    settings = await db.hotspot_settings.find_one({}, {"_id": 0}) or {}
    wa = settings.get("wa_number", "")
    if not wa or "x" in wa.lower():
        wa = "6282228304543"  # Fallback Arba Training

    # Info rekening bank untuk pembayaran (Moota)
    payment_enabled = settings.get("payment_enabled", False)
    bank_info = None
    if payment_enabled:
        bank_info = {
            "bank_name": settings.get("bank_name", ""),
            "account_number": settings.get("bank_account_number", ""),
            "account_name": settings.get("bank_account_name", ""),
        }
        # Jika rekening belum dikonfigurasi, nonaktifkan fitur beli
        if not bank_info["account_number"]:
            payment_enabled = False
            bank_info = None

    return {
        "wa_number": wa,
        "packages": settings.get("packages", DEFAULT_PACKAGES),
        "qris_image_url": settings.get("qris_image_url", ""),
        "payment_enabled": payment_enabled,
        "bank_info": bank_info,
        "payment_timeout_minutes": settings.get("payment_timeout_minutes", 60),
        "portal_title": settings.get("portal_title", ""),
        "portal_subtitle": settings.get("portal_subtitle", ""),
        "portal_color": settings.get("portal_color", ""),
    }


# ── Order Pembayaran Captive Portal (Moota Bank Transfer) ──────────────────────

class HotspotOrderRequest(BaseModel):
    package_name: str
    package_price: int
    package_profile: str = "default"
    package_validity: str = ""
    uptime_limit: str = ""
    device_id: Optional[str] = None      # Opsional: router tujuan
    customer_phone: Optional[str] = None # Opsional: No. WA untuk notifikasi setelah bayar

@router.post("/webhook/hotspot-create-order")
async def create_hotspot_order(data: HotspotOrderRequest):
    """
    Endpoint PUBLIK — buat order pembelian voucher dari Captive Portal.
    Menggunakan sistem kode unik Moota: pelanggan transfer tepat (harga + kode_unik).
    Voucher di-pre-generate dan dikembalikan SETELAH Moota konfirmasi bayar
    (via polling endpoint hotspot-order-status).
    """
    import random
    from datetime import datetime, timezone, timedelta
    db = get_db()
    settings = await db.hotspot_settings.find_one({}, {"_id": 0}) or {}

    # Validasi: fitur payment harus diaktifkan dan rekening bank sudah dikonfigurasi
    if not settings.get("payment_enabled"):
        raise HTTPException(403, "Fitur pembelian paket belum diaktifkan oleh admin.")
    if not settings.get("bank_account_number"):
        raise HTTPException(503, "Rekening bank belum dikonfigurasi.")

    # Validasi harga (minimal Rp 1.000)
    if data.package_price < 1000:
        raise HTTPException(400, "Harga paket tidak valid.")

    # Hitung kode unik Moota (1 – 500) — anti-collision sederhana
    # Coba sampai 20x agar tidak bentrok dengan order pending lain
    unique_code = random.randint(1, 500)
    for _ in range(20):
        candidate_total = data.package_price + unique_code
        conflict = await db.hotspot_invoices.find_one({
            "total": candidate_total,
            "status": "unpaid",
        })
        if not conflict:
            break
        unique_code = random.randint(1, 500)

    total = data.package_price + unique_code
    now_utc = datetime.now(timezone.utc)
    timeout_minutes = settings.get("payment_timeout_minutes", 60)
    expires_at = (now_utc + timedelta(minutes=timeout_minutes)).isoformat()

    # Pre-generate kode voucher (akan aktif setelah Moota webhook konfirmasi bayar)
    chars = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
    vc_user = "VC" + "".join(random.choice(chars) for _ in range(6))
    vc_pass = vc_user

    # Nomor invoice
    today = now_utc.astimezone().date()
    period_prefix = f"{today.year}-{today.month:02d}"
    count = await db.hotspot_invoices.count_documents(
        {"period_start": {"$regex": f"^{period_prefix}"}}
    )
    invoice_number = f"CPV-{today.year}-{today.month:02d}-{(count + 1):04d}"

    # Simpan invoice di hotspot_invoices (sama seperti WA AI CS)
    invoice_doc = {
        "id": str(uuid.uuid4()),
        "invoice_number": invoice_number,
        "customer_name": "Pelanggan Captive Portal",
        "customer_phone": (data.customer_phone or "").strip(),  # Dari input WA user di portal
        "customer_id": None,
        "package_id": "",
        "package_name": data.package_name,
        "profile_name": data.package_profile or "default",
        "uptime_limit": data.uptime_limit or "",
        "validity": data.package_validity or "",
        "amount": data.package_price,
        "discount": 0,
        "unique_code": unique_code,
        "total": total,
        "voucher_username": vc_user,
        "voucher_password": vc_pass,
        "voucher_sent": False,
        "device_id": data.device_id or "",
        "period_start": today.isoformat(),
        "period_end": today.isoformat(),
        "due_date": expires_at,
        "expires_at": expires_at,
        "status": "unpaid",
        "payment_method": None,
        "source": "captive_portal",
        "notes": f"Order dari Captive Portal — {data.package_name}",
        "created_at": now_utc.isoformat(),
        "updated_at": now_utc.isoformat(),
    }
    await db.hotspot_invoices.insert_one(invoice_doc)

    return {
        "order_id": invoice_doc["id"],
        "invoice_number": invoice_number,
        "package_name": data.package_name,
        "amount": data.package_price,
        "unique_code": unique_code,
        "total": total,
        "bank_name": settings.get("bank_name", ""),
        "account_number": settings.get("bank_account_number", ""),
        "account_name": settings.get("bank_account_name", ""),
        "expires_at": expires_at,
        "timeout_minutes": timeout_minutes,
        "status": "unpaid",
    }


@router.get("/webhook/hotspot-order-status/{order_id}")
async def get_hotspot_order_status(order_id: str):
    """
    Endpoint PUBLIK — polling status order dari Captive Portal.
    Dipanggil setiap 3 detik oleh login.html setelah order dibuat.
    Jika sudah PAID → kembalikan kode voucher agar portal bisa tampilkan.
    """
    from datetime import datetime, timezone
    db = get_db()
    inv = await db.hotspot_invoices.find_one({"id": order_id}, {"_id": 0})
    if not inv:
        raise HTTPException(404, "Order tidak ditemukan.")

    now_utc = datetime.now(timezone.utc)
    status = inv.get("status", "unpaid")

    # Cek apakah order sudah expired
    expires_at_str = inv.get("expires_at") or inv.get("due_date", "")
    if status == "unpaid" and expires_at_str:
        try:
            exp = datetime.fromisoformat(expires_at_str.replace("Z", "+00:00"))
            if exp.tzinfo is None:
                exp = exp.replace(tzinfo=timezone.utc)
            if now_utc > exp:
                status = "expired"
                await db.hotspot_invoices.update_one(
                    {"id": order_id}, {"$set": {"status": "expired"}}
                )
        except Exception:
            pass

    response = {
        "order_id": order_id,
        "status": status,  # "unpaid" | "paid" | "expired"
        "invoice_number": inv.get("invoice_number", ""),
        "package_name": inv.get("package_name", ""),
        "total": inv.get("total", 0),
        "expires_at": expires_at_str,
    }

    # Jika sudah dibayar → sertakan kode voucher
    if status == "paid":
        response["voucher_code"] = inv.get("voucher_username", "")
        response["voucher_password"] = inv.get("voucher_password", "")
        response["paid_at"] = inv.get("paid_at", "")

    return response

# ── Walled Garden ──────────────────────────────────────────────────────────────

DEFAULT_WALLED_GARDEN = [
    {"dst-host": "wa.me",                "comment": "WhatsApp Short Link"},
    {"dst-host": "*.whatsapp.net",       "comment": "WhatsApp — Bot"},
    {"dst-host": "*.whatsapp.com",       "comment": "WhatsApp — Bot"},
    {"dst-host": "*.fb.me",              "comment": "Meta — Handshake"},
    {"dst-host": "*.facebook.net",       "comment": "Meta — Handshake"},
    {"dst-host": "*.facebook.com",       "comment": "Meta — Handshake"},
    {"dst-host": "*.fbcdn.net",          "comment": "WhatsApp CDN"},
    {"dst-host": "*.cdn.whatsapp.net",   "comment": "WhatsApp CDN"},
    {"dst-host": "*.g.whatsapp.net",     "comment": "WhatsApp Chat Server"},
    {"dst-host": "*.v.whatsapp.net",     "comment": "WhatsApp Chat Server"},
    {"dst-host": "*.mmg.whatsapp.net",   "comment": "WhatsApp Media Server"},
    {"dst-host": "*.d.whatsapp.net",     "comment": "WhatsApp Chat Server"},
    {"dst-host": "web.whatsapp.com",     "comment": "WhatsApp Web"},
    # Meta / WhatsApp IP Ranges (CIDR) — Untuk Mengatasi status "Connecting..."
    {"dst-address": "157.240.0.0/16",    "comment": "Meta Core IP"},
    {"dst-address": "129.134.0.0/16",    "comment": "Meta Core IP"},
    {"dst-address": "173.252.64.0/18",   "comment": "Meta Core IP"},
    {"dst-address": "185.60.216.0/22",   "comment": "Meta Core IP"},
    {"dst-address": "69.171.224.0/19",   "comment": "Meta Analytics"},
    {"dst-address": "66.220.144.0/20",   "comment": "FB/Meta IP"},
    {"dst-host": "alir1.arbatraining.com", "comment": "NOC-Sentinel API Server"},
    {"dst-host": "fonts.googleapis.com", "comment": "Google Fonts CSS"},
    {"dst-host": "fonts.gstatic.com",    "comment": "Google Fonts Static"},
    {"dst-host": "*.google-analytics.com", "comment": "Google Analytics"},
    {"dst-host": "*.googletagmanager.com", "comment": "Google Tag Manager"},
    {"dst-host": "*.klikbca.com",        "comment": "KlikBCA Mobile"},
    {"dst-host": "*.bca.co.id",          "comment": "BCA Mobile"},
    {"dst-host": "*.bni.co.id",          "comment": "BNI Mobile"},
    {"dst-host": "*.bri.co.id",          "comment": "BRImo"},
    {"dst-host": "*.mandiri.co.id",      "comment": "Mandiri Online"},
    {"dst-host": "*.dana.id",            "comment": "DANA e-wallet"},
    {"dst-host": "*.gopay.co.id",        "comment": "GoPay e-wallet"},
    {"dst-host": "qris.online",          "comment": "QRIS Gateway"},
    {"dst-host": "*.linkaja.id",         "comment": "LinkAja"},
]


@router.get("/hotspot-walled-garden-defaults")
async def get_walled_garden_defaults(user=Depends(get_current_user)):
    """Kembalikan daftar domain default Walled Garden (WA + perbankan + QRIS)."""
    return DEFAULT_WALLED_GARDEN


@router.get("/hotspot-walled-garden")
async def list_walled_garden(device_id: str, user=Depends(get_current_user)):
    """List semua Walled Garden entries yang sudah ada di MikroTik."""
    mt, _ = await _get_mt_api(device_id)
    try:
        return await mt.list_walled_garden()
    except Exception as e:
        raise HTTPException(503, f"Gagal ambil Walled Garden: {e}")


class PushWalledGardenRequest(BaseModel):
    device_id: str
    entries: Optional[list] = None      # None = pakai DEFAULT_WALLED_GARDEN
    custom_hosts: Optional[list] = None  # Domain tambahan (misal URL N8N)
    server: str = "all"


@router.post("/hotspot-push-walled-garden")
async def push_walled_garden(data: PushWalledGardenRequest, user=Depends(require_write)):
    """
    Push Walled Garden rules ke MikroTik secara batch.
    - entries = None  → pakai DEFAULT_WALLED_GARDEN (WA + bank + QRIS).
    - custom_hosts    → domain tambahan (misal domain N8N server).
    - Skip otomatis jika entry sudah ada — aman dijalankan berulang kali.
    """
    mt, device = await _get_mt_api(data.device_id)
    entries_to_push = list(data.entries) if data.entries is not None else DEFAULT_WALLED_GARDEN.copy()
    if data.custom_hosts:
        for h in data.custom_hosts:
            if h and h.strip():
                entries_to_push.append({"host": h.strip(), "comment": "Custom — NOC-Sentinel"})
    try:
        result = await mt.setup_walled_garden(entries=entries_to_push, server=data.server)
        result["device_name"] = device.get("name", "")
        result["total_entries"] = len(entries_to_push)
        return result
    except Exception as e:
        raise HTTPException(503, f"Gagal push Walled Garden: {e}")


@router.delete("/hotspot-walled-garden/{mt_id}")
async def delete_walled_garden_entry(mt_id: str, device_id: str, user=Depends(require_write)):
    """Hapus satu entry Walled Garden dari MikroTik berdasarkan .id"""
    mt, _ = await _get_mt_api(device_id)
    try:
        return await mt._async_req("DELETE", f"ip/hotspot/walled-garden/{mt_id}")
    except Exception as e:
        raise HTTPException(503, f"Gagal hapus entry: {e}")
