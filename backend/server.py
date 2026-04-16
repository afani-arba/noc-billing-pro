"""
NOC-Billing-Pro Backend — Entry Point

Edition : BILLING PRO (Enterprise subset dengan GenieACS + Peering Eye)
Features:
  1.  Dashboard Interface
  2.  Device Hub
  3.  GenieACS + ZTP (TR-069)
  4.  RADIUS Server
  5.  Billing PPPoE
  6.  Billing Hotspot
  7.  Laporan Keuangan
  8.  CS Command Center (WA)
  9.  Portal Pelanggan
  10. Sentinel Peering Eye
  11. BGP Content Steering
  12. Pengaturan Platform
  13. Integrasi & Otomasi
  14. User Management
  15. Update Aplikasi
  16. Lisensi Sistem

Router TIDAK disertakan:
  - SD-WAN / SDWAN Page
  - OSPF / Routing Monitor
  - Network Topology
  - SLA Monitor
  - Incidents
  - Ping Tool / Network Tools
"""
import os
import asyncio
import logging
from contextlib import asynccontextmanager
from pathlib import Path
from dotenv import load_dotenv
from fastapi import FastAPI
from starlette.middleware.cors import CORSMiddleware

ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / ".env")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

from core.db import init_db
init_db()

from core.edition import EDITION, EDITION_NAME, is_enterprise, FEATURES

# ── Routers ────────────────────────────────────────────────────────────────
from fastapi import APIRouter
from routers.auth import router as auth_router
from routers.devices import router as devices_router
from routers.pppoe import router as pppoe_router
from routers.hotspot import router as hotspot_router
from routers.billing import router as billing_router, webhook_router as billing_webhook_router
from routers.customers import router as customers_router
from routers.client_portal import router as client_portal_router
from routers.reports import router as reports_router
from routers.admin import router as admin_router
from routers.system import router as system_router
from routers.notifications import router as notifications_router
from routers.backups import router as backups_router
from routers.syslog import router as syslog_router
from routers.metrics import router as metrics_router
from routers.audit import router as audit_router
from routers.events import router as events_router
from routers.scheduler import router as scheduler_router
from routers.speedtest import router as speedtest_router
from routers.routing_alerts import router as routing_alerts_router
from routers.license import router as license_router
from routers.wallboard import router as wallboard_router
from routers.wa_customer_service import router as wa_cs_router
# 3. GenieACS + ZTP
from routers.genieacs import router as genieacs_router
# 10. Sentinel Peering Eye (includes BGP Content Steering)
from routers.peering_eye import router as peering_eye_router
# Payment Gateway Voucher PDF
from routers.voucher_pdf import router as voucher_pdf_router

