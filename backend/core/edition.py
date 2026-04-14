"""
core/edition.py — NOC Sentinel Edition Manager
================================================
Module tunggal sebagai pusat kebenaran edisi yang aktif.
Dibaca sekali saat startup dari environment variable APP_EDITION.

Nilai valid:
  "pro"        = NOC-Sentinel Pro (Monitoring Only, tanpa Billing)
  "enterprise" = NOC-Sentinel Enterprise (Full Service + Billing)

Cara pakai di modul lain:
  from core.edition import EDITION, is_enterprise, FEATURES
"""
import os
import logging

logger = logging.getLogger(__name__)

# Baca dari environment, default ke "pro" (aman / minimal)
EDITION: str = os.environ.get("APP_EDITION", "pro").lower().strip()

# Normalisasi: pastikan hanya nilai valid
if EDITION not in ("pro", "enterprise"):
    logger.warning(
        f"APP_EDITION='{EDITION}' tidak valid. Menggunakan 'pro' sebagai default."
    )
    EDITION = "pro"

# ── Edition Metadata ──────────────────────────────────────────────────────────

EDITION_NAMES = {
    "pro": "NOC-Sentinel Pro",
    "enterprise": "NOC-Sentinel Enterprise",
}

EDITION_NAME: str = EDITION_NAMES.get(EDITION, "NOC-Sentinel Pro")

# ── Feature Flags ─────────────────────────────────────────────────────────────
# Tentukan fitur apa saja yang aktif berdasarkan edisi
FEATURES: dict = {
    # === MONITORING (Semua edisi) ===
    "dashboard":          True,
    "devices":            True,
    "pppoe_users":        True,   # PPPoE Users reader-only (bukan billing)
    "hotspot_users":      True,   # Hotspot Users reader-only
    "reports":            True,
    "bandwidth":          True,
    "sla":                True,
    "incidents":          True,
    "topology":           True,
    "wallboard":          True,
    "bgp":                True,
    "routing":            True,
    "sdwan":              True,
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

    # === BILLING (Enterprise only) ===
    "billing":            EDITION == "enterprise",
    "customers":          EDITION == "enterprise",
    "billing_scheduler":  EDITION == "enterprise",
    "auto_isolir":        EDITION == "enterprise",
    "n8n_integration":    EDITION == "enterprise",
    "finance_report":     EDITION == "enterprise",
}


def is_enterprise() -> bool:
    """Return True jika edisi saat ini adalah Enterprise."""
    return EDITION == "enterprise"


def is_pro() -> bool:
    """Return True jika edisi saat ini adalah Pro."""
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
