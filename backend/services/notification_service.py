"""
Notification service: WhatsApp via Fonnte API + Telegram Bot API.

Settings stored in MongoDB 'notification_settings' collection.
"""
import logging
import httpx
from core.db import get_db

logger = logging.getLogger(__name__)

FONNTE_API_URL = "https://api.fonnte.com/send"
TELEGRAM_API_BASE = "https://api.telegram.org/bot"


async def _get_settings() -> dict:
    """Fetch notification settings from DB."""
    db = get_db()
    settings = await db.notification_settings.find_one({}, {"_id": 0})
    return settings or {}


async def send_whatsapp(phone: str, message: str, token: str) -> bool:
    """Send WhatsApp via Fonnte API."""
    if not token or not phone:
        return False
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.post(
                FONNTE_API_URL,
                headers={"Authorization": token},
                data={"target": phone, "message": message, "countryCode": "62"},
            )
            data = resp.json()
            if resp.status_code == 200 and data.get("status"):
                logger.info(f"WA notification sent to {phone}")
                return True
            else:
                logger.warning(f"WA send failed: {data}")
                return False
    except Exception as e:
        logger.error(f"WA notification error: {e}")
        return False


async def send_telegram(chat_id: str, message: str, bot_token: str) -> bool:
    """Send message via Telegram Bot API."""
    if not bot_token or not chat_id:
        return False
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.post(
                f"{TELEGRAM_API_BASE}{bot_token}/sendMessage",
                json={"chat_id": chat_id, "text": message, "parse_mode": "Markdown"},
            )
            data = resp.json()
            if resp.status_code == 200 and data.get("ok"):
                logger.info(f"Telegram notification sent to {chat_id}")
                return True
            else:
                logger.warning(f"Telegram send failed: {data}")
                return False
    except Exception as e:
        logger.error(f"Telegram notification error: {e}")
        return False


async def send_to_all_recipients(message: str, settings: dict) -> int:
    """Send message to all configured WA + Telegram recipients. Returns count sent."""
    sent = 0

    # WhatsApp via Fonnte
    token = settings.get("fonnte_token", "")
    recipients = settings.get("recipients", [])
    if token and recipients:
        for r in recipients:
            phone = r.get("phone", "").strip()
            if phone and r.get("active", True):
                ok = await send_whatsapp(phone, message, token)
                if ok:
                    sent += 1

    # Telegram Bot
    if settings.get("telegram_enabled", False):
        bot_token = settings.get("telegram_bot_token", "")
        chat_ids = settings.get("telegram_chat_ids", [])
        for chat_id in chat_ids:
            if chat_id:
                ok = await send_telegram(str(chat_id).strip(), message, bot_token)
                if ok:
                    sent += 1

    return sent


async def check_and_notify(device: dict, poll_result: dict, update: dict):
    """
    Called after each poll. Checks conditions and sends WA+Telegram if needed.
    Uses 'alert_sent' flags in device doc to avoid flooding.
    """
    settings = await _get_settings()
    if not settings.get("enabled", False):
        return

    db = get_db()
    device_id = device["id"]
    device_name = device.get("name", device_id)
    ip = device.get("ip_address", "")
    thresholds = settings.get("thresholds", {})
    cpu_threshold = thresholds.get("cpu", 80)
    mem_threshold = thresholds.get("memory", 80)

    current_doc = await db.devices.find_one({"id": device_id}, {"_id": 0, "alert_offline_sent": 1, "alert_cpu_sent": 1, "alert_mem_sent": 1})
    alert_offline_sent = current_doc.get("alert_offline_sent", False) if current_doc else False
    alert_cpu_sent = current_doc.get("alert_cpu_sent", False) if current_doc else False
    alert_mem_sent = current_doc.get("alert_mem_sent", False) if current_doc else False

    status = update.get("status", "unknown")
    cpu = update.get("cpu_load", 0)
    memory = update.get("memory_usage", 0)
    flags_update = {}

    # ── Device OFFLINE
    if status == "offline" and not alert_offline_sent and settings.get("notify_offline", True):
        msg = (
            f"🔴 *ALERT: Device Offline*\n"
            f"━━━━━━━━━━━━━━\n"
            f"📡 Device: *{device_name}*\n"
            f"🌐 IP: {ip}\n"
            f"⏰ Status: OFFLINE\n"
            f"━━━━━━━━━━━━━━\n"
            f"NOC-Sentinel Monitoring"
        )
        await send_to_all_recipients(msg, settings)
        flags_update["alert_offline_sent"] = True
        flags_update["alert_cpu_sent"] = False
        flags_update["alert_mem_sent"] = False

    # ── Device back ONLINE
    elif status == "online" and alert_offline_sent:
        msg = (
            f"🟢 *RECOVER: Device Online*\n"
            f"━━━━━━━━━━━━━━\n"
            f"📡 Device: *{device_name}*\n"
            f"🌐 IP: {ip}\n"
            f"⏰ Status: ONLINE\n"
            f"━━━━━━━━━━━━━━\n"
            f"NOC-Sentinel Monitoring"
        )
        await send_to_all_recipients(msg, settings)
        flags_update["alert_offline_sent"] = False

    # ── High CPU
    if status == "online" and settings.get("notify_cpu", True):
        if cpu > cpu_threshold and not alert_cpu_sent:
            msg = (
                f"⚠️ *ALERT: High CPU Usage*\n"
                f"━━━━━━━━━━━━━━\n"
                f"📡 Device: *{device_name}*\n"
                f"🌐 IP: {ip}\n"
                f"🖥️ CPU: *{cpu}%* (threshold: {cpu_threshold}%)\n"
                f"━━━━━━━━━━━━━━\n"
                f"NOC-Sentinel Monitoring"
            )
            await send_to_all_recipients(msg, settings)
            flags_update["alert_cpu_sent"] = True
        elif cpu <= cpu_threshold:
            flags_update["alert_cpu_sent"] = False

    # ── High Memory
    if status == "online" and settings.get("notify_memory", True):
        if memory > mem_threshold and not alert_mem_sent:
            msg = (
                f"⚠️ *ALERT: High Memory Usage*\n"
                f"━━━━━━━━━━━━━━\n"
                f"📡 Device: *{device_name}*\n"
                f"🌐 IP: {ip}\n"
                f"💾 Memory: *{memory}%* (threshold: {mem_threshold}%)\n"
                f"━━━━━━━━━━━━━━\n"
                f"NOC-Sentinel Monitoring"
            )
            await send_to_all_recipients(msg, settings)
            flags_update["alert_mem_sent"] = True
        elif memory <= mem_threshold:
            flags_update["alert_mem_sent"] = False

    if flags_update:
        await db.devices.update_one({"id": device_id}, {"$set": flags_update})