_background_tasks: list = []


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("=" * 65)
    logger.info("  🚀  NOC-Billing-Pro v1.0 — Starting up")
    logger.info("       Edition  : BILLING PRO (Enterprise subset)")
    logger.info("       GenieACS : ENABLED (ZTP + TR-069)")
    logger.info("       Peering  : ENABLED (BGP Content Steering)")
    logger.info("       Billing  : ENABLED (PPPoE + Hotspot)")
    logger.info("=" * 65)

    # DB Indexes
    try:
        from core.db import get_db
        db = get_db()
        await db.traffic_history.create_index([("device_id", 1), ("timestamp", -1)], background=True)
        await db.traffic_history.create_index([("timestamp", -1)], background=True)
        await db.traffic_snapshots.create_index([("device_id", 1)], background=True)
        await db.devices.create_index([("id", 1)], unique=True, background=True)
        logger.info("MongoDB indexes verified.")

        ga_cfg = await db.system_settings.find_one({"_id": "genieacs_config"})
        if not ga_cfg:
            from datetime import datetime
            default_ga = {
                "_id": "genieacs_config",
                "url": os.environ.get("GENIEACS_URL", "http://genieacs-nbi:7557"),
                "username": os.environ.get("GENIEACS_USERNAME", "admin"),
                "password": os.environ.get("GENIEACS_PASSWORD", ""),
                "password_set": False,
                "updated_at": datetime.utcnow().isoformat()
            }
            await db.system_settings.insert_one(default_ga)
            logger.info("GenieACS default config seeded.")

        # Default Admin Seeding
        admin_count = await db.admin_users.count_documents({})
        if admin_count == 0:
            import uuid
            from core.auth import pwd_context
            from datetime import datetime, timezone
            default_admin = {
                "id": str(uuid.uuid4()),
                "username": "admin",
                "password": pwd_context.hash("admin123"),
                "name": "Administrator",
                "role": "administrator",
                "is_active": True,
                "created_at": datetime.now(timezone.utc).isoformat()
            }
            await db.admin_users.insert_one(default_admin)
            logger.info("Default admin user (admin/admin123) seeded.")
    except Exception as e:
        logger.error(f"DB init error: {e}")

    # TTL Indexes
    try:
        from core.db import get_db
        db = get_db()
        await db.audit_logs.create_index([("timestamp", 1)], expireAfterSeconds=7_776_000, background=True, name="ttl_audit_90d")
        await db.syslog_logs.create_index([("timestamp", 1)], expireAfterSeconds=5_184_000, background=True, name="ttl_syslog_60d")
        await db.traffic_history.create_index([("timestamp", 1)], expireAfterSeconds=604_800, background=True, name="ttl_traffic_7d")
    except Exception as e:
        logger.error(f"TTL index error: {e}")

    def _svc(key: str) -> bool:
        return os.environ.get(key, "true").lower() == "true"

    # Start ping scanner
    if _svc("ENABLE_POLLING"):
        from core.polling import polling_loop
        t = asyncio.create_task(polling_loop())
        _background_tasks.append(t)
        logger.info("Ping scanner started")

    # Start SSE
    if _svc("ENABLE_SSE"):
        from routers.events import start_poller
        t = start_poller()
        _background_tasks.append(t)
        logger.info("SSE event poller started")

    # Start syslog UDP
    loop = asyncio.get_running_loop()
    if _svc("ENABLE_SYSLOG"):
        from syslog_server import start_syslog_server
        ts = await start_syslog_server(loop)
        if ts:
            _background_tasks.extend(ts)

    # Start auto-backup
    if _svc("ENABLE_BACKUP"):
        from services.backup_service import auto_backup_loop
        t = asyncio.create_task(auto_backup_loop())
        _background_tasks.append(t)
        logger.info("Auto backup scheduler started")

    # Firebase
    try:
        from services.firebase_service import initialize_firebase
        if initialize_firebase():
            logger.info("Firebase: OK")
        else:
            logger.warning("Firebase: credentials not found")
    except Exception as e:
        logger.error(f"Firebase init error: {e}")

    # Auto isolir
    if _svc("ENABLE_ISOLIR"):
        from services.isolir_service import auto_isolir_loop
        t = asyncio.create_task(auto_isolir_loop())
        _background_tasks.append(t)
        logger.info("Auto isolir scheduler started")

    # Billing scheduler
    if _svc("ENABLE_BILLING_SCHEDULER"):
        from services.billing_scheduler import billing_scheduler_loop
        t = asyncio.create_task(billing_scheduler_loop())
        _background_tasks.append(t)
        logger.info("Billing scheduler started")

        from services.bandwidth_scheduler import bandwidth_scheduler_loop
        t = asyncio.create_task(bandwidth_scheduler_loop())
        _background_tasks.append(t)
        logger.info("Dynamic bandwidth scheduler started")

    # Hotspot cleanup
    if _svc("ENABLE_HOTSPOT_CLEANUP"):
        from services.hotspot_cleanup import hotspot_cleanup_loop
        t = asyncio.create_task(hotspot_cleanup_loop())
        _background_tasks.append(t)
        logger.info("Hotspot cleanup started")

    # Routing alerts
    if _svc("ENABLE_ROUTING_ALERTS"):
        from services.routing_alert_service import bgp_ospf_alert_loop
        t = asyncio.create_task(bgp_ospf_alert_loop())
        _background_tasks.append(t)
        logger.info("BGP/OSPF alert monitor started")

    # SNMP Poller
    if _svc("ENABLE_SNMP_POLLER"):
        try:
            from core.snmp_poller import start_snmp_poller
            t = asyncio.create_task(start_snmp_poller())
            _background_tasks.append(t)
            logger.info("SNMP Poller started")
        except Exception as e:
            logger.error(f"SNMP Poller error: {e}")

    # Speedtest
    if _svc("ENABLE_SPEEDTEST"):
        from services.speedtest_service import speedtest_loop
        t = asyncio.create_task(speedtest_loop())
        _background_tasks.append(t)
        logger.info("Speedtest scheduler started")

    # Session cache
    if _svc("ENABLE_SESSION_CACHE"):
        from services.session_cache_service import session_cache_loop
        t = asyncio.create_task(session_cache_loop())
        _background_tasks.append(t)
        logger.info("Session cache started")

    # BGP Content Steering
    if _svc("ENABLE_BGP_STEERING"):
        try:
            from services.bgp_steering_injector import bgp_steering_loop
            t = asyncio.create_task(bgp_steering_loop())
            _background_tasks.append(t)
            logger.info("BGP Content Steering injector started")
        except Exception as e:
            logger.error(f"BGP Steering error: {e}")

    # App Traffic Metrics Poller (Global ISP per-App bandwidth counter)
    if _svc("ENABLE_BGP_STEERING"):
        try:
            from services.app_metrics_poller import app_metrics_loop
            t = asyncio.create_task(app_metrics_loop())
            _background_tasks.append(t)
            logger.info("App Traffic Metrics poller started (5-min interval)")
        except Exception as e:
            logger.error(f"App Metrics Poller error: {e}")

    # GenieACS Sync
    if _svc("ENABLE_GENIEACS_SYNC"):
        try:
            from services.genieacs_service import genieacs_sync_loop
            t = asyncio.create_task(genieacs_sync_loop())
            _background_tasks.append(t)
            logger.info("GenieACS sync service started (ZTP ready)")
        except Exception as e:
            logger.error(f"GenieACS sync error: {e}")

    # Peering intelligence cache
    try:
        from services.peering_intelligence_cache import peering_cache_loop
        t = asyncio.create_task(peering_cache_loop())
        _background_tasks.append(t)
        logger.info("Peering intelligence cache started")
    except Exception as e:
        logger.error(f"Peering cache error: {e}")

    # License verification
    from services.license_service import license_check_loop
    t = asyncio.create_task(license_check_loop())
    _background_tasks.append(t)
    logger.info("License verification started")

    # RADIUS Server
    try:
        from radius_server import start_radius_server
        from core.db import get_db
        db = get_db()
        start_radius_server(loop, db)
        logger.info("RADIUS Server started (PAP + CHAP)")
    except Exception as e:
        logger.error(f"RADIUS Server error: {e}")

    logger.info("✅ NOC-Billing-Pro READY!")

    yield

    logger.info("NOC-Billing-Pro shutting down...")
    for task in _background_tasks:
        if not task.done():
            task.cancel()
    if _background_tasks:
        await asyncio.gather(*_background_tasks, return_exceptions=True)
    from core.db import close_db
    close_db()
    logger.info("Shutdown complete")


