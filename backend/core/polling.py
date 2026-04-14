"""
core/polling.py — NOC Sentinel v3 (Push Telemetry Edition)
============================================================
Polling loop HANYA untuk:
  1. ICMP Ping setiap 10 menit per device → update status online/offline
  2. Auto-discovery API mode (hanya saat device baru ditambahkan)

Traffic, CPU, RAM, Logs → semua via Streaming Push:
  - NetFlow v9  (services/netflow_receiver.py)  → Traffic bandwidth
  - Syslog UDP  (syslog_server.py)              → CPU, RAM, Logs

Fungsi yang diekspor:
  - poll_single_device(device)  → untuk trigger manual (test connection)
  - polling_loop()              → background ping scanner (10 menit interval)
"""

import asyncio
import logging
import socket
from datetime import datetime, timezone

from core.db import get_db
from mikrotik_api import get_host_only, get_api_client, discover_device
import ping_service

logger = logging.getLogger(__name__)

# ── Konstanta ──────────────────────────────────────────────────────────────────
PING_INTERVAL     = 600     # 10 menit antar siklus scan semua device
PING_COUNT        = 3       # Jumlah ping per device untuk rata-rata
PING_TIMEOUT      = 5       # Timeout per ping (detik)
OFFLINE_GRACE     = 3       # Kegagalan beruntun sebelum tandai offline
MAX_CONCURRENT    = 50      # Semaphore worker pool

# ── State tracker ─────────────────────────────────────────────────────────────
_device_tick: dict = {}      # device_id → consecutive_failures (int)
_pppoe_cycle: dict = {}      # device_id → cycle counter untuk throttle PPPoE/Hotspot poll
PPPOE_POLL_EVERY_N_CYCLES = 6   # Poll PPPoE/Hotspot setiap 6 cycles = 60 menit (WINBOX FIX: kurangi load)
                                # ── Mengurangi beban API calls berat ke MikroTik ────
ISP_POLL_EVERY_N_CYCLES   = 3   # Poll ISP interfaces setiap 3 cycles = 30 menit


# ══════════════════════════════════════════════════════════════════════════════
# Auto-Discovery (dijalankan sekali saat device pertama kali poll)
# ══════════════════════════════════════════════════════════════════════════════

async def _ensure_api_mode(device: dict, db) -> dict:
    """Jalankan auto-discover API mode hanya jika belum diketahui."""
    if device.get("api_mode") in ("rest", "api"):
        return device

    logger.info(f"Auto-discover: {device.get('name','?')} [{device.get('ip_address','?')}]...")
    disc = await discover_device(device)

    if disc["success"]:
        upf = {
            "api_mode":    disc["api_mode"],
            "ros_version": disc.get("ros_version", ""),
            "model":       disc.get("board_name", "") or device.get("model", ""),
        }
        if disc["api_mode"] == "rest":
            upf["use_https"] = disc.get("use_https", False)
            if disc.get("rest_port"):
                upf["api_port"] = disc["rest_port"]
        elif disc.get("api_port"):
            upf["api_port"] = disc["api_port"]

        await db.devices.update_one({"id": device["id"]}, {"$set": upf})
        device = {**device, **upf}
        logger.info(f"Discovery OK: {device.get('name','?')} → mode={disc['api_mode']}")
    else:
        logger.warning(f"Discovery GAGAL: {device.get('name','?')} — gunakan mode default 'rest'")
        device = {**device, "api_mode": "rest"}

    return device


# ══════════════════════════════════════════════════════════════════════════════
# Ping-Only Device Checker
# ══════════════════════════════════════════════════════════════════════════════

