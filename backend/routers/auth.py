"""
Auth router: login and get current user.
"""
import time
from fastapi import APIRouter, HTTPException, Depends, Request
from pydantic import BaseModel
from core.db import get_db
from core.auth import create_token, get_current_user, pwd_context, VALID_ROLES
from datetime import datetime, timezone

router = APIRouter(prefix="/auth", tags=["auth"])

# ── Rate Limiter (Brute-Force Protection) ─────────────────────────────────────
# In-memory store:
#   _login_attempts : {ip: [timestamp, ...]}  — sliding window counter
#   _lockout_until  : {ip: timestamp}          — hard lockout after limit exceeded
_login_attempts: dict = {}
_lockout_until:  dict = {}
_RATE_LIMIT_MAX    = 5      # maks percobaan gagal dalam window
_RATE_LIMIT_WINDOW = 60     # detik sliding window
_LOCKOUT_DURATION  = 300    # detik lockout setelah limit terlampaui (5 menit)


def _check_rate_limit(ip: str) -> None:
    """
    Raise HTTP 429 jika IP:
      - Sedang dalam masa lockout (5 menit setelah burst), ATAU
      - Telah melakukan >= _RATE_LIMIT_MAX percobaan dalam _RATE_LIMIT_WINDOW detik.
    """
    now = time.time()

    # 1. Cek hard lockout
    lockout_exp = _lockout_until.get(ip, 0)
    if now < lockout_exp:
        retry_after = int(lockout_exp - now)
        raise HTTPException(
            status_code=429,
            detail=f"Terlalu banyak percobaan login. IP diblokir selama {retry_after} detik lagi.",
            headers={"Retry-After": str(retry_after)},
        )

    # 2. Sliding window — buang timestamp di luar window
    window_start = now - _RATE_LIMIT_WINDOW
    timestamps = [t for t in _login_attempts.get(ip, []) if t > window_start]

    if len(timestamps) >= _RATE_LIMIT_MAX:
        # Aktifkan lockout penuh
        _lockout_until[ip] = now + _LOCKOUT_DURATION
        _login_attempts.pop(ip, None)
        raise HTTPException(
            status_code=429,
            detail=f"Terlalu banyak percobaan login. IP diblokir selama {_LOCKOUT_DURATION // 60} menit.",
            headers={"Retry-After": str(_LOCKOUT_DURATION)},
        )

    timestamps.append(now)
    _login_attempts[ip] = timestamps

    # 3. Bersihkan IP kadaluarsa dari memory (max 2000 entry)
    if len(_login_attempts) > 2000:
        stale = [k for k, v in _login_attempts.items() if not any(t > window_start for t in v)]
        for k in stale:
            del _login_attempts[k]
    if len(_lockout_until) > 2000:
        expired = [k for k, exp in _lockout_until.items() if now >= exp]
        for k in expired:
            del _lockout_until[k]


def _clear_rate_limit(ip: str) -> None:
    """Hapus counter login setelah login berhasil agar tidak salah blokir."""
    _login_attempts.pop(ip, None)
    _lockout_until.pop(ip, None)


class UserLogin(BaseModel):
    username: str
    password: str


@router.post("/login")
async def login(data: UserLogin, request: Request = None):
    ip = request.client.host if request and request.client else "unknown"
    _check_rate_limit(ip)
    db = get_db()
    user = await db.admin_users.find_one({"username": data.username})
    if not user or not pwd_context.verify(data.password, user.get("password", "")):
        raise HTTPException(401, "Username atau password salah")

    # Cek apakah akun dinonaktifkan
    if user.get("is_active") is False:
        raise HTTPException(403, "Akun Anda telah dinonaktifkan. Hubungi administrator.")

    # Login berhasil — bersihkan rate limit counter
    _clear_rate_limit(ip)

    # FIX: Legacy users from v2 might not have 'id' or 'role'
    needs_update = False
    upd_auth = {}
    if "id" not in user:
        import uuid
        user["id"] = str(uuid.uuid4())
        upd_auth["id"] = user["id"]
        needs_update = True
    if "role" not in user:
        user["role"] = "administrator"
        upd_auth["role"] = user["role"]
        needs_update = True
    if "is_active" not in user:
        upd_auth["is_active"] = True
        needs_update = True

    # Selalu update last_login dan last_login_ip
    now_str = datetime.now(timezone.utc).isoformat()
    upd_auth["last_login"] = now_str
    upd_auth["last_login_ip"] = ip
    needs_update = True

    if needs_update:
        await db.admin_users.update_one({"_id": user["_id"]}, {"$set": upd_auth})
        user["last_login"] = now_str
        user["last_login_ip"] = ip

    # Remove ObjectId so it's JSON serializable
    user.pop("_id", None)

    # Audit log: LOGIN event
    try:
        from routers.audit import log_action
        ip = request.client.host if request and request.client else ""
        await log_action(
            action="LOGIN",
            resource="auth",
            details=f"User '{data.username}' logged in",
            username=data.username,
            user_id=str(user.get("id", "")),
            ip_address=ip,
        )
    except Exception:
        pass

    return {"token": create_token(user), "user": {k: v for k, v in user.items() if k != "password"}}




@router.get("/me")
async def get_me(user=Depends(get_current_user)):
    return {k: v for k, v in user.items() if k != "password"}
