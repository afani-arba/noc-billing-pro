"""
Peering Alert Service — Auto-alerting untuk platform berbahaya.

Membaca platform yang dikonfigurasi dengan alert_threshold_hits > 0,
dan memeriksa setiap snapshot DNS flush untuk mendeteksi pelanggaran.

Threshold:
  - alert_threshold_hits : jumlah DNS hits dalam satu flush period
  - alert_threshold_mb   : total bytes (MB) dalam satu flush period

Notifikasi:
  - Insert ke collection peering_alerts di MongoDB
  - Kirim WhatsApp jika integrasi aktif

Cara pakai (dipanggil dari syslog_server._peering_eye_flusher setelah bulk_write):
  from services.peering_alert_service import check_alerts_from_snapshot
  asyncio.create_task(check_alerts_from_snapshot(snapshot))
"""
import asyncio
import logging
import uuid
from datetime import datetime, timezone, timedelta

from core.db import get_db

logger = logging.getLogger(__name__)

# Cooldown per (device_id, platform) — jangan spam alert
_ALERT_COOLDOWN_MINUTES = 30
_alert_cooldown: dict = {}  # {(device_id, platform): last_alert_iso}


def _is_in_cooldown(device_id: str, platform: str) -> bool:
    key = (device_id, platform)
    last = _alert_cooldown.get(key)
    if not last:
        return False
    try:
        last_dt = datetime.fromisoformat(last)
        if (datetime.now(timezone.utc) - last_dt).total_seconds() < _ALERT_COOLDOWN_MINUTES * 60:
            return True
    except Exception:
        pass
    return False


def _set_cooldown(device_id: str, platform: str) -> None:
    _alert_cooldown[(device_id, platform)] = datetime.now(timezone.utc).isoformat()


async def _get_platform_thresholds(db) -> dict:
    """Return {platform_name: {hits: N, mb: N}} dari peering_platforms collection."""
    docs = await db.peering_platforms.find(
        {"$or": [
            {"alert_threshold_hits": {"$gt": 0}},
            {"alert_threshold_mb": {"$gt": 0}},
        ]},
        {"_id": 0, "name": 1, "alert_threshold_hits": 1, "alert_threshold_mb": 1}
    ).to_list(200)
    return {
        d["name"]: {
            "hits": d.get("alert_threshold_hits", 0),
            "mb":   d.get("alert_threshold_mb", 0),
        }
        for d in docs
    }


async def _send_whatsapp_alert(db, message: str) -> None:
    """Kirim notifikasi WhatsApp via integration jika aktif."""
    try:
        cfg = await db.system_settings.find_one({"_id": "integration_settings"})
        if not cfg:
            return
        wa_url = cfg.get("wa_webhook_url") or cfg.get("whatsapp_webhook_url") or ""
        if not wa_url:
            return

        import httpx
        payload = {"message": message}
        async with httpx.AsyncClient(timeout=10) as client:
            r = await client.post(wa_url, json=payload)
            if r.status_code < 300:
                logger.info(f"[PeeringAlert] WA notifikasi terkirim")
            else:
                logger.warning(f"[PeeringAlert] WA gagal: HTTP {r.status_code}")
    except Exception as e:
        logger.debug(f"[PeeringAlert] WA error: {e}")


async def check_alerts_from_snapshot(snapshot: dict) -> None:
    """
    Periksa snapshot DNS flush terhadap threshold platform.
    snapshot format: {(device_id, platform): {hits, bytes, icon, color, ...}}
    """
    try:
        db = get_db()
        thresholds = await _get_platform_thresholds(db)
        if not thresholds:
            return

        now_iso = datetime.now(timezone.utc).isoformat()
        alerts_to_insert = []

        for (device_id, platform), data in snapshot.items():
            threshold = thresholds.get(platform)
            if not threshold:
                continue

            hits = data.get("hits", 0)
            bytes_val = data.get("bytes", 0)
            mb_val = bytes_val / (1024 * 1024)

            # Cek apakah melewati threshold
            triggered = False
            reasons = []
            if threshold["hits"] > 0 and hits >= threshold["hits"]:
                triggered = True
                reasons.append(f"{hits} hits (threshold: {threshold['hits']})")
            if threshold["mb"] > 0 and mb_val >= threshold["mb"]:
                triggered = True
                reasons.append(f"{mb_val:.1f} MB (threshold: {threshold['mb']} MB)")

            if not triggered:
                continue

            if _is_in_cooldown(device_id, platform):
                logger.debug(f"[PeeringAlert] {platform} @ {device_id} in cooldown, skip")
                continue

            # Ambil nama device
            dev_doc = await db.devices.find_one(
                {"$or": [{"id": device_id}, {"ip_address": device_id}, {"name": device_id}]},
                {"name": 1, "_id": 0}
            )
            device_name = dev_doc.get("name", device_id) if dev_doc else device_id

            alert_doc = {
                "id":          str(uuid.uuid4()),
                "device_id":   device_id,
                "device_name": device_name,
                "platform":    platform,
                "icon":        data.get("icon", "⚠️"),
                "color":       data.get("color", "#ef4444"),
                "hits":        hits,
                "bytes":       bytes_val,
                "reasons":     reasons,
                "status":      "active",    # active / dismissed
                "timestamp":   now_iso,
                "dismissed_at": None,
                "dismissed_by": None,
            }
            alerts_to_insert.append(alert_doc)
            _set_cooldown(device_id, platform)

            logger.warning(
                f"[PeeringAlert] ALERT: {platform} pada {device_name} "
                f"— {', '.join(reasons)}"
            )

        if alerts_to_insert:
            await db.peering_alerts.insert_many(alerts_to_insert)
            logger.info(f"[PeeringAlert] {len(alerts_to_insert)} alert(s) disimpan ke MongoDB")

            # Kirim WA untuk setiap alert
            for alert in alerts_to_insert:
                wa_msg = (
                    f"[PEERING ALERT] {alert['icon']} {alert['platform']}\n"
                    f"Device: {alert['device_name']}\n"
                    f"Trigger: {', '.join(alert['reasons'])}\n"
                    f"Waktu: {now_iso}"
                )
                await _send_whatsapp_alert(db, wa_msg)

    except Exception as e:
        logger.error(f"[PeeringAlert] check_alerts_from_snapshot error: {e}")


async def cleanup_old_alerts_loop() -> None:
    """Hapus alert yang lebih dari 7 hari secara berkala."""
    while True:
        try:
            db = get_db()
            cutoff = (datetime.now(timezone.utc) - timedelta(days=7)).isoformat()
            r = await db.peering_alerts.delete_many({"timestamp": {"$lt": cutoff}})
            if r.deleted_count > 0:
                logger.info(f"[PeeringAlert] Cleaned {r.deleted_count} old alerts")
        except asyncio.CancelledError:
            break
        except Exception as e:
            logger.error(f"[PeeringAlert] cleanup error: {e}")
        await asyncio.sleep(3600 * 6)  # setiap 6 jam
