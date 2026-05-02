from fastapi import APIRouter, Depends, HTTPException, Body
from datetime import datetime, timezone
import asyncio
from core.db import get_db
from core.auth import get_current_user, require_write, require_admin

router = APIRouter(prefix="/zapret", tags=["Zapret"])

async def _run_host_cmd(args: list) -> tuple[bool, str]:
    """Jalankan perintah di host OS menggunakan nsenter ke PID 1."""
    # Gunakan path absolut nsenter, hanya masuk ke mount namespace
    nsenter = "/usr/bin/nsenter"
    import shutil
    if not shutil.which("nsenter") and shutil.which("/usr/bin/nsenter"):
        nsenter = "/usr/bin/nsenter"
    elif shutil.which("nsenter"):
        nsenter = shutil.which("nsenter")

    cmd = [nsenter, "-t", "1", "-m", "-u", "-i", "-n", "-p", "--"] + args
    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
        )
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=15)
        out = (stdout + stderr).decode(errors="replace").strip()
        return proc.returncode == 0, out
    except Exception as e:
        return False, str(e)


async def _run_host_sh(script: str) -> tuple[bool, str]:
    """Jalankan shell script di host OS."""
    import shutil
    nsenter = shutil.which("nsenter") or "/usr/bin/nsenter"
    cmd = [nsenter, "-t", "1", "-m", "-u", "-i", "-n", "-p", "--", "/bin/sh", "-c", script]
    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
        )
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=20)
        out = (stdout + stderr).decode(errors="replace").strip()
        return proc.returncode == 0, out
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
    ok, out = await _run_host_sh("systemctl start zapret 2>&1 || /bin/systemctl start zapret 2>&1")
    if not ok:
        raise HTTPException(500, f"Failed to start Zapret: {out}")
    return {"message": "Zapret started"}

@router.post("/stop")
async def stop_zapret(user=Depends(require_write)):
    ok, out = await _run_host_sh("systemctl stop zapret 2>&1 || /bin/systemctl stop zapret 2>&1")
    if not ok:
        raise HTTPException(500, f"Failed to stop Zapret: {out}")
    return {"message": "Zapret stopped"}

@router.post("/restart")
async def restart_zapret(user=Depends(require_write)):
    ok, out = await _run_host_sh("systemctl restart zapret 2>&1 || /bin/systemctl restart zapret 2>&1")
    if not ok:
        raise HTTPException(500, f"Failed to restart Zapret: {out}")
    return {"message": "Zapret restarted"}

@router.get("/diag")
async def zapret_diag(user=Depends(require_write)):
    """Endpoint diagnostik untuk debug koneksi nsenter ke host."""
    results = {}
    ok_which, out_which = await _run_host_sh("which systemctl && systemctl --version 2>&1 | head -2")
    results["systemctl"] = {"ok": ok_which, "out": out_which}
    ok_ls, out_ls = await _run_host_sh("ls /opt/zapret/ 2>&1")
    results["zapret_dir"] = {"ok": ok_ls, "out": out_ls}
    ok_svc, out_svc = await _run_host_sh("systemctl is-active zapret 2>&1")
    results["zapret_service"] = {"active": ok_svc, "status": out_svc}
    return results

DEFAULT_ZAPRET_CONFIG = """# ===================================================================
# ZAPRET CONFIGURATION FOR INDONESIAN BROADBAND ISPs
# ===================================================================

# MODE: nfqws, tpws, tpws-socks, filter, custom
MODE=nfqws
DISABLE_IPV4=0
DISABLE_IPV6=1
FWTYPE=nftables

# -------------------------------------------------------------------
# DPI BYPASS STRATEGIES (Uncomment salah satu yang sesuai dengan ISP)
# -------------------------------------------------------------------

# 1. IndiHome / Indibiz / Telkomsel (Typical Telkom DPI)
# Sering kali membutuhkan disorder atau split pada posisi host
# NFQWS_OPT="--dpi-desync=fake,disorder2 --dpi-desync-split-pos=1 --dpi-desync-ttl=8 --dpi-desync-fooling=md5sig"

# 2. Iconnet / PLN
# Biasanya cukup dengan split sederhana atau disorder
# NFQWS_OPT="--dpi-desync=disorder2 --dpi-desync-split-pos=2"

# 3. Starlink Indonesia
# Starlink global routing umumnya tidak ketat, tapi jika ada pemblokiran lokal:
# NFQWS_OPT="--dpi-desync=split2 --dpi-desync-split-pos=1"

# 4. Biznet / MyRepublic / FirstMedia
# Cenderung menggunakan DNS filtering + SNI sniffing ringan
# NFQWS_OPT="--dpi-desync=fake,split2 --dpi-desync-ttl=4"

# 5. Default Universal (Lebih aman untuk berbagai ISP)
NFQWS_OPT="--dpi-desync=disorder2 --dpi-desync-split-pos=2 --dpi-desync-ttl=4"
"""

@router.get("/config")
async def get_zapret_config(user=Depends(get_current_user)):
    ok, out = await _run_host_sh("cat /opt/zapret/config 2>&1")
    if not ok or not out.strip():
        return {"config": DEFAULT_ZAPRET_CONFIG, "is_default": True}
    return {"config": out, "is_default": False}

@router.put("/config")
async def save_zapret_config(body: dict = Body(...), user=Depends(require_write)):
    new_config = body.get("config", "")
    if not new_config:
        raise HTTPException(400, "Config content cannot be empty")

    # Pastikan direktori ada di host
    await _run_host_sh("mkdir -p /opt/zapret")

    # Escape single quotes dan tulis via printf untuk keamanan
    escaped = new_config.replace("'", "'\"'\"'")
    ok_w, out_w = await _run_host_sh(f"printf '%s' '{escaped}' > /opt/zapret/config")
    if not ok_w:
        raise HTTPException(500, f"Failed to write config: {out_w}")

    ok_res, out_res = await _run_host_sh("systemctl restart zapret 2>&1 || true")
    return {"message": "Configuration saved", "restart_output": out_res}

@router.get("/logs")
async def get_zapret_logs(user=Depends(get_current_user)):
    ok, out = await _run_host_sh("journalctl -u zapret -n 50 --no-pager 2>&1")
    if not ok:
        return {"logs": f"Failed to fetch logs: {out}"}
    return {"logs": out}
