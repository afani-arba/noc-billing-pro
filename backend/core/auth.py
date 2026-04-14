"""
Auth helpers: JWT creation, dependency injection for route protection.

Role Definitions:
  super_admin   - Full access to everything (previously: administrator)
  administrator - Alias for super_admin (backward-compatible)
  noc_engineer  - Full monitoring + network config, BLOCKED from billing
  billing_staff - Full billing access, BLOCKED from network config
  helpdesk      - Read-only access to monitoring + customer list
  viewer        - Legacy alias for helpdesk
"""
import os
import jwt
from fastapi import Depends, HTTPException, Request
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from passlib.context import CryptContext
from datetime import datetime, timezone, timedelta
from core.db import get_db

import warnings

security = HTTPBearer()
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

JWT_SECRET = os.environ.get("JWT_SECRET") or os.environ.get("SECRET_KEY")
if not JWT_SECRET:
    if os.environ.get("DEV_MODE", "").strip() == "1":
        JWT_SECRET = "dev_secret_do_not_use_in_production"
        warnings.warn(
            "[DEV_MODE] JWT_SECRET not set! Using insecure placeholder. "
            "Set JWT_SECRET in .env before deploying.",
            UserWarning,
            stacklevel=2,
        )
    else:
        raise RuntimeError(
            "JWT_SECRET (or SECRET_KEY) environment variable must be set. "
            "Generate one dengan: python -c \"import secrets; print(secrets.token_hex(32))\" "
            "lalu tambahkan ke file .env"
        )

# ── Role Constants ─────────────────────────────────────────────────────────
VALID_ROLES = ["super_admin", "administrator", "noc_engineer", "billing_staff", "helpdesk", "viewer"]

# Groups untuk kemudahan pengecekan
ADMIN_ROLES      = {"super_admin", "administrator"}
NOC_ROLES        = {"super_admin", "administrator", "noc_engineer"}
BILLING_ROLES    = {"super_admin", "administrator", "billing_staff"}
READONLY_ROLES   = {"super_admin", "administrator", "noc_engineer", "billing_staff", "helpdesk", "viewer"}

# Services yang bisa di-assign per user
ALL_SERVICES = [
    "dashboard", "pppoe", "hotspot", "reports", "devices",
    "bgp", "routing", "sdwan", "traffic_flow", "genieacs",
    "wallboard", "bandwidth", "topology", "sla", "incidents",
    "peering_eye", "looking_glass", "netwatch",
    "billing", "hotspot_billing", "finance_report",
    "notifications", "backups", "scheduler", "syslog",
    "audit", "settings", "integration_settings", "update",
    "ping", "wa_customer_service", "radius_server", "license",
]

# Default services per role
ROLE_DEFAULT_SERVICES = {
    "super_admin":    ALL_SERVICES,
    "administrator":  ALL_SERVICES,
    "noc_engineer":   [
        "dashboard", "pppoe", "hotspot", "reports", "devices",
        "bgp", "routing", "sdwan", "genieacs",
        "wallboard", "topology", "sla", "incidents",
        "peering_eye", "ping", "audit",
    ],
    "billing_staff":  [
        "dashboard", "pppoe", "hotspot", "reports",
        "billing", "hotspot_billing", "finance_report",
        "wa_customer_service"
    ],
    "helpdesk":       [
        "dashboard", "pppoe", "hotspot", "reports",
        "wallboard", "incidents", "sla",
    ],
    "viewer":         [
        "dashboard", "pppoe", "hotspot", "reports",
        "wallboard", "topology", "sla", "incidents", "ping",
    ],
}


def create_token(user_data: dict) -> str:
    expire_minutes = int(os.environ.get("ACCESS_TOKEN_EXPIRE_MINUTES", "1440"))
    return jwt.encode(
        {
            "sub": user_data["id"],
            "username": user_data["username"],
            "role": user_data["role"],
            "exp": datetime.now(timezone.utc) + timedelta(minutes=expire_minutes),
        },
        JWT_SECRET,
        algorithm="HS256",
    )


async def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(security)):
    db = get_db()
    try:
        payload = jwt.decode(credentials.credentials, JWT_SECRET, algorithms=["HS256"])
        user = await db.admin_users.find_one({"id": payload["sub"]}, {"_id": 0})
        if not user:
            raise HTTPException(status_code=401, detail="User not found")
        # Enforce is_active flag
        if user.get("is_active") is False:
            raise HTTPException(status_code=403, detail="Akun dinonaktifkan. Hubungi administrator.")
        return user
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token expired")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid token")


def decode_token(token: str) -> dict | None:
    """
    Decode JWT token tanpa DB lookup — untuk SSE endpoint yang tidak bisa
    menggunakan Depends(get_current_user) karena EventSource tidak support headers.
    """
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=["HS256"])
        return payload
    except Exception:
        return None