async def poll_single_device(device: dict) -> dict:
    """
    Lakukan ICMP ping ke device, update status online/offline, dan simpan
    rata-rata latency & jitter ke MongoDB. Tidak ada traffic/CPU/RAM polling.

    Dikembalikan: dict dengan key 'reachable', 'avg_ms', 'jitter_ms'.
    """
    db      = get_db()
    did     = device["id"]
    dev_name = device.get("name", device.get("ip_address", "?"))
    ip      = get_host_only(device.get("ip_address", ""))

    if not ip:
        logger.warning(f"[Ping] Device {dev_name} tidak punya IP valid, skip.")
        return {"reachable": False, "avg_ms": 0, "jitter_ms": 0}

    # ── Auto-discover API mode jika belum ada ────────────────────────────────
    if not device.get("api_mode"):
        device = await _ensure_api_mode(device, db)

    # ── Suppress login logging (sekali saja) ─────────────────────────────────
    if not device.get("logging_suppressed") and device.get("status") == "online":
        try:
            mt = get_api_client(device)
            ok = await asyncio.wait_for(mt.suppress_account_logging(), timeout=6.0)
            if ok:
                await db.devices.update_one({"id": did}, {"$set": {"logging_suppressed": True}})
        except Exception:
            pass

    # ── ICMP Ping ─────────────────────────────────────────────────────────────
    ping_result = {"reachable": False, "avg": 0, "jitter": 0, "min": 0, "max": 0, "loss": 100}
    try:
        ping_result = await asyncio.wait_for(
            ping_service.ping_host(ip, count=PING_COUNT, timeout=PING_TIMEOUT),
            timeout=PING_COUNT * PING_TIMEOUT + 5
        )
    except Exception as e:
        logger.debug(f"[Ping] {dev_name} ({ip}): {e}")

    reachable  = ping_result.get("reachable", False)
    avg_ms     = float(ping_result.get("avg") or 0)
    jitter_ms  = float(ping_result.get("jitter") or 0)

    # ── Status / Grace Period ─────────────────────────────────────────────────
    old_status  = device.get("status", "unknown")
    fail_key    = f"{did}_fails"
    consecutive = int(_device_tick.get(fail_key, device.get("consecutive_poll_failures") or 0))

    if reachable:
        new_status  = "online"
        consecutive = 0
    else:
        consecutive += 1
        new_status = "offline" if consecutive >= OFFLINE_GRACE else old_status

    _device_tick[fail_key] = consecutive
    now_iso = datetime.now(timezone.utc).isoformat()

    # ── Tulis ke DB ───────────────────────────────────────────────────────────
    update: dict = {
        "status":                    new_status,
        "last_poll":                 now_iso,
        "consecutive_poll_failures": consecutive,
        "ping_avg":                  round(avg_ms, 1),
        "ping_jitter":               round(jitter_ms, 1),
    }

    # API poller untuk PPPoE/Hotspot count & resources
    if reachable:
        pppoe_count   = 0
        hotspot_count = 0
        ros_version   = ""
        uptime        = ""
        isp_ifaces    = []

        update_fields = {
            **update,
            "last_traffic.ping_ms":    round(avg_ms, 1),
            "last_traffic.jitter_ms":  round(jitter_ms, 1),
        }

        # ── Throttle API calls ke MikroTik (WINBOX PERFORMANCE FIX) ────────────
        # Setiap REST API call = 1 log entry di MikroTik (bahkan setelah logging suppressed!
        # karena suppression mungkin belum efektif atau gagal). Kurangi semaksimal mungkin.
        cycle_key     = f"{did}_pppoe_cycle"
        current_cycle = _pppoe_cycle.get(cycle_key, 0)
        should_poll_pppoe = (current_cycle % PPPOE_POLL_EVERY_N_CYCLES == 0)
        should_poll_isp   = (current_cycle % ISP_POLL_EVERY_N_CYCLES   == 0)
        _pppoe_cycle[cycle_key] = current_cycle + 1

        if should_poll_pppoe:
            try:
                mt = get_api_client(device)
                # Fetch concurrently — pisahkan ISP detection (ringan) dari PPPoE/Hotspot (berat)
                res_pppoe, res_hotspot, sys_res, isp_res, out_res = await asyncio.gather(
                    asyncio.wait_for(mt.list_pppoe_active(),   timeout=8.0),
                    asyncio.wait_for(mt.list_hotspot_active(), timeout=8.0),
                    asyncio.wait_for(mt.get_system_resource(), timeout=5.0),
                    asyncio.wait_for(mt.get_isp_interfaces(),  timeout=5.0),
                    asyncio.wait_for(mt.get_out_interfaces(),  timeout=5.0),
                    return_exceptions=True
                )

                if isinstance(res_pppoe,   list): pppoe_count   = len(res_pppoe)
                if isinstance(res_hotspot, list): hotspot_count = len(res_hotspot)
                if isinstance(sys_res, dict):
                    ros_version = sys_res.get("version", "")
                    uptime      = sys_res.get("uptime", "")
                    try:
                        update_fields["cpu_load"] = int(sys_res.get("cpu-load", 0))
                    except: pass
                if isinstance(isp_res, list) and isp_res:
                    isp_ifaces = isp_res
                if isinstance(out_res, list) and out_res:
                    out_ifaces = out_res
            except Exception as e:
                logger.debug(f"[Ping] {dev_name} API Fetch failed: {e}")

            update_fields["pppoe_active"]   = pppoe_count
            update_fields["hotspot_active"] = hotspot_count
            if ros_version:
                update_fields["ros_version"] = ros_version
            if uptime:
                update_fields["uptime"] = uptime
            if isp_ifaces:
                update_fields["isp_interfaces"] = isp_ifaces
                logger.debug(f"[Ping] {dev_name} ISP interfaces detected: {isp_ifaces}")
            if 'out_ifaces' in locals() and out_ifaces:
                update_fields["out_interfaces"] = out_ifaces
        elif should_poll_isp:
            # Poll hanya ISP interfaces + system resource (lebih ringan dari full PPPoE)
            try:
                mt = get_api_client(device)
                sys_res, isp_res, out_res = await asyncio.gather(
                    asyncio.wait_for(mt.get_system_resource(), timeout=5.0),
                    asyncio.wait_for(mt.get_isp_interfaces(),  timeout=5.0),
                    asyncio.wait_for(mt.get_out_interfaces(),  timeout=5.0),
                    return_exceptions=True
                )
                if isinstance(sys_res, dict):
                    ros_version = sys_res.get("version", "")
                    uptime      = sys_res.get("uptime", "")
                    try:
                        update_fields["cpu_load"] = int(sys_res.get("cpu-load", 0))
                    except: pass
                if isinstance(isp_res, list) and isp_res:
                    isp_ifaces = isp_res
                if isinstance(out_res, list) and out_res:
                    out_ifaces = out_res
            except Exception as e:
                logger.debug(f"[Ping] {dev_name} lightweight fetch failed: {e}")

            if ros_version:
                update_fields["ros_version"] = ros_version
            if uptime:
                update_fields["uptime"] = uptime
            if isp_ifaces:
                update_fields["isp_interfaces"] = isp_ifaces
            if 'out_ifaces' in locals() and out_ifaces:
                update_fields["out_interfaces"] = out_ifaces
        else:
            try:
                # ── ALWAYS POLL CPU EVERY CYCLE (ROS 7 Fallback) ──
                mt = get_api_client(device)
                sys_res = await asyncio.wait_for(mt.get_system_resource(), timeout=3.0)
                if isinstance(sys_res, dict):
                    try: update_fields["cpu_load"] = int(sys_res.get("cpu-load", 0))
                    except: pass
                    if "version" in sys_res: update_fields["ros_version"] = sys_res["version"]
                    if "uptime" in sys_res:  update_fields["uptime"] = sys_res["uptime"]
            except Exception:
                pass
            # Cycle ini SKIP API call — hanya ping, tidak ada koneksi ke MikroTik
            # Ini yang membuat Winbox tidak berat: tidak ada TCP connection dibuka!
            logger.debug(f"[Ping] {dev_name}: API call di-skip (cycle throttle, cycle={current_cycle})")

        await db.devices.update_one(
            {"id": did},
            {"$set": update_fields}
        )

    else:
        await db.devices.update_one({"id": did}, {"$set": update})

    # ── SLA Event saat status berubah ─────────────────────────────────────────
    if old_status != new_status and new_status in ("online", "offline"):
        logger.info(f"[Ping] {dev_name}: {old_status} → {new_status} (ping avg={avg_ms:.1f}ms)")
        try:
            await db.sla_events.insert_one({
                "device_id":   did,
                "device_name": dev_name,
                "event_type":  new_status,
                "from_status": old_status,
                "timestamp":   now_iso,
            })
        except Exception:
            pass

    return {"reachable": reachable, "avg_ms": avg_ms, "jitter_ms": jitter_ms}


