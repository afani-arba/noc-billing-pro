"""
Auto-backup service for MikroTik configurations.
Export strategy (in order):
  1. SSH /export terse  (works for both RouterOS 6 and 7, most reliable)
  2. REST API /export   (RouterOS 7+ REST API fallback)
Backups stored in /backups/ directory relative to backend folder.

Auto-backup scheduler:
  - Runs daily at configurable time (default 02:00 WIB = 19:00 UTC)
  - Backs up all online devices
  - Cleans up backups older than retention_days (default 30)
"""
import asyncio
import logging
import os
import re
from pathlib import Path
from datetime import datetime, timezone
from typing import Optional
from core.db import get_db
from mikrotik_api import get_api_client

logger = logging.getLogger(__name__)

BACKUP_DIR = Path(__file__).parent.parent / "backups"
BACKUP_DIR.mkdir(exist_ok=True)

SSH_PORT = 42
SSH_TIMEOUT = 20


async def _get_device(device_id: str) -> Optional[dict]:
    db = get_db()
    return await db.devices.find_one({"id": device_id}, {"_id": 0})


def _safe_filename(name: str) -> str:
    """Sanitize device name for use in filename."""
    return re.sub(r"[^a-zA-Z0-9_-]", "_", name)


def _export_via_ssh(host: str, username: str, password: str, port: int = SSH_PORT) -> Optional[str]:
    """Run /export terse on MikroTik via SSH. Works for RouterOS 6 and 7."""
    try:
        import paramiko
        client = paramiko.SSHClient()
        client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        client.connect(
            hostname=host,
            port=port,
            username=username,
            password=password,
            timeout=SSH_TIMEOUT,
            look_for_keys=False,
            allow_agent=False,
        )
        _, stdout, _ = client.exec_command("/export terse", timeout=60)
        output = stdout.read().decode("utf-8", errors="replace")
        client.close()
        if output and len(output.strip()) > 10:
            return output
        logger.warning(f"SSH export returned empty output for {host}")
        return None
    except ImportError:
        logger.warning("paramiko not installed — SSH export unavailable")
        return None
    except Exception as e:
        logger.warning(f"SSH export failed for {host}: {e}")
        return None


def _export_via_rest(mt_client) -> Optional[str]:
    """Fetch RSC config via REST API /export endpoint (RouterOS 7+)."""
    if not hasattr(mt_client, "base_url"):
        return None
    try:
        import requests
        resp = requests.get(
            f"{mt_client.base_url}/export",
            auth=mt_client.auth,
            verify=False,
            timeout=60,
        )
        if resp.status_code == 200 and resp.text.strip():
            return resp.text
        logger.warning(f"REST /export returned HTTP {resp.status_code}")
        return None
    except Exception as e:
        logger.warning(f"REST export failed: {e}")
        return None


def _get_rsc_export(mt_client, device: dict) -> Optional[str]:
    """Try SSH export first, then REST API."""
    host = getattr(mt_client, "host", None) or device.get("ip_address", "")
    username = device.get("api_username", "admin")
    password = device.get("api_password", "")

    # Method 1: SSH — most reliable, works for ROS6 and ROS7
    if host and username:
        content = _export_via_ssh(host, username, password, port=SSH_PORT)
        if content:
            logger.info(f"RSC export via SSH successful for {host}")
            return content

    # Method 2: REST API — ROS7 fallback
    content = _export_via_rest(mt_client)
    if content:
        logger.info(f"RSC export via REST successful")
        return content

    return None


async def backup_device_api(device: dict) -> dict:
    """
    Backup MikroTik config via SSH export (primary) or REST API (fallback).
    Returns: {"success": bool, "filename": str, "size": int, "type": str}
    """
    device_name = _safe_filename(device.get("name", device["id"]))
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    backup_name = f"backup_{device_name}_{timestamp}"

    try:
        mt = get_api_client(device)

        rsc_content = await asyncio.to_thread(_get_rsc_export, mt, device)
        if rsc_content:
            rsc_filename = f"{backup_name}.rsc"
            rsc_path = BACKUP_DIR / rsc_filename
            rsc_path.write_text(rsc_content, encoding="utf-8")
            logger.info(f"RSC backup saved: {rsc_filename} ({len(rsc_content)} bytes)")

            db = get_db()
            await db.backups.insert_one({
                "device_id": device["id"],
                "device_name": device.get("name", ""),
                "ip_address": device.get("ip_address", ""),
                "filename": rsc_filename,
                "type": "rsc",
                "size": len(rsc_content.encode()),
                "created_at": datetime.now(timezone.utc).isoformat(),
            })
            return {
                "success": True,
                "filename": rsc_filename,
                "size": len(rsc_content.encode()),
                "type": "rsc",
            }

        return {
            "success": False,
            "error": (
                "Tidak dapat mengambil konfigurasi dari device. "
                f"Pastikan SSH (port {SSH_PORT}) aktif di MikroTik: /ip service set ssh port={SSH_PORT} disabled=no"
            ),
        }

    except Exception as e:
        logger.error(f"Backup failed for {device.get('name', device['id'])}: {e}")
        return {"success": False, "error": str(e)}