def _is_admin(user: dict) -> bool:
    """Return True if user is super_admin or administrator."""
    return user.get("role") in ADMIN_ROLES


# ── Role-based dependency injectors ───────────────────────────────────────

async def require_admin(request: Request, user=Depends(get_current_user)):
    """Requires administrator, but bypasses if custom allowed_services is granted for admin module."""
    if request.method in ["POST", "PUT", "DELETE", "PATCH"] and user.get("role") in {"helpdesk", "viewer"}:
        raise HTTPException(status_code=403, detail="Role Read-Only tidak dapat memodifikasi data.")

    if not _is_admin(user):
        explicit = user.get("allowed_services")
        if explicit is not None:
            admin_services = {"settings", "integration_settings", "update", "license", "radius_server", "audit", "backups", "syslog", "scheduler", "notifications", "wa_customer_service"}
            if set(explicit) & admin_services:
                return user
        raise HTTPException(status_code=403, detail="Admin access required")
    return user


async def require_super_admin(request: Request, user=Depends(get_current_user)):
    """Strict: only super_admin or administrator."""
    if request.method in ["POST", "PUT", "DELETE", "PATCH"] and user.get("role") in {"helpdesk", "viewer"}:
        raise HTTPException(status_code=403, detail="Role Read-Only tidak dapat memodifikasi data.")

    if not _is_admin(user):
        raise HTTPException(status_code=403, detail="Super admin access required")
    return user


async def require_noc(request: Request, user=Depends(get_current_user)):
    """NOC operations: bypasses strict role if NOC custom services exist."""
    if request.method in ["POST", "PUT", "DELETE", "PATCH"] and user.get("role") in {"helpdesk", "viewer"}:
        raise HTTPException(status_code=403, detail="Role Read-Only tidak dapat memodifikasi data.")

    if user.get("role") not in NOC_ROLES:
        explicit = user.get("allowed_services")
        if explicit is not None:
             noc_services = {"dashboard", "pppoe", "hotspot", "reports", "devices", "bgp", "routing", "sdwan", "genieacs", "wallboard", "topology", "sla", "incidents", "peering_eye", "ping"}
             if set(explicit) & noc_services:
                 return user
        raise HTTPException(
            status_code=403,
            detail="Akses ditolak. Fitur ini membutuhkan role NOC Engineer atau akses kustom."
        )
    return user


async def require_billing(request: Request, user=Depends(get_current_user)):
    """Billing operations: bypasses strict role if billing custom services exist."""
    if request.method in ["POST", "PUT", "DELETE", "PATCH"] and user.get("role") in {"helpdesk", "viewer"}:
        raise HTTPException(status_code=403, detail="Role Read-Only tidak dapat memodifikasi data.")

    if user.get("role") not in BILLING_ROLES:
        explicit = user.get("allowed_services")
        if explicit is not None:
            billing_services = {"billing", "hotspot_billing", "finance_report"}
            if set(explicit) & billing_services:
                return user
        raise HTTPException(
            status_code=403,
            detail="Akses ditolak. Fitur ini membutuhkan role Billing Staff atau akses kustom."
        )
    return user


async def require_write(user=Depends(get_current_user)):
    """Write permission: completely blocks read-only roles (viewer/helpdesk) from modifying data."""
    if user.get("role") in {"helpdesk", "viewer"}:
        raise HTTPException(status_code=403, detail="Role Read-Only tidak dapat memodifikasi data.")
    return user


async def require_enterprise(user=Depends(get_current_user)):
    """
    Pastikan aplikasi berjalan dalam edisi Enterprise.
    Dipakai sebagai guard untuk semua endpoint Billing, Customer, Finance.
    Jika edisi PRO, return 403 dengan keterangan yang jelas.
    """
    from core.edition import is_enterprise
    if not is_enterprise():
        raise HTTPException(
            status_code=403,
            detail=(
                "Fitur Billing & Manajemen Pelanggan hanya tersedia di edisi "
                "NOC-Sentinel Enterprise. Upgrade lisensi Anda untuk mengakses fitur ini."
            ),
        )
    return user



def check_device_access(user: dict, device_id: str) -> bool:
    """
    Return True if user is allowed to access this device.
    super_admin / administrator always allowed.
    Other roles: must have device_id in allowed_devices list.
    """
    if _is_admin(user):
        return True
    allowed = user.get("allowed_devices", [])
    return device_id in allowed


def get_user_services(user: dict) -> set:
    """
    Return set of service names the user can access.
    Uses explicit allowed_services if set, falls back to role defaults.
    """
    if _is_admin(user):
        return set(ALL_SERVICES)
    explicit = user.get("allowed_services")
    if explicit:
        return set(explicit)
    role = user.get("role", "viewer")
    return set(ROLE_DEFAULT_SERVICES.get(role, []))
