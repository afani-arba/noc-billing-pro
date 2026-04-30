"""
Latency Monitor Service — NOC Billing Pro
==========================================
Background service yang melakukan ping dari setiap MikroTik router
ke gateway ISP masing-masing setiap 30 detik.

Data disimpan ke MongoDB collection: latency_metrics (timeseries)
Threshold alert: Warning >30ms, Critical >80ms atau loss >5%
"""
import asyncio
import logging
from datetime import datetime, timezone
from core.db import get_db
from mikrotik_api import get_api_client

logger = logging.getLogger("latency_monitor")

# Gateway targets — ping ke gateway ISP upstream
DEFAULT_GATEWAYS = ["8.8.8.8", "1.1.1.1"]

POLL_INTERVAL = 30   # detik
MAX_HISTORY = 2880   # ~24 jam data per device per gateway (30s interval)


async def _ping_from_router(mt, gateway: str, count: int = 5) -> dict:
    """
    Jalankan ping dari router via MikroTik API.
    Return: {avg_rtt, max_rtt, min_rtt, jitter, packet_loss}
    """
    try:
        results = await mt.ping_host(address=gateway, count=count)
        if not results or not isinstance(results, list):
            return {"avg_rtt": 0, "max_rtt": 0, "min_rtt": 0, "jitter": 0, "packet_loss": 100}

        rtts = []
        received = 0
        for r in results:
            # ROS 7 format: {"time": "12ms 345us", "status": ""}
            # atau: {"avg-rtt": "12ms", "packet-loss": "0"}
            time_str = str(r.get("time", ""))
            if time_str and "ms" in time_str:
                try:
                    # Parse "12ms 345us" → 12.345 atau "12ms" → 12.0
                    ms_part = time_str.split("ms")[0].strip()
                    rtt = float(ms_part)
                    rtts.append(rtt)
                    received += 1
                except (ValueError, IndexError):
                    pass
            elif r.get("avg-rtt"):
                # Aggregated format
                try:
                    avg_str = str(r["avg-rtt"]).replace("ms", "").strip()
                    avg_val = float(avg_str)
                    return {
                        "avg_rtt": round(avg_val, 2),
                        "max_rtt": round(float(str(r.get("max-rtt", avg_str)).replace("ms", "").strip()), 2),
                        "min_rtt": round(float(str(r.get("min-rtt", avg_str)).replace("ms", "").strip()), 2),
                        "jitter": 0,
                        "packet_loss": round(float(str(r.get("packet-loss", "0")).replace("%", "").strip()), 1),
                    }
                except (ValueError, TypeError):
                    pass
            # Cek status — jika "timeout" maka loss
            status = str(r.get("status", "")).lower()
            if status == "" or "timeout" not in status:
                if not rtts:  # tidak ada time tapi status OK
                    received += 1

        if not rtts:
            loss = round((1 - received / count) * 100, 1) if count > 0 else 100
            return {"avg_rtt": 0, "max_rtt": 0, "min_rtt": 0, "jitter": 0, "packet_loss": loss}

        avg_rtt = round(sum(rtts) / len(rtts), 2)
        max_rtt = round(max(rtts), 2)
        min_rtt = round(min(rtts), 2)
        jitter = round(max_rtt - min_rtt, 2)
        loss = round((1 - len(rtts) / count) * 100, 1)

        return {
            "avg_rtt": avg_rtt,
            "max_rtt": max_rtt,
            "min_rtt": min_rtt,
            "jitter": jitter,
            "packet_loss": loss,
        }

    except Exception as e:
        logger.warning(f"Ping error to {gateway}: {e}")
        return {"avg_rtt": 0, "max_rtt": 0, "min_rtt": 0, "jitter": 0, "packet_loss": 100}


async def _poll_all_devices():
    """Poll latency dari semua device yang terdaftar."""
    db = get_db()
    devices = await db.devices.find(
        {"is_disabled": {"$ne": True}},
        {"_id": 0, "id": 1, "name": 1, "ip_address": 1, "api_username": 1,
         "api_password": 1, "api_mode": 1, "use_https": 1, "api_port": 1,
         "api_ssl": 1, "api_plaintext_login": 1}
    ).to_list(50)

    now_iso = datetime.now(timezone.utc).isoformat()

    for dev in devices:
        device_id = dev.get("id", "")
        device_name = dev.get("name", "Unknown")
        if not device_id:
            continue

        try:
            mt = get_api_client(dev)
        except Exception as e:
            logger.debug(f"Cannot create API client for {device_name}: {e}")
            continue

        # Tentukan gateway — coba baca dari DB dulu, fallback ke default
        gateways = list(DEFAULT_GATEWAYS)
        try:
            dev_settings = await db.system_settings.find_one({"_id": f"latency_gw_{device_id}"})
            if dev_settings and dev_settings.get("gateways"):
                gateways = dev_settings["gateways"]
        except Exception:
            pass

        for gw in gateways:
            try:
                result = await _ping_from_router(mt, gw, count=5)

                doc = {
                    "device_id": device_id,
                    "device_name": device_name,
                    "gateway": gw,
                    "avg_rtt": result["avg_rtt"],
                    "max_rtt": result["max_rtt"],
                    "min_rtt": result["min_rtt"],
                    "jitter": result["jitter"],
                    "packet_loss": result["packet_loss"],
                    "timestamp": now_iso,
                }

                await db.latency_metrics.insert_one(doc)

                # Pruning: hapus data lama (simpan ~24 jam per device per gateway)
                count = await db.latency_metrics.count_documents(
                    {"device_id": device_id, "gateway": gw}
                )
                if count > MAX_HISTORY:
                    oldest = await db.latency_metrics.find(
                        {"device_id": device_id, "gateway": gw},
                        {"_id": 1}
                    ).sort("timestamp", 1).limit(count - MAX_HISTORY).to_list(count - MAX_HISTORY)
                    if oldest:
                        ids = [d["_id"] for d in oldest]
                        await db.latency_metrics.delete_many({"_id": {"$in": ids}})

                # Alert jika latency tinggi atau loss tinggi
                if result["avg_rtt"] > 80 or result["packet_loss"] > 5:
                    logger.warning(
                        f"[LATENCY] {device_name} → {gw}: "
                        f"avg={result['avg_rtt']}ms loss={result['packet_loss']}% (CRITICAL)"
                    )
                elif result["avg_rtt"] > 30 or result["packet_loss"] > 1:
                    logger.info(
                        f"[LATENCY] {device_name} → {gw}: "
                        f"avg={result['avg_rtt']}ms loss={result['packet_loss']}% (warning)"
                    )

            except Exception as e:
                logger.debug(f"Latency poll error {device_name} → {gw}: {e}")

        # Jeda kecil antar device agar tidak membanjiri jaringan
        await asyncio.sleep(1)


async def latency_monitor_loop():
    """Background loop untuk latency monitoring."""
    logger.info("Latency Monitor service started.")
    await asyncio.sleep(10)  # Delay startup

    while True:
        try:
            await _poll_all_devices()
        except Exception as e:
            logger.error(f"Latency monitor error: {e}")

        await asyncio.sleep(POLL_INTERVAL)