# ══════════════════════════════════════════════════════════════════════════════
# Ping Scanner Loop (10 Menit)
# ══════════════════════════════════════════════════════════════════════════════

async def polling_loop():
    """
    Background loop: ICMP ping scan ke semua device setiap PING_INTERVAL detik.
    Traffic/CPU/RAM sudah dihandle oleh NetFlow receiver dan Syslog interceptor.
    """
    semaphore = asyncio.Semaphore(MAX_CONCURRENT)

    async def ping_with_jitter(dev: dict, index: int):
        # Jitter kecil agar tidak semua device dipong serentak
        jitter_sec = 0.1 * (index % 30)
        await asyncio.sleep(jitter_sec)
        async with semaphore:
            try:
                await asyncio.wait_for(poll_single_device(dev), timeout=30)
            except asyncio.TimeoutError:
                pass
            except Exception as e:
                logger.error(f"[Ping] Error {dev.get('name','?')}: {e}")

    logger.info(f"[PingScanner] Loop dimulai — interval {PING_INTERVAL}s ({PING_INTERVAL//60} menit)")
    last_scan = 0.0

    while True:
        current_time = asyncio.get_running_loop().time()

        if current_time - last_scan < PING_INTERVAL:
            await asyncio.sleep(5.0)
            continue

        last_scan = current_time
        logger.info("[PingScanner] Memulai scan ping semua device...")

        try:
            db      = get_db()
            devices = await db.devices.find(
                {},
                {"_id": 0, "id": 1, "name": 1, "ip_address": 1, "status": 1,
                 "api_mode": 1, "api_username": 1, "api_password": 1,
                 "api_port": 1, "use_https": 1, "api_ssl": 1, "api_plaintext_login": 1,
                 "consecutive_poll_failures": 1, "logging_suppressed": 1,
                 "last_traffic": 1}
            ).to_list(None)

            if devices:
                tasks = [ping_with_jitter(d, i) for i, d in enumerate(devices)]
                await asyncio.gather(*tasks, return_exceptions=True)
                logger.info(f"[PingScanner] Selesai — {len(devices)} device di-ping.")

        except asyncio.CancelledError:
            logger.info("[PingScanner] Loop dihentikan.")
            break
        except Exception as e:
            logger.error(f"[PingScanner] Fatal error: {e}")

        await asyncio.sleep(1.0)

