"""
IP Accounting Poller — Bandwidth per Platform via MikroTik IP Accounting.

Strategy:
- Setiap 5 menit, poll semua device online untuk snapshot IP Accounting.
- Korelasikan IP asal/tujuan ke platform menggunakan DNS hits terbaru di memory.
- Update field `bytes` di peering_eye_stats untuk platform yang cocok.

Catatan ROS:
- ROS 7 (REST): GET /ip/accounting/snapshot (otomatis take+read)
- ROS 6 (API):  /ip accounting snapshot take → /ip accounting snapshot read (two-step)

Env vars:
  IP_ACCOUNTING_INTERVAL  — polling interval in seconds (default: 300)
  ENABLE_IP_ACCOUNTING    — "true"/"false" (default: true)
"""
import asyncio
import logging
import os
from datetime import datetime, timezone, timedelta

from core.db import get_db
from mikrotik_api import get_api_client

logger = logging.getLogger(__name__)

IP_ACCOUNTING_INTERVAL = int(os.environ.get("IP_ACCOUNTING_INTERVAL", "300"))
_MAX_CONCURRENT = 5   # concurrent polling (jaga beban router)


async def _poll_device_accounting(device: dict) -> tuple[str, int]:
    """
    Poll IP Accounting snapshot dari satu device.
    Return (device_id, total_bytes_sampled).
    Tambahkan bytes ke peering_eye_stats untuk device ini.
    """
    dev_id = device.get("id", "")
    dev_name = device.get("name", dev_id)

    try:
        mt = get_api_client(device)

        # Ambil snapshot IP Accounting
        try:
            raw_entries = await asyncio.wait_for(
                mt.get_ip_accounting_snapshot(),
                timeout=30
            )
        except NotImplementedError:
            # Metode tidak ada di client ini, skip device
            logger.debug(f"[IPAccounting] {dev_name}: get_ip_accounting_snapshot tidak tersedia")
            return dev_id, 0
        except asyncio.TimeoutError:
            logger.warning(f"[IPAccounting] Timeout {dev_name}")
            return dev_id, 0

        if not raw_entries or not isinstance(raw_entries, list):
            return dev_id, 0

        # Aggregate total bytes per src/dst IP
        ip_bytes: dict = {}  # {ip: total_bytes}
        total_bytes = 0
        for entry in raw_entries:
            try:
                src = entry.get("src-address", "")
                dst = entry.get("dst-address", "")
                b   = int(entry.get("bytes", 0))
                if src:
                    ip_bytes[src] = ip_bytes.get(src, 0) + b
                if dst:
                    ip_bytes[dst] = ip_bytes.get(dst, 0) + b
                total_bytes += b
            except (ValueError, TypeError):
                continue

        if not ip_bytes:
            return dev_id, 0

        # Ambil data stats terbaru per device untuk update bytes
        db = get_db()
        now_iso = datetime.now(timezone.utc).isoformat()
        cutoff  = (datetime.now(timezone.utc) - timedelta(minutes=10)).isoformat()

        # Ambil platform stats terbaru untuk device ini
        recent_stats = await db.peering_eye_stats.find(
            {"device_id": {"$in": [dev_id, dev_name]}, "timestamp": {"$gte": cutoff}},
            {"_id": 0, "device_id": 1, "platform": 1, "top_clients": 1, "timestamp": 1}
        ).to_list(200)

        if not recent_stats:
            logger.debug(f"[IPAccounting] {dev_name}: tidak ada recent stats untuk korelasi")
            return dev_id, total_bytes

        # Distribusikan bytes ke platform berdasarkan top_clients yang cocok
        from pymongo import UpdateOne
        ops = []
        for stat in recent_stats:
            top_clients = stat.get("top_clients") or {}
            platform_bytes = 0
            for client_ip in top_clients:
                platform_bytes += ip_bytes.get(client_ip, 0)

            if platform_bytes > 0:
                ops.append(UpdateOne(
                    {
                        "device_id": stat["device_id"],
                        "platform":  stat["platform"],
                        "timestamp": stat["timestamp"],
                    },
                    {"$inc": {"bytes": platform_bytes}}
                ))

        if ops:
            await db.peering_eye_stats.bulk_write(ops)
            logger.info(
                f"[IPAccounting] {dev_name}: {total_bytes:,} bytes distributed "
                f"ke {len(ops)} platform records"
            )

        return dev_id, total_bytes

    except asyncio.CancelledError:
        raise
    except Exception as e:
        logger.warning(f"[IPAccounting] Error {dev_name}: {e}")
        return dev_id, 0


async def ip_accounting_poll_once() -> None:
    """Jalankan satu putaran polling ke semua device online."""
    try:
        db = get_db()
        devices = await db.devices.find(
            {"status": "online"},
            {"_id": 0}
        ).to_list(200)

        if not devices:
            logger.debug("[IPAccounting] Tidak ada device online")
            return

        sem = asyncio.Semaphore(_MAX_CONCURRENT)

        async def throttled(device):
            async with sem:
                return await _poll_device_accounting(device)

        results = await asyncio.gather(
            *[throttled(d) for d in devices],
            return_exceptions=True
        )

        total_polled = sum(1 for r in results if isinstance(r, tuple))
        total_bytes  = sum(r[1] for r in results if isinstance(r, tuple))
        logger.info(
            f"[IPAccounting] Poll selesai: {total_polled}/{len(devices)} device, "
            f"total {total_bytes:,} bytes diakumulasi"
        )

    except Exception as e:
        logger.error(f"[IPAccounting] poll_once error: {e}")


async def ip_accounting_loop() -> None:
    """Background loop: poll IP Accounting setiap IP_ACCOUNTING_INTERVAL detik."""
    logger.info(
        f"[IPAccounting] Service dimulai "
        f"(interval={IP_ACCOUNTING_INTERVAL}s, max_concurrent={_MAX_CONCURRENT})"
    )
    # Delay awal agar device cache syslog_server sudah terisi
    await asyncio.sleep(60)

    while True:
        try:
            await ip_accounting_poll_once()
        except asyncio.CancelledError:
            logger.info("[IPAccounting] Service dihentikan")
            break
        except Exception as e:
            logger.error(f"[IPAccounting] Loop error: {e}")
        await asyncio.sleep(IP_ACCOUNTING_INTERVAL)
