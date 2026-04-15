"""
core/edition.py — NOC Sentinel Edition Manager
================================================
Module tunggal sebagai pusat kebenaran edisi yang aktif.
Dibaca sekali saat startup dari environment variable APP_EDITION.

Nilai valid:
  "pro"          = NOC-Sentinel Pro (Monitoring Only, tanpa Billing)
  "enterprise"   = NOC-Sentinel Enterprise (Full Service + Billing)
  "billing_pro"  = NOC-Billing-Pro (GenieACS + BGP + Billing, tanpa SD-WAN)

Cara pakai di modul lain:
  from core.edition import EDITION, is_enterprise, FEATURES
"""
import os
import logging

logger = logging.getLogger(__name__)

# Baca dari environment, default ke "pro" (aman / minimal)
EDITION: str = os.environ.get("APP_EDITION", "pro").lower().strip()

# Normalisasi: pastikan hanya nilai valid
# billing_pro = alias untuk enterprise (superset fitur billing, tanpa SD-WAN/routing advanced)
if EDITION not in ("pro", "enterprise", "billing_pro"):
    logger.warning(
        f"APP_EDITION='{EDITION}' tidak valid. Menggunakan 'pro' sebagai default."
    )
    EDITION = "pro"

# ── Edition Metadata ──────────────────────────────────────────────────────────

EDITION_NAMES = {
    "pro":         "NOC-Sentinel Pro",
    "enterprise":  "NOC-Sentinel Enterprise",
    "billing_pro": "NOC-Billing-Pro",
}

EDITION_NAME: str = EDITION_NAMES.get(EDITION, "NOC-Sentinel Pro")

# billing_pro memiliki semua fitur billing (sama dengan enterprise)
_is_billing = EDITION in ("enterprise", "billing_pro")

# ── Feature Flags ─────────────────────────────────────────────────────────────
# Tentukan fitur apa saja yang aktif berdasarkan edisi
FEATURES: dict = {
    # === MONITORING (Semua edisi) ===
    "dashboard":          True,
    "devices":            True,
    "pppoe_users":        True,   # PPPoE Users reader-only (dan billing di billing_pro)
    "hotspot_users":      True,   # Hotspot Users reader-only (dan billing di billing_pro)
    "reports":            True,
    "bandwidth":          True,
    "sla":                True,
    "incidents":          True,
    "topology":           True,
    "wallboard":          True,
    "bgp":                True,
    "routing":            True,
    "sdwan":              EDITION == "enterprise",  # SD-WAN hanya di Enterprise penuh
    "traffic_flow":       True,
    "netwatch":           True,
    "peering_eye":        True,
    "looking_glass":      True,
    "genieacs":           True,   # GenieACS/TR-069 tersedia di semua edisi
    "syslog":             True,
    "audit_log":          True,
    "backups":            True,
    "scheduler":          True,
    "speedtest":          True,
    "notifications":      True,   # Notifikasi sistem (bukan WA billing)

    # === BILLING (Enterprise & Billing Pro) ===
    "billing":            _is_billing,
    "customers":          _is_billing,
    "billing_scheduler":  _is_billing,
    "auto_isolir":        _is_billing,
    "n8n_integration":    _is_billing,
    "finance_report":     _is_billing,
    "genieacs_ztp":       _is_billing,   # ZTP provisioning aktif di billing_pro
    "bgp_steering":       _is_billing,   # BGP Content Steering aktif di billing_pro
    "cs_command_center":  _is_billing,   # CS WhatsApp center
    "client_portal":      _is_billing,   # Portal pelanggan self-service
    "radius":             _is_billing,   # RADIUS Server (hotspot/PPPoE auth)
}


def is_enterprise() -> bool:
    """Return True jika edisi saat ini adalah Enterprise atau Billing Pro."""
    return EDITION in ("enterprise", "billing_pro")


def is_billing_pro() -> bool:
    """Return True jika edisi saat ini adalah Billing Pro."""
    return EDITION == "billing_pro"


def is_pro() -> bool:
    """Return True jika edisi saat ini adalah Pro (monitoring only)."""
    return EDITION == "pro"


def get_edition_name() -> str:
    """Return nama edisi yang dapat dibaca manusia."""
    return EDITION_NAME


def get_disabled_features() -> list:
    """Return daftar fitur yang dimatikan pada edisi saat ini."""
    return [k for k, v in FEATURES.items() if not v]


def get_enabled_features() -> list:
    """Return daftar fitur yang aktif pada edisi saat ini."""
    return [k for k, v in FEATURES.items() if v]


# ── Log Edition pada import ───────────────────────────────────────────────────
logger.info(
    f"🏷️  Running as: {EDITION_NAME} (APP_EDITION={EDITION})"
)
if EDITION == "pro":
    disabled = get_disabled_features()
    logger.info(
        f"   Fitur DINONAKTIFKAN di edisi Pro: {', '.join(disabled)}"
    )
