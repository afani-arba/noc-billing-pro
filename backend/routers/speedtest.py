"""
Speedtest router: API untuk hasil, history, run manual, dan config speed test.
"""
import logging
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from core.db import get_db
from core.auth import get_current_user, require_admin

router = APIRouter(prefix="/speedtest", tags=["speedtest"])
logger = logging.getLogger(__name__)


class SpeedtestConfig(BaseModel):
    enabled: bool = True
    interval_minutes: int = 60    # interval test (min 10, max 1440)
    ping_count: int = 5           # jumlah ping per test
    http_timeout: int = 10        # HTTP timeout detik


@router.get("/results")
async def get_speedtest_results(user=Depends(get_current_user)):
    """Ambil hasil speed test terbaru per device (1 record terbaru per device)."""
    db = get_db()
    # Ambil semua hasil, lalu filter ke yang terbaru per device
    pipeline = [
        {"$sort": {"timestamp": -1}},
        {"$group": {
            "_id": "$device_id",
            "device_name": {"$first": "$device_name"},
            "ip_address": {"$first": "$ip_address"},
            "ping_ms": {"$first": "$ping_ms"},
            "ping_loss_pct": {"$first": "$ping_loss_pct"},
            "http_ms": {"$first": "$http_ms"},
            "tcp_ms": {"$first": "$tcp_ms"},
            "status": {"$first": "$status"},
            "timestamp": {"$first": "$timestamp"},
        }},
        {"$sort": {"device_name": 1}},
    ]
    results = await db.speedtest_results.aggregate(pipeline).to_list(500)
    # Normalize _id → device_id
    for r in results:
        r["device_id"] = r.pop("_id")
    return results


@router.get("/history/{device_id}")
async def get_speedtest_history(device_id: str, limit: int = 48, user=Depends(get_current_user)):
    """Ambil history speed test satu device untuk grafik tren (default 48 records = 2 hari)."""
    db = get_db()
    history = await db.speedtest_results.find(
        {"device_id": device_id},
        {"_id": 0}
    ).sort("timestamp", -1).limit(limit).to_list(limit)
    return list(reversed(history))  # balik ke kronologis untuk grafik


@router.post("/run/{device_id}")
async def run_speedtest(device_id: str, user=Depends(require_admin)):
    """Trigger speed test manual ke satu device."""
    db = get_db()
    device = await db.devices.find_one({"id": device_id}, {"_id": 0})
    if not device:
        raise HTTPException(404, "Device not found")

    from services.speedtest_service import speedtest_device
    result = await speedtest_device(device)

    # Simpan hasil ke DB
    await db.speedtest_results.insert_one({**result})

    return result


@router.post("/run-all")
async def run_speedtest_all(user=Depends(require_admin)):
    """Trigger speed test manual ke semua device online (background)."""
    import asyncio
    from services.speedtest_service import speedtest_all_devices
    asyncio.create_task(speedtest_all_devices())
    return {
        "message": "Speed test dimulai untuk semua device online",
        "started_at": datetime.now(timezone.utc).isoformat(),
    }


@router.get("/config")
async def get_speedtest_config(user=Depends(require_admin)):
    """Lihat konfigurasi speed test scheduler."""
    db = get_db()
    cfg = await db.scheduler_config.find_one({"type": "speedtest"}, {"_id": 0})
    if not cfg:
        return {"enabled": True, "interval_minutes": 60, "ping_count": 5, "http_timeout": 10}
    return {
        "enabled": cfg.get("enabled", True),
        "interval_minutes": cfg.get("interval_minutes", 60),
        "ping_count": cfg.get("ping_count", 5),
        "http_timeout": cfg.get("http_timeout", 10),
    }


@router.put("/config")
async def update_speedtest_config(body: SpeedtestConfig, user=Depends(require_admin)):
    """Update konfigurasi speed test scheduler."""
    if not (10 <= body.interval_minutes <= 1440):
        raise HTTPException(400, "interval_minutes harus antara 10-1440")
    if not (1 <= body.ping_count <= 20):
        raise HTTPException(400, "ping_count harus antara 1-20")

    db = get_db()
    await db.scheduler_config.update_one(
        {"type": "speedtest"},
        {"$set": {
            "type": "speedtest",
            "enabled": body.enabled,
            "interval_minutes": body.interval_minutes,
            "ping_count": body.ping_count,
            "http_timeout": body.http_timeout,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }},
        upsert=True
    )
    return {"message": "Konfigurasi speed test berhasil disimpan", **body.model_dump()}
