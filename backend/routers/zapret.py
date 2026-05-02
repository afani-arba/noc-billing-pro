from fastapi import APIRouter, Depends, HTTPException, Body
from datetime import datetime, timezone
import asyncio
from core.db import get_db
from core.auth import get_current_user, require_write, require_admin

router = APIRouter(prefix="/zapret", tags=["Zapret"])

async def _run_host_cmd(args: list) -> tuple[bool, str]:
    cmd = ["nsenter", "-t", "1", "-m", "-u", "-i", "-n", "-p", "--"] + args
    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
        )
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=15)
        return proc.returncode == 0, (stdout + stderr).decode().strip()
    except Exception as e:
        return False, str(e)

@router.get("/status")
async def get_zapret_status(user=Depends(get_current_user)):
    db = get_db()
    status = await db.system_settings.find_one({"_id": "zapret_status"}, {"_id": 0})
    if not status:
        return {
            "running": False,
            "pid": 0,
            "uptime_seconds": 0,
            "cpu_percent": 0.0,
            "ram_mb": 0.0,
            "packets_processed": 0,
            "bytes_processed": 0,
            "config_mode": "",
            "nfqws_opt": ""
        }
    return status

@router.post("/start")
async def start_zapret(user=Depends(require_write)):
    ok, out = await _run_host_cmd(["systemctl", "start", "zapret"])
    if not ok:
        raise HTTPException(500, f"Failed to start Zapret: {out}")
    return {"message": "Zapret started"}

@router.post("/stop")
async def stop_zapret(user=Depends(require_write)):
    ok, out = await _run_host_cmd(["systemctl", "stop", "zapret"])
    if not ok:
        raise HTTPException(500, f"Failed to stop Zapret: {out}")
    return {"message": "Zapret stopped"}

@router.post("/restart")
async def restart_zapret(user=Depends(require_write)):
    ok, out = await _run_host_cmd(["systemctl", "restart", "zapret"])
    if not ok:
        raise HTTPException(500, f"Failed to restart Zapret: {out}")
    return {"message": "Zapret restarted"}

DEFAULT_ZAPRET_CONFIG = """# MODE: nfqws, tpws, tpws-socks, filter, custom
MODE=nfqws
DISABLE_IPV4=0
DISABLE_IPV6=1
FWTYPE=nftables
NFQWS_OPT="--dpi-desync=disorder2 --dpi-desync-split-pos=2 --dpi-desync-ttl=4"
"""

@router.get("/config")
async def get_zapret_config(user=Depends(get_current_user)):
    ok, out = await _run_host_cmd(["cat", "/opt/zapret/config"])
    if not ok:
        # Jika tidak ada config, kembalikan default template daripada error
        return {"config": DEFAULT_ZAPRET_CONFIG, "is_default": True}
    return {"config": out, "is_default": False}

@router.put("/config")
async def save_zapret_config(body: dict = Body(...), user=Depends(require_write)):
    new_config = body.get("config", "")
    if not new_config:
        raise HTTPException(400, "Config content cannot be empty")
    
    # Pastikan direktori ada di host
    await _run_host_cmd(["mkdir", "-p", "/opt/zapret"])

    # Simpan ke temporary file dulu di host
    ok_echo, out_echo = await _run_host_cmd(["bash", "-c", f"cat << 'EOF' > /tmp/zapret_config.tmp\n{new_config}\nEOF"])
    if not ok_echo:
        raise HTTPException(500, f"Failed to write temp config file: {out_echo}")
        
    ok_mv, out_mv = await _run_host_cmd(["mv", "/tmp/zapret_config.tmp", "/opt/zapret/config"])
    if not ok_mv:
        raise HTTPException(500, f"Failed to apply new config: {out_mv}")
        
    ok_res, out_res = await _run_host_cmd(["systemctl", "restart", "zapret"])
    return {"message": "Configuration saved and Zapret restarted"}

@router.get("/logs")
async def get_zapret_logs(user=Depends(get_current_user)):
    ok, out = await _run_host_cmd(["journalctl", "-u", "zapret", "-n", "50", "--no-pager"])
    if not ok:
        return {"logs": f"Failed to fetch logs: {out}"}
    return {"logs": out}
