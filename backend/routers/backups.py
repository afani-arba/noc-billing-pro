"""
Backups router: trigger, list, download, and delete MikroTik config backups.
"""
import logging
from fastapi import APIRouter, HTTPException, Depends
from fastapi.responses import FileResponse
from services.backup_service import (
    backup_device_api, list_backup_files, get_backup_path, delete_backup_file
)
from core.db import get_db
from core.auth import get_current_user, require_admin

router = APIRouter(prefix="/backups", tags=["backups"])
logger = logging.getLogger(__name__)


@router.get("")
async def list_backups(user=Depends(get_current_user)):
    """List all available backup files."""
    return list_backup_files()


@router.post("/trigger/{device_id}")
async def trigger_backup(device_id: str, user=Depends(require_admin)):
    """Trigger a manual backup for a specific device."""
    db = get_db()
    device = await db.devices.find_one({"id": device_id}, {"_id": 0})
    if not device:
        raise HTTPException(404, "Device not found")
    if device.get("status") != "online":
        raise HTTPException(400, f"Device {device.get('name', device_id)} is offline. Cannot backup offline device.")
    result = await backup_device_api(device)
    if result["success"]:
        return result
    raise HTTPException(503, f"Backup failed: {result.get('error', 'Unknown error')}")


@router.get("/download/{filename}")
async def download_backup(filename: str, user=Depends(get_current_user)):
    """Download a backup file."""
    path = get_backup_path(filename)
    if not path:
        raise HTTPException(404, "Backup file not found")
    return FileResponse(
        path=str(path),
        filename=filename,
        media_type="application/octet-stream"
    )


@router.delete("/{filename}")
async def delete_backup(filename: str, user=Depends(require_admin)):
    """Delete a backup file."""
    ok = delete_backup_file(filename)
    if not ok:
        raise HTTPException(404, "Backup file not found")
    return {"message": f"Backup {filename} deleted"}


@router.get("/diff")
async def diff_backups(
    file_a: str,
    file_b: str,
    user=Depends(get_current_user)
):
    """
    Bandingkan dua file backup RSC dan tampilkan unified diff.
    Digunakan untuk mendeteksi perubahan konfigurasi antar backup.
    Response: {diff: [...lines], additions: int, removals: int, changed: bool}
    """
    import difflib

    path_a = get_backup_path(file_a)
    path_b = get_backup_path(file_b)

    if not path_a:
        raise HTTPException(404, f"Backup '{file_a}' tidak ditemukan")
    if not path_b:
        raise HTTPException(404, f"Backup '{file_b}' tidak ditemukan")

    try:
        lines_a = path_a.read_text(encoding="utf-8", errors="replace").splitlines(keepends=True)
        lines_b = path_b.read_text(encoding="utf-8", errors="replace").splitlines(keepends=True)

        diff = list(difflib.unified_diff(
            lines_a, lines_b,
            fromfile=file_a,
            tofile=file_b,
            n=3,
        ))

        additions = sum(1 for l in diff if l.startswith("+") and not l.startswith("+++"))
        removals  = sum(1 for l in diff if l.startswith("-") and not l.startswith("---"))

        return {
            "diff":      [l.rstrip("\n") for l in diff],
            "additions": additions,
            "removals":  removals,
            "changed":   len(diff) > 0,
            "file_a":    file_a,
            "file_b":    file_b,
        }
    except Exception as e:
        raise HTTPException(500, f"Gagal membandingkan backup: {e}")