app = FastAPI(
    title="NOC-Billing-Pro API",
    version="1.0.0",
    description="NOC Billing Pro — Dashboard + Device + GenieACS + Billing + Peering",
    lifespan=lifespan
)

# CORS
_cors_origins_raw = os.environ.get("CORS_ORIGINS", "").strip()
if _cors_origins_raw and _cors_origins_raw != "*":
    _cors_origins = [o.strip() for o in _cors_origins_raw.split(",") if o.strip()]
    _allow_credentials = True
else:
    _cors_origins = ["*"]
    _allow_credentials = False

app.add_middleware(
    CORSMiddleware,
    allow_credentials=_allow_credentials,
    allow_origins=_cors_origins,
    allow_methods=["*"],
    allow_headers=["*"],
)

# License middleware
from starlette.requests import Request
from starlette.responses import JSONResponse
from core.db import get_db

@app.middleware("http")
async def license_middleware(request: Request, call_next):
    path = request.url.path
    if path.startswith("/api/"):
        allowed = [
            "/api/auth/", "/api/system/license", "/api/syslog/",
            "/api/devices/events", "/api/edition", "/api/system/info",
            "/api/wa-chat/log", "/api/webhook/moota",
            "/api/webhook/hotspot-public-config",
            "/api/webhook/hotspot-create-order",
            "/api/webhook/hotspot-order-status/",
            "/api/webhook/xendit",
            "/api/webhook/bca",
            "/api/webhook/bri",
        ]
        if not any(path.startswith(p) for p in allowed):
            try:
                db = get_db()
                if db is not None:
                    status_doc = await db.system_settings.find_one({"_id": "license_status"})
                    if (status_doc or {}).get("status") != "valid":
                        msg = (status_doc or {}).get("message", "Unlicensed")
                        return JSONResponse(status_code=403, content={"detail": f"License Error: {msg}"})
            except Exception:
                pass
    return await call_next(request)


