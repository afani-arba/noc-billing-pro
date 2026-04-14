"""
Notifications router: manage WhatsApp alert settings.
"""
import logging
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from typing import List, Optional
from core.db import get_db
from core.auth import require_admin
from services.notification_service import send_whatsapp, send_telegram

router = APIRouter(prefix="/notifications", tags=["notifications"])
logger = logging.getLogger(__name__)


class Recipient(BaseModel):
    phone: str         # Format: 628xxxxxxxxxx
    name: str = ""
    active: bool = True


class NotificationSettings(BaseModel):
    enabled: bool = False
    fonnte_token: str = ""
    recipients: List[Recipient] = []
    notify_offline: bool = True
    notify_cpu: bool = True
    notify_memory: bool = True   # FIX BUG #17: tambahkan field yang hilang, konsisten dengan notification_service.py
    notify_ping_high: bool = False
    notify_interface_down: bool = False
    notify_bgp: bool = True       # Alert saat BGP peer down/recover
    notify_ospf: bool = True      # Alert saat OSPF neighbor down/recover
    watched_interfaces: List[str] = []   # interface names to monitor for down events
    thresholds: dict = {"cpu": 80, "ping_ms": 100}
    # Telegram
    telegram_enabled: bool = False
    telegram_bot_token: str = ""
    telegram_chat_ids: List[str] = []    # multiple chat IDs supported


class TestMessage(BaseModel):
    phone: str
    fonnte_token: str


@router.get("/settings")
async def get_settings(user=Depends(require_admin)):
    db = get_db()
    settings = await db.notification_settings.find_one({}, {"_id": 0})
    if not settings:
        return NotificationSettings().model_dump()
    # Mask token partially for security
    if settings.get("fonnte_token"):
        token = settings["fonnte_token"]
        settings["fonnte_token"] = token[:4] + "****" + token[-4:] if len(token) > 8 else "****"
    return settings


@router.put("/settings")
async def update_settings(data: NotificationSettings, user=Depends(require_admin)):
    db = get_db()
    doc = data.model_dump()
    # Don't overwrite token if it's masked (contains ****)
    if "****" in doc.get("fonnte_token", ""):
        existing = await db.notification_settings.find_one({}, {"_id": 0, "fonnte_token": 1})
        if existing:
            doc["fonnte_token"] = existing.get("fonnte_token", "")
    if "****" in doc.get("telegram_bot_token", ""):
        existing = await db.notification_settings.find_one({}, {"_id": 0, "telegram_bot_token": 1})
        if existing:
            doc["telegram_bot_token"] = existing.get("telegram_bot_token", "")
    await db.notification_settings.replace_one({}, doc, upsert=True)
    return {"message": "Settings saved"}


@router.get("/settings/raw")
async def get_raw_settings(user=Depends(require_admin)):
    """Get full settings including token (for internal use)."""
    db = get_db()
    settings = await db.notification_settings.find_one({}, {"_id": 0})
    return settings or {}


@router.post("/test")
async def send_test(data: TestMessage, user=Depends(require_admin)):
    """Send a test WhatsApp message."""
    db = get_db()
    token = data.fonnte_token
    if "****" in token:
        stored = await db.notification_settings.find_one({}, {"_id": 0, "fonnte_token": 1})
        token = (stored or {}).get("fonnte_token", "")
    if not token:
        raise HTTPException(400, "Fonnte token not configured")
    
    msg = (
        "✅ *Test Notifikasi NOC-Sentinel*\n"
        "━━━━━━━━━━━━━━\n"
        "Notifikasi WhatsApp berhasil dikonfigurasi!\n"
        "Sistem monitoring aktif dan siap mengirim alert.\n"
        "━━━━━━━━━━━━━━\n"
        "NOC-Sentinel Monitoring"
    )
    ok = await send_whatsapp(data.phone, msg, token)
    if ok:
        return {"success": True, "message": f"Test message sent to {data.phone}"}
    else:
        raise HTTPException(503, "Failed to send message. Check token and phone number.")


class TestTelegramMessage(BaseModel):
    chat_id: str
    bot_token: str = ""


@router.post("/test-telegram")
async def send_test_telegram(data: TestTelegramMessage, user=Depends(require_admin)):
    """Send a test Telegram message."""
    db = get_db()
    bot_token = data.bot_token
    if not bot_token or "****" in bot_token:
        stored = await db.notification_settings.find_one({}, {"_id": 0, "telegram_bot_token": 1})
        bot_token = (stored or {}).get("telegram_bot_token", "")
    if not bot_token:
        raise HTTPException(400, "Telegram bot token not configured")
    msg = (
        "✅ *Test Notifikasi NOC-Sentinel*\n"
        "━━━━━━━━━━━━━━\n"
        "Notifikasi Telegram berhasil dikonfigurasi!\n"
        "Sistem monitoring aktif dan siap mengirim alert.\n"
        "━━━━━━━━━━━━━━\n"
        "NOC\-Sentinel Monitoring"
    )
    ok = await send_telegram(data.chat_id, msg, bot_token)
    if ok:
        return {"success": True, "message": f"Test Telegram sent to {data.chat_id}"}
    else:
        raise HTTPException(503, "Failed to send Telegram. Check bot token and chat ID.")
