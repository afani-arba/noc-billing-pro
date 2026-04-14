"""
Admin users router: Full CRUD + session management + activity log for system users.
"""
import uuid
from fastapi import APIRouter, HTTPException, Depends, Query
from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime, timezone
from core.db import get_db
from core.auth import (
    require_admin, pwd_context, VALID_ROLES, ROLE_DEFAULT_SERVICES, ALL_SERVICES
)

router = APIRouter(prefix="/admin", tags=["admin"])


class UserCreate(BaseModel):
    username: str
    password: str
    full_name: str
    role: str = "noc_engineer"
    allowed_devices: List[str] = []
    allowed_services: Optional[List[str]] = None  # None = use role defaults
    telegram_chat_id: Optional[str] = None
    is_active: bool = True


class UserUpdate(BaseModel):
    full_name: Optional[str] = None
    role: Optional[str] = None
    password: Optional[str] = None
    allowed_devices: Optional[List[str]] = None
    allowed_services: Optional[List[str]] = None
    telegram_chat_id: Optional[str] = None
    is_active: Optional[bool] = None


def _clean_user(doc: dict) -> dict:
    """Remove sensitive fields before returning to client."""
    return {k: v for k, v in doc.items() if k not in ("_id", "password")}


@router.get("/users")
async def list_admin_users(user=Depends(require_admin)):
    db = get_db()
    users = await db.admin_users.find({}, {"_id": 0, "password": 0}).to_list(200)
    return users


@router.post("/users", status_code=201)
async def create_admin_user(data: UserCreate, user=Depends(require_admin)):
    db = get_db()

    if await db.admin_users.find_one({"username": data.username}):
        raise HTTPException(400, "Username sudah digunakan")
    if data.role not in VALID_ROLES:
        raise HTTPException(400, f"Role tidak valid. Pilih salah satu: {', '.join(VALID_ROLES)}")

    # Use role defaults for allowed_services if not explicitly set
    services = data.allowed_services if data.allowed_services is not None else ROLE_DEFAULT_SERVICES.get(data.role, [])

    doc = {
        "id": str(uuid.uuid4()),
        "username": data.username,
        "password": pwd_context.hash(data.password),
        "full_name": data.full_name,
        "role": data.role,
        "allowed_devices": data.allowed_devices,
        "allowed_services": services,
        "telegram_chat_id": data.telegram_chat_id,
        "is_active": data.is_active,
        "last_login": None,
        "last_login_ip": None,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "created_by": user.get("username", ""),
    }
    await db.admin_users.insert_one(doc)

    # Audit log
    try:
        from routers.audit import log_action
        await log_action(
            action="CREATE", resource="admin_users", resource_id=doc["id"],
            details=f"Created user '{data.username}' with role '{data.role}'",
            username=user.get("username", ""), user_id=user.get("id", ""),
        )
    except Exception:
        pass

    return _clean_user(doc)


@router.put("/users/{user_id}")
async def update_admin_user(user_id: str, data: UserUpdate, user=Depends(require_admin)):
    db = get_db()

    upd = {}
    if data.full_name is not None:
        upd["full_name"] = data.full_name
    if data.role is not None:
        if data.role not in VALID_ROLES:
            raise HTTPException(400, f"Role tidak valid. Pilih salah satu: {', '.join(VALID_ROLES)}")
        upd["role"] = data.role
        # If role changed and no explicit services given, reset to role defaults
        if data.allowed_services is None:
            upd["allowed_services"] = ROLE_DEFAULT_SERVICES.get(data.role, [])
    if data.password is not None:
        upd["password"] = pwd_context.hash(data.password)
    if data.allowed_devices is not None:
        upd["allowed_devices"] = data.allowed_devices
    if data.allowed_services is not None:
        upd["allowed_services"] = data.allowed_services
    if data.telegram_chat_id is not None:
        upd["telegram_chat_id"] = data.telegram_chat_id
    if data.is_active is not None:
        upd["is_active"] = data.is_active

    if not upd:
        raise HTTPException(400, "Tidak ada perubahan untuk disimpan")

    upd["updated_at"] = datetime.now(timezone.utc).isoformat()
    upd["updated_by"] = user.get("username", "")

    r = await db.admin_users.update_one({"id": user_id}, {"$set": upd})
    if r.matched_count == 0:
        raise HTTPException(404, "User tidak ditemukan")

    # Audit log
    try:
        from routers.audit import log_action
        changed = [k for k in upd if k not in ("password", "updated_at", "updated_by")]
        target = await db.admin_users.find_one({"id": user_id}, {"_id": 0, "username": 1})
        await log_action(
            action="UPDATE", resource="admin_users", resource_id=user_id,
            details=f"Updated user '{target.get('username', user_id)}': {', '.join(changed)}",
            username=user.get("username", ""), user_id=user.get("id", ""),
        )
    except Exception:
        pass

    result = await db.admin_users.find_one({"id": user_id}, {"_id": 0, "password": 0})
    return result


@router.delete("/users/{user_id}")
async def delete_admin_user(user_id: str, user=Depends(require_admin)):
    db = get_db()
    target = await db.admin_users.find_one({"id": user_id}, {"_id": 0})
    if not target:
        raise HTTPException(404, "User tidak ditemukan")
    if target["id"] == user["id"]:
        raise HTTPException(400, "Tidak dapat menghapus akun sendiri")

    await db.admin_users.delete_one({"id": user_id})

    # Audit log
    try:
        from routers.audit import log_action
        await log_action(
            action="DELETE", resource="admin_users", resource_id=user_id,
            details=f"Deleted user '{target.get('username', user_id)}'",
            username=user.get("username", ""), user_id=user.get("id", ""),
        )
    except Exception:
        pass

    return {"message": "User berhasil dihapus"}


