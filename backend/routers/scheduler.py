"""
Scheduler router: API untuk config dan trigger backup otomatis terjadwal.
"""
import logging
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from core.db import get_db
from core.auth import require_admin

router = APIRouter(prefix="/scheduler", tags=["scheduler"])
logger = logging.getLogger(__name__)


class BackupScheduleConfig(BaseModel):
    enabled: bool = True
    hour_wib: int = 2           # jam WIB (0-23), dikonversi ke UTC secara internal
    minute: int = 0             # menit (0-59)
    retention_days: int = 30    # simpan backup selama N hari


@router.get("/config")
async def get_scheduler_config(user=Depends(require_admin)):
    """Lihat konfigurasi backup scheduler saat ini."""
    db = get_db()
    cfg = await db.scheduler_config.find_one({"type": "backup"}, {"_id": 0})
    if not cfg:
        # Default config
        return {
            "enabled": True,
            "hour_wib": 2,
            "minute": 0,
            "hour_utc": 19,
            "retention_days": 30,
            "next_run_info": "Setiap hari jam 02:00 WIB"
        }
    hour_utc = cfg.get("hour_utc", 19)
    hour_wib = (hour_utc + 7) % 24
    return {
        "enabled": cfg.get("enabled", True),
        "hour_wib": hour_wib,
        "minute": cfg.get("minute_utc", 0),
        "hour_utc": hour_utc,
        "retention_days": cfg.get("retention_days", 30),
        "next_run_info": f"Setiap hari jam {hour_wib:02d}:{cfg.get('minute_utc', 0):02d} WIB"
    }


@router.put("/config")
async def update_scheduler_config(body: BackupScheduleConfig, user=Depends(require_admin)):
    """Update konfigurasi backup scheduler."""
    if not (0 <= body.hour_wib <= 23):
        raise HTTPException(400, "hour_wib harus antara 0-23")
    if not (0 <= body.minute <= 59):
        raise HTTPException(400, "minute harus antara 0-59")
    if not (1 <= body.retention_days <= 365):
        raise HTTPException(400, "retention_days harus antara 1-365")

    hour_utc = (body.hour_wib - 7) % 24  # WIB → UTC

    db = get_db()
    await db.scheduler_config.update_one(
        {"type": "backup"},
        {"$set": {
            "type": "backup",
            "enabled": body.enabled,
            "hour_utc": hour_utc,
            "minute_utc": body.minute,
            "retention_days": body.retention_days,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }},
        upsert=True
    )
    return {
        "message": "Konfigurasi scheduler berhasil disimpan",
        "enabled": body.enabled,
        "schedule": f"Setiap hari jam {body.hour_wib:02d}:{body.minute:02d} WIB",
        "retention_days": body.retention_days,
    }


@router.post("/backup/run-now")
async def run_backup_now(user=Depends(require_admin)):
    """Trigger backup semua device online sekarang juga (async background)."""
    import asyncio
    from services.backup_service import backup_all_devices
    # Jalankan backup sebagai background task agar tidak timeout
    asyncio.create_task(backup_all_devices())
    return {
        "message": "Backup dimulai untuk semua device online. Cek halaman Backups untuk hasilnya.",
        "started_at": datetime.now(timezone.utc).isoformat(),
    }


@router.get("/backup/history")
async def get_backup_history(limit: int = 20, user=Depends(require_admin)):
    """Lihat history backup otomatis (bukan manual)."""
    db = get_db()
    history = await db.scheduler_history.find(
        {"type": "auto_backup_run"},
        {"_id": 0}
    ).sort("timestamp", -1).limit(limit).to_list(limit)
    return history


@router.get("/backup/status")
async def get_backup_status(user=Depends(require_admin)):
    """Status backup terakhir: kapan, berapa device, success/fail."""
    db = get_db()
    last = await db.scheduler_history.find_one(
        {"type": "auto_backup_run"},
        {"_id": 0},
        sort=[("timestamp", -1)]
    )
    return last or {"message": "Belum ada backup otomatis yang pernah dijalankan"}
