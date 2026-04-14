"""
Speed Test Service: ukur latency dan HTTP response time dari server monitoring
ke setiap MikroTik device secara terjadwal.

Tidak membutuhkan iperf3 di sisi device — cukup:
  1. ICMP ping (sudah ada di ping_service)
  2. HTTP GET ke REST API device (mengukur round-trip API)
  3. TCP connect time ke port API device
"""
import asyncio
import logging
import time
from datetime import datetime, timezone
from typing import Optional
from core.db import get_db

logger = logging.getLogger(__name__)

SPEEDTEST_INTERVAL_SECONDS = 3600  # cek setiap 1 jam


async def _get_speedtest_config() -> dict:
    """Load speedtest config dari DB."""
    db = get_db()
    cfg = await db.scheduler_config.find_one({"type": "speedtest"}, {"_id": 0})
    if not cfg:
        cfg = {}
    return {
        "enabled": cfg.get("enabled", True),
        "interval_minutes": cfg.get("interval_minutes", 60),
        "ping_count": cfg.get("ping_count", 5),
        "http_timeout": cfg.get("http_timeout", 10),
    }


async def _measure_tcp_connect(host: str, port: int, timeout: float = 5.0) -> Optional[float]:
    """Ukur waktu TCP connection ke host:port. Return ms atau None jika gagal."""
    try:
        start = time.monotonic()
        reader, writer = await asyncio.wait_for(
            asyncio.open_connection(host, port),
            timeout=timeout
        )
        elapsed_ms = (time.monotonic() - start) * 1000
        writer.close()
        try:
            await writer.wait_closed()
        except Exception:
            pass
        return round(elapsed_ms, 2)
    except Exception:
        return None


async def _measure_http_response(device: dict, timeout: float = 10.0) -> Optional[float]:
    """
    Ukur HTTP response time ke REST API device.
    Menggunakan endpoint ringan: /rest/system/resource (atau /ip/service di ROS6).
    Return ms atau None jika gagal.
    """
    import httpx
    ip = device.get("ip_address", "")
    use_https = device.get("use_https", False)
    port = device.get("api_port") or (443 if use_https else 80)
    scheme = "https" if use_https else "http"
    username = device.get("api_username", "admin")
    password = device.get("api_password", "")

    if device.get("api_mode") == "api":
        # ROS6 — tidak pakai REST, skip HTTP test
        return None

    url = f"{scheme}://{ip}:{port}/rest/system/clock"

    try:
        start = time.monotonic()
        async with httpx.AsyncClient(
            verify=False,
            timeout=timeout,
            auth=(username, password) if username else None
        ) as client:
            resp = await client.get(url)
            elapsed_ms = (time.monotonic() - start) * 1000
            if resp.status_code in (200, 401, 403):  # 401/403 = device respond (auth issue)
                return round(elapsed_ms, 2)
            return None
    except Exception:
        return None


async def speedtest_device(device: dict, ping_count: int = 5) -> dict:
    """
    Jalankan speed test ke satu device. Return dict hasil.
    """
    from ping_service import ping_host
    device_id = device["id"]
    device_name = device.get("name", device_id)
    ip = device.get("ip_address", "")

    result = {
        "device_id": device_id,
        "device_name": device_name,
        "ip_address": ip,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "ping_ms": None,
        "ping_loss_pct": None,
        "http_ms": None,
        "tcp_ms": None,
        "status": "ok",
    }

    if not ip:
        result["status"] = "no_ip"
        return result

    # 1. ICMP Ping
    try:
        ping_result = await ping_host(ip, count=ping_count)
        result["ping_ms"] = ping_result.get("avg_ms")
        result["ping_loss_pct"] = ping_result.get("packet_loss_pct", 100)
        if result["ping_ms"] is None or result["ping_loss_pct"] == 100:
            result["status"] = "ping_fail"
    except Exception as e:
        logger.debug(f"Ping failed for {device_name}: {e}")
        result["status"] = "ping_fail"

    # 2. HTTP Response Time (REST API)
    try:
        http_ms = await _measure_http_response(device, timeout=10.0)
        result["http_ms"] = http_ms
    except Exception:
        pass

    # 3. TCP Connect Time (ke port API)
    api_port = device.get("api_port")
    if not api_port:
        api_port = 443 if device.get("use_https") else 80
        if device.get("api_mode") == "api":
            api_port = 8729 if device.get("api_ssl", True) else 8728

    try:
        tcp_ms = await _measure_tcp_connect(ip, int(api_port), timeout=5.0)
        result["tcp_ms"] = tcp_ms
    except Exception:
        pass

    return result


async def speedtest_all_devices(ping_count: int = 5) -> dict:
    """Jalankan speed test ke semua device online secara concurrent."""
    db = get_db()
    devices = await db.devices.find({"status": "online"}, {"_id": 0}).to_list(1000)
    total = len(devices)

    if total == 0:
        return {"total": 0, "results": [], "timestamp": datetime.now(timezone.utc).isoformat()}

    logger.info(f"Speed test started: {total} online devices")

    # Jalankan concurrent, tapi batasi 10 device sekaligus agar tidak overload
    semaphore = asyncio.Semaphore(10)

    async def _run_with_sem(device):
        async with semaphore:
            return await speedtest_device(device, ping_count=ping_count)

    results = await asyncio.gather(*[_run_with_sem(d) for d in devices], return_exceptions=True)

    valid_results = []
    for r in results:
        if isinstance(r, dict):
            valid_results.append(r)
            # Simpan ke DB
            try:
                await db.speedtest_results.insert_one({**r})
            except Exception:
                pass
        elif isinstance(r, Exception):
            logger.debug(f"Speedtest exception: {r}")

    logger.info(f"Speed test finished: {len(valid_results)}/{total} completed")

    return {
        "total": total,
        "completed": len(valid_results),
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "results": valid_results,
    }


async def speedtest_loop():
    """
    Background task: jalankan speed test ke semua device setiap 1 jam.
    """
    logger.info("Speed test scheduler started")

    # Tunggu 5 menit setelah startup sebelum test pertama
    await asyncio.sleep(300)

    while True:
        try:
            cfg = await _get_speedtest_config()
            if not cfg["enabled"]:
                await asyncio.sleep(300)
                continue

            await speedtest_all_devices(ping_count=cfg["ping_count"])

            interval = cfg["interval_minutes"] * 60
            logger.info(f"Speed test done. Next in {cfg['interval_minutes']} minutes")
            await asyncio.sleep(interval)

        except asyncio.CancelledError:
            logger.info("Speed test scheduler cancelled")
            break
        except Exception as e:
            logger.error(f"Speed test loop error: {e}")
            await asyncio.sleep(120)