def list_backup_files() -> list:
    """List all backup files in the backup directory."""
    files = []
    for f in sorted(BACKUP_DIR.iterdir(), reverse=True):
        if f.is_file() and f.suffix in (".rsc", ".backup"):
            files.append({
                "filename": f.name,
                "size": f.stat().st_size,
                "created_at": datetime.fromtimestamp(f.stat().st_mtime, tz=timezone.utc).isoformat(),
                "type": f.suffix[1:],
            })
    return files


def get_backup_path(filename: str) -> Optional[Path]:
    """Get safe path for a backup file, ensuring no path traversal."""
    if not re.match(r"^[a-zA-Z0-9_.\-]+$", filename):
        return None
    path = BACKUP_DIR / filename
    if path.exists() and path.is_file():
        return path
    return None


def delete_backup_file(filename: str) -> bool:
    """Delete a backup file."""
    path = get_backup_path(filename)
    if path:
        path.unlink()
        return True
    return False


# ── Auto-Backup Scheduler ────────────────────────────────────────────────────

DEFAULT_BACKUP_HOUR = 19   # 02:00 WIB = 19:00 UTC
DEFAULT_BACKUP_MINUTE = 0
DEFAULT_RETENTION_DAYS = 30


async def _get_scheduler_config() -> dict:
    """Load scheduler config from DB (collection: scheduler_config)."""
    db = get_db()
    cfg = await db.scheduler_config.find_one({"type": "backup"}, {"_id": 0})
    if not cfg:
        cfg = {}
    return {
        "enabled": cfg.get("enabled", True),
        "hour_utc": cfg.get("hour_utc", DEFAULT_BACKUP_HOUR),
        "minute_utc": cfg.get("minute_utc", DEFAULT_BACKUP_MINUTE),
        "retention_days": cfg.get("retention_days", DEFAULT_RETENTION_DAYS),
    }


def cleanup_old_backups(retention_days: int = DEFAULT_RETENTION_DAYS) -> int:
    """Delete backup files older than retention_days. Returns count deleted."""
    from datetime import timedelta
    cutoff = datetime.now(timezone.utc) - timedelta(days=retention_days)
    deleted = 0
    for f in BACKUP_DIR.iterdir():
        if f.is_file() and f.suffix in (".rsc", ".backup"):
            mtime = datetime.fromtimestamp(f.stat().st_mtime, tz=timezone.utc)
            if mtime < cutoff:
                f.unlink()
                deleted += 1
                logger.info(f"Auto-cleanup: deleted old backup {f.name}")
    return deleted


async def backup_all_devices() -> dict:
    """
    Backup all online devices. Returns summary dict.
    Called by auto_backup_loop or manual trigger.
    """
    db = get_db()
    devices = await db.devices.find({"status": "online"}, {"_id": 0}).to_list(1000)
    total = len(devices)
    success = 0
    failed = 0
    errors = []

    logger.info(f"Auto backup started: {total} online devices")

    for device in devices:
        try:
            result = await backup_device_api(device)
            if result["success"]:
                success += 1
                logger.info(f"Auto backup OK: {device.get('name')} → {result.get('filename')}")
            else:
                failed += 1
                err = f"{device.get('name')}: {result.get('error', 'Unknown')}"
                errors.append(err)
                logger.warning(f"Auto backup failed: {err}")
        except Exception as e:
            failed += 1
            err = f"{device.get('name')}: {e}"
            errors.append(err)
            logger.error(f"Auto backup exception: {err}")

    # Simpan history ke DB
    summary = {
        "type": "auto_backup_run",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "total": total,
        "success": success,
        "failed": failed,
        "errors": errors[:20],  # cap agar tidak terlalu besar
    }
    await db.scheduler_history.insert_one({**summary})

    logger.info(f"Auto backup finished: {success}/{total} succeeded, {failed} failed")
    return summary


async def auto_backup_loop():
    """
    Background task: run backup_all_devices setiap hari pada jam yang dikonfigurasi.
    Default: 19:00 UTC (= 02:00 WIB).
    """
    import asyncio as _asyncio

    logger.info("Auto backup scheduler started")

    while True:
        try:
            cfg = await _get_scheduler_config()
            if not cfg["enabled"]:
                await _asyncio.sleep(300)  # cek lagi setelah 5 menit
                continue

            now = datetime.now(timezone.utc)
            target_hour = cfg["hour_utc"]
            target_minute = cfg["minute_utc"]

            # Hitung waktu tunggu sampai jam backup berikutnya
            next_run = now.replace(hour=target_hour, minute=target_minute, second=0, microsecond=0)
            if next_run <= now:
                # Sudah lewat hari ini → jadwalkan besok
                from datetime import timedelta
                next_run += timedelta(days=1)

            wait_seconds = (next_run - now).total_seconds()
            logger.info(f"Auto backup: next run at {next_run.isoformat()} (in {wait_seconds/3600:.1f}h)")

            await _asyncio.sleep(wait_seconds)

            # Jalankan backup
            await backup_all_devices()

            # Cleanup backup lama
            deleted = cleanup_old_backups(cfg["retention_days"])
            if deleted:
                logger.info(f"Auto-cleanup: {deleted} old backup files removed")

        except _asyncio.CancelledError:
            logger.info("Auto backup scheduler cancelled")
            break
        except Exception as e:
            logger.error(f"Auto backup loop error: {e}")
            await _asyncio.sleep(60)  # retry setelah 1 menit jika ada error