@router.post("/users/{user_id}/toggle-active")
async def toggle_user_active(user_id: str, user=Depends(require_admin)):
    """Aktifkan / nonaktifkan akun user tanpa menghapusnya."""
    db = get_db()
    target = await db.admin_users.find_one({"id": user_id}, {"_id": 0, "is_active": 1, "username": 1})
    if not target:
        raise HTTPException(404, "User tidak ditemukan")
    if target["id"] == user["id"] if "id" in target else user_id == user["id"]:
        raise HTTPException(400, "Tidak dapat menonaktifkan akun sendiri")

    new_state = not target.get("is_active", True)
    await db.admin_users.update_one(
        {"id": user_id},
        {"$set": {"is_active": new_state, "updated_at": datetime.now(timezone.utc).isoformat()}}
    )

    try:
        from routers.audit import log_action
        action_label = "diaktifkan" if new_state else "dinonaktifkan"
        await log_action(
            action="UPDATE", resource="admin_users", resource_id=user_id,
            details=f"Akun '{target.get('username', user_id)}' {action_label}",
            username=user.get("username", ""), user_id=user.get("id", ""),
        )
    except Exception:
        pass

    return {"is_active": new_state, "message": f"Akun {'diaktifkan' if new_state else 'dinonaktifkan'}"}


@router.post("/users/{user_id}/revoke-sessions")
async def revoke_user_sessions(user_id: str, user=Depends(require_admin)):
    """
    Force logout: simpan user_id ke collection 'revoked_sessions'.
    Setiap request akan dicek apakah user_id ada di koleksi ini.
    Token akan expired pada TTL berikutnya (default 24 jam).
    """
    db = get_db()
    target = await db.admin_users.find_one({"id": user_id}, {"_id": 0, "username": 1})
    if not target:
        raise HTTPException(404, "User tidak ditemukan")
    if user_id == user.get("id"):
        raise HTTPException(400, "Tidak dapat mencabut sesi sendiri")

    # Tandai semua sesi sebagai revoked
    await db.revoked_sessions.update_one(
        {"user_id": user_id},
        {"$set": {
            "user_id": user_id,
            "revoked_at": datetime.now(timezone.utc).isoformat(),
            "revoked_by": user.get("username", ""),
        }},
        upsert=True
    )

    try:
        from routers.audit import log_action
        await log_action(
            action="UPDATE", resource="admin_users", resource_id=user_id,
            details=f"Force logout / revoke sessions: '{target.get('username', user_id)}'",
            username=user.get("username", ""), user_id=user.get("id", ""),
        )
    except Exception:
        pass

    return {"message": f"Sesi user '{target.get('username')}' telah dicabut. Mereka akan otomatis logout."}


@router.get("/users/{user_id}/activity")
async def get_user_activity(
    user_id: str,
    limit: int = Query(50, ge=1, le=200),
    user=Depends(require_admin)
):
    """Ambil riwayat audit log untuk user tertentu."""
    db = get_db()
    target = await db.admin_users.find_one({"id": user_id}, {"_id": 0, "username": 1})
    if not target:
        raise HTTPException(404, "User tidak ditemukan")

    logs = await db.audit_logs.find(
        {"user_id": user_id}, {"_id": 0}
    ).sort("timestamp", -1).limit(limit).to_list(limit)

    return {"username": target.get("username"), "logs": logs, "total": len(logs)}


@router.get("/active-sessions")
async def list_active_sessions(user=Depends(require_admin)):
    """
    List approximate active sessions: users with last_login dalam 24 jam terakhir
    dan tidak ada revoked session.
    """
    db = get_db()
    from datetime import timedelta
    cutoff = (datetime.now(timezone.utc) - timedelta(hours=24)).isoformat()

    users = await db.admin_users.find(
        {"last_login": {"$gte": cutoff}, "is_active": {"$ne": False}},
        {"_id": 0, "password": 0}
    ).to_list(200)

    revoked = await db.revoked_sessions.find({}, {"_id": 0, "user_id": 1}).to_list(200)
    revoked_ids = {r["user_id"] for r in revoked}

    sessions = []
    for u in users:
        sessions.append({
            "user_id": u.get("id"),
            "username": u.get("username"),
            "full_name": u.get("full_name"),
            "role": u.get("role"),
            "last_login": u.get("last_login"),
            "last_login_ip": u.get("last_login_ip"),
            "is_revoked": u.get("id") in revoked_ids,
        })

    return sessions


@router.get("/roles-config")
async def get_roles_config(user=Depends(require_admin)):
    """Return available roles and their default services for frontend form."""
    return {
        "valid_roles": VALID_ROLES,
        "all_services": ALL_SERVICES,
        "role_defaults": {r: ROLE_DEFAULT_SERVICES.get(r, []) for r in VALID_ROLES},
        "role_info": {
            "super_admin":    {"label": "Super Admin",     "color": "red",    "desc": "Akses penuh ke semua fitur, pengaturan lisensi dan sistem"},
            "administrator":  {"label": "Administrator",   "color": "red",    "desc": "Akses penuh (alias super_admin, backward-compatible)"},
            "noc_engineer":   {"label": "NOC Engineer",    "color": "orange", "desc": "Full monitoring & routing, tidak bisa akses Billing/Keuangan"},
            "billing_staff":  {"label": "Billing Staff",   "color": "green",  "desc": "Full Billing & Laporan Keuangan, tidak bisa konfigurasi router"},
            "helpdesk":       {"label": "Helpdesk / CS",   "color": "blue",   "desc": "Read-only monitoring + daftar pelanggan, tidak bisa ubah data"},
            "viewer":         {"label": "Viewer (Legacy)", "color": "gray",   "desc": "Read-only semua halaman monitoring (alias helpdesk)"},
        }
    }