# ── API Router ─────────────────────────────────────────────────────────────
api = APIRouter(prefix="/api")

@api.get("/edition", tags=["system"])
async def get_edition_info():
    return {
        "edition": "enterprise",
        "edition_name": "NOC-Billing-Pro",
        "is_enterprise": True,
        "is_pro": False,
        "features": {
            "billing": True,
            "customers": True,
            "finance_report": True,
            "genieacs": True,
            "ztp": True,
            "peering_eye": True,
            "bgp_steering": True,
            "cs_command_center": True,
            "client_portal": True,
            "n8n_integration": True,
        },
        "disabled_features": ["sdwan", "routing_monitor", "topology", "sla", "incidents"],
        "billing_enabled": True,
        "version": "1.0.0",
    }

# ── Auth & Webhooks (public, before auth check) ───────────────────────────
api.include_router(auth_router)
api.include_router(billing_webhook_router)      # Moota / Hotspot public webhook

# ── 1. Dashboard ──────────────────────────────────────────────────────────
api.include_router(metrics_router)
api.include_router(wallboard_router)
api.include_router(events_router)               # SSE real-time events
api.include_router(speedtest_router)

# ── 2. Device Hub ─────────────────────────────────────────────────────────
api.include_router(devices_router)

# ── 3. GenieACS + ZTP ─────────────────────────────────────────────────────
api.include_router(genieacs_router)

# ── 4. RADIUS (via hotspot router) ────────────────────────────────────────
api.include_router(hotspot_router)              # Hotspot + RADIUS Status & Push

# ── 5. Billing PPPoE ──────────────────────────────────────────────────────
api.include_router(pppoe_router)
api.include_router(billing_router)
api.include_router(customers_router)
api.include_router(voucher_pdf_router)      # Voucher Hotspot PDF Generator

# ── 6. Billing Hotspot ─────────────────────────────────────────────────────
# (hotspot_router already included above, handles all hotspot + billing endpoints)

# ── 7. Laporan Keuangan ────────────────────────────────────────────────────
api.include_router(reports_router)

# ── 8. CS Command Center ──────────────────────────────────────────────────
api.include_router(wa_cs_router)

# ── 9. Portal Pelanggan ────────────────────────────────────────────────────
api.include_router(client_portal_router)

# ── 10 & 11. Sentinel Peering Eye + BGP Content Steering ──────────────────
api.include_router(peering_eye_router)

# ── 12. Pengaturan Platform ────────────────────────────────────────────────
api.include_router(system_router)
api.include_router(notifications_router)

# ── 13. Integrasi & Otomasi ────────────────────────────────────────────────
# (bagian dari system_router dan integration_settings di system.py)

# ── 14. User Management ────────────────────────────────────────────────────
api.include_router(admin_router)

# ── 15. Update Aplikasi ────────────────────────────────────────────────────
# (bagian dari system_router)

# ── 16. Lisensi Sistem ─────────────────────────────────────────────────────
api.include_router(license_router)

# ── Admin pendukung ────────────────────────────────────────────────────────
api.include_router(backups_router)
api.include_router(syslog_router)
api.include_router(audit_router)
api.include_router(scheduler_router)
api.include_router(routing_alerts_router)

app.include_router(api)


@app.get("/")
async def root():
    return {
        "status": "ok",
        "service": "NOC-Billing-Pro",
        "edition": "billing_pro",
        "version": "1.0.0",
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("server:app", host="0.0.0.0", port=8000, reload=False)
