import asyncio
import logging
import json
import re
from datetime import datetime, timezone
from core.db import get_db

logger = logging.getLogger("zapret_monitor")

async def _run_host_cmd(args: list) -> tuple[bool, str]:
    """Jalankan command di HOST via nsenter (sama seperti GoBGP)."""
    cmd = ["nsenter", "-t", "1", "-m", "-u", "-i", "-n", "-p", "--"] + args
    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
        )
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=10)
        return proc.returncode == 0, (stdout + stderr).decode().strip()
    except Exception as e:
        logger.error(f"nsenter command failed: {e}")
        return False, str(e)

async def _poll_zapret_status() -> dict:
    status_data = {
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
    
    # 1. Cek status service
    ok, is_active = await _run_host_cmd(["systemctl", "is-active", "zapret"])
    status_data["running"] = (is_active == "active")

    if status_data["running"]:
        # 2. Ambil PID nfqws
        ok_pid, pid_out = await _run_host_cmd(["pidof", "nfqws"])
        if ok_pid and pid_out:
            pids = pid_out.split()
            if pids:
                status_data["pid"] = int(pids[0])

        # 3. Ambil Uptime
        ok_uptime, uptime_out = await _run_host_cmd(["systemctl", "show", "zapret", "-p", "ActiveEnterTimestamp", "--value"])
        if ok_uptime and uptime_out:
            # Output format: Thu 2026-04-30 14:00:00 WIB
            try:
                # We can just use bash to get uptime in seconds
                ok_sec, sec_out = await _run_host_cmd(["bash", "-c", 'echo $(($(date +%s) - $(date -d "$(systemctl show zapret -p ActiveEnterTimestamp --value)" +%s)))'])
                if ok_sec and sec_out.isdigit():
                    status_data["uptime_seconds"] = int(sec_out)
            except Exception:
                pass

        # 4. Ambil stats dari proc (jika PID valid)
        if status_data["pid"] > 0:
            pid = status_data["pid"]
            # RAM
            ok_mem, mem_out = await _run_host_cmd(["bash", "-c", f"grep VmRSS /proc/{pid}/status | awk '{{print $2}}'"])
            if ok_mem and mem_out.isdigit():
                status_data["ram_mb"] = round(int(mem_out) / 1024, 2)
            
            # CPU (ps)
            ok_cpu, cpu_out = await _run_host_cmd(["ps", "-p", str(pid), "-o", "%cpu", "--no-headers"])
            if ok_cpu and cpu_out.strip():
                try:
                    status_data["cpu_percent"] = float(cpu_out.strip())
                except ValueError:
                    pass

        # 5. Packets & Bytes (DPI Bypass counts)
        # Zapret uses nftables generally. We can extract packet counters from nftables if zapret tables exist.
        ok_nft, nft_out = await _run_host_cmd(["nft", "list", "counters"])
        if ok_nft:
            # Look for packets and bytes counts for zapret-related rules. This is a heuristic.
            # E.g. packets 1234 bytes 5678
            packets = 0
            bytes_c = 0
            for line in nft_out.split('\n'):
                m = re.search(r'packets\s+(\d+)\s+bytes\s+(\d+)', line)
                if m:
                    packets += int(m.group(1))
                    bytes_c += int(m.group(2))
            
            # If nft counters don't give much, fallback to iptables if it's used
            if packets == 0:
                ok_ipt, ipt_out = await _run_host_cmd(["iptables", "-L", "PREROUTING", "-t", "mangle", "-v", "-n"])
                if ok_ipt:
                    for line in ipt_out.split('\n'):
                        if "NFQUEUE" in line:
                            parts = line.split()
                            if len(parts) >= 2 and parts[0].isdigit():
                                packets += int(parts[0])
                                bytes_c += int(parts[1])

            status_data["packets_processed"] = packets
            status_data["bytes_processed"] = bytes_c

    # 6. Read Config
    ok_cfg, cfg_out = await _run_host_cmd(["cat", "/opt/zapret/config"])
    if ok_cfg:
        for line in cfg_out.split('\n'):
            line = line.strip()
            if line.startswith("MODE="):
                status_data["config_mode"] = line.split("=", 1)[1].strip('"\'')
            elif line.startswith("NFQWS_OPT="):
                status_data["nfqws_opt"] = line.split("=", 1)[1].strip('"\'')

    return status_data

async def zapret_monitor_loop():
    """Background service untuk memonitor Zapret DPI Bypass."""
    logger.info("Zapret monitor loop started.")
    await asyncio.sleep(5)  # Delay startup
    
    while True:
        try:
            status = await _poll_zapret_status()
            
            doc = status.copy()
            doc["_id"] = "zapret_status"
            doc["updated_at"] = datetime.now(timezone.utc).isoformat()
            
            db = get_db()
            await db.system_settings.replace_one(
                {"_id": "zapret_status"},
                doc,
                upsert=True
            )
        except Exception as e:
            logger.error(f"Error in Zapret monitor: {e}")
        
        await asyncio.sleep(30)
