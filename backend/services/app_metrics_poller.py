"""
app_metrics_poller.py
─────────────────────────────────────────────────────────────────────────────
Global ISP Application Traffic Counter

Cara Kerja:
  1. Membaca semua BGP Steering Policy yang aktif dari MongoDB.
     Setiap policy merepresentasikan sebuah platform (misal: YouTube, Facebook).

  2. Menarik statistik Simple Queue bernama "GLOBAL_APP_<PlatformName>"
     dari semua device yang terdaftar di DB (yang bisa diakses lewat REST API).
     Queue tersebut dibuat sekali via script setup MikroTik (.rsc).

  3. Menyimpan delta bytes (trafik berjalan) setiap 5 menit ke MongoDB
     di collection `global_app_metrics` untuk dibuatkan Grafik/Chart.

  4. Tidak ada modifikasi pada polling/service yang sudah ada — hanya tambah
     background task baru yang sepenuhnya terisolasi.
─────────────────────────────────────────────────────────────────────────────
"""
import asyncio
import logging
from datetime import datetime, timezone, date, timedelta

logger = logging.getLogger(__name__)

# Prefix nama Queue/Mangle di MikroTik yang akan dipantau
QUEUE_PREFIX = "GLOBAL_APP_"

# Interval polling (setiap 5 menit)
POLL_INTERVAL_SECONDS = 300


def _db():
    from core.db import get_db
    return get_db()


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _parse_bytes(val) -> int:
    """Parse string bytes dari MikroTik (contoh: '1234567') ke int."""
    try:
        return int(str(val).replace(",", "").strip())
    except (ValueError, TypeError):
        return 0


async def _get_active_platform_names() -> list[str]:
    """
    Ambil daftar nama platform dari BGP Steering Policies yang aktif.
    Ini menjadi acuan nama Queue yang akan dicari di MikroTik.
    """
    try:
        db = _db()
        policies = await db.bgp_steering_policies.find(
            {"enabled": True}, {"platform_name": 1}
        ).to_list(100)
        return list({p.get("platform_name", "") for p in policies if p.get("platform_name")})
    except Exception as e:
        logger.warning(f"[AppMetrics] Gagal ambil platform names: {e}")
        return []


async def _list_simple_queues_rest(device: dict) -> list[dict]:
    """
    Tarik daftar Simple Queue dari MikroTik via REST API.
    Return list of dicts (sesuai format RouterOS REST).
    """
    try:
        from mikrotik_api import get_api_client
        mt = get_api_client(device)
        # REST API endpoint: /queue/simple
        result = await mt._async_req("GET", "queue/simple")
        return result if isinstance(result, list) else []
    except Exception as e:
        host = device.get("ip_address", "?")
        logger.debug(f"[AppMetrics] Gagal ambil queue dari {host}: {e}")
        return []


async def poll_device_app_traffic(device: dict, platform_names: list[str]) -> dict:
    """
    Poll traffic stats untuk device tertentu.
    Return: {platform_name: {"bytes_rx": int, "bytes_tx": int}}
    """
    queues = await _list_simple_queues_rest(device)
    if not queues:
        return {}

    # Buat index: queue_name -> queue_data
    queue_map = {}
    for q in queues:
        name = q.get("name", "")
        if name.startswith(QUEUE_PREFIX):
            app_name = name[len(QUEUE_PREFIX):]  # strip prefix
            queue_map[app_name] = q

    results = {}
    for platform in platform_names:
        q = queue_map.get(platform)
        if not q:
            continue
        # RouterOS REST: "bytes" field = "rx-byte/tx-byte"
        # Format dari ROS REST API: "bytes" = "1234/5678" (rx/tx) ATAU field terpisah
        bytes_str = q.get("bytes", "0/0")
        if "/" in str(bytes_str):
            parts = str(bytes_str).split("/")
            rx = _parse_bytes(parts[0]) if len(parts) > 0 else 0
            tx = _parse_bytes(parts[1]) if len(parts) > 1 else 0
        else:
            # Coba field terpisah
            rx = _parse_bytes(q.get("rx-byte", q.get("bytes-rx", 0)))
            tx = _parse_bytes(q.get("tx-byte", q.get("bytes-tx", 0)))

        results[platform] = {"bytes_rx": rx, "bytes_tx": tx}

    return results


async def run_poll_cycle():
    """
    Satu siklus polling: query semua device aktif, hitung delta bytes,
    simpan ke global_app_metrics.
    """
    db = _db()
    platform_names = await _get_active_platform_names()
    if not platform_names:
        logger.debug("[AppMetrics] Tidak ada BGP Steering Policy aktif, lewati polling.")
        return

    # Ambil semua device yang aktif (tidak offline, pakai REST API)
    devices = await db.devices.find(
        {"status": {"$ne": "offline"}, "api_mode": {"$in": ["rest", "rest_http"]}},
        {"id": 1, "ip_address": 1, "username": 1, "password": 1, "api_mode": 1, "name": 1}
    ).to_list(200)

    if not devices:
        logger.debug("[AppMetrics] Tidak ada device REST API online.")
        return

    now_iso = _now_iso()
    today_str = date.today().isoformat()
    hour_str = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:00:00+00:00")

    # Agregasi global (gabungan semua device)
    global_totals: dict[str, dict] = {}

    for device in devices:
        try:
            device_stats = await poll_device_app_traffic(device, platform_names)
            for platform, stats in device_stats.items():
                if platform not in global_totals:
                    global_totals[platform] = {"bytes_rx": 0, "bytes_tx": 0}
                global_totals[platform]["bytes_rx"] += stats["bytes_rx"]
                global_totals[platform]["bytes_tx"] += stats["bytes_tx"]
        except Exception as e:
            logger.warning(f"[AppMetrics] Error poll device {device.get('name', '?')}: {e}")

    if not global_totals:
        return

    # ── Simpan snapshot per jam ke MongoDB ─────────────────────────────────
    for platform, stats in global_totals.items():
        total_bytes = stats["bytes_rx"] + stats["bytes_tx"]
        if total_bytes == 0:
            continue

        # Upsert snapshot per jam (replace agar tidak duplikat)
        await db.global_app_metrics.update_one(
            {
                "platform": platform,
                "period_hour": hour_str,
                "date": today_str,
            },
            {
                "$set": {
                    "platform": platform,
                    "period_hour": hour_str,
                    "date": today_str,
                    "bytes_rx": stats["bytes_rx"],
                    "bytes_tx": stats["bytes_tx"],
                    "total_bytes": total_bytes,
                    "updated_at": now_iso,
                }
            },
            upsert=True
        )

    logger.info(
        f"[AppMetrics] Snapshot disimpan: {len(global_totals)} platform | "
        f"Top: {sorted(global_totals.items(), key=lambda x: x[1]['bytes_rx']+x[1]['bytes_tx'], reverse=True)[0][0] if global_totals else '-'}"
    )

    # ── Auto-cleanup data lebih dari 30 hari ──────────────────────────────
    cutoff = (date.today() - timedelta(days=30)).isoformat()
    await db.global_app_metrics.delete_many({"date": {"$lt": cutoff}})


async def app_metrics_loop():
    """
    Main loop: poll setiap POLL_INTERVAL_SECONDS (5 menit).
    """
    logger.info("[AppMetrics] Application Traffic Poller dimulai (interval: 5 menit).")

    # Tunggu sebentar agar service lain (BGP Steering, etc.) siap lebih dulu
    await asyncio.sleep(30)

    while True:
        try:
            await run_poll_cycle()
        except Exception as e:
            logger.error(f"[AppMetrics] Loop error: {e}")

        await asyncio.sleep(POLL_INTERVAL_SECONDS)


# ── Helper untuk dipakai oleh API endpoint ────────────────────────────────

async def get_app_traffic_summary(days: int = 1) -> list[dict]:
    """
    Ambil rekapan traffic per platform untuk N hari terakhir.
    Return: sorted list [{platform, total_bytes, bytes_rx, bytes_tx, percent}]
    """
    db = _db()
    cutoff = (date.today() - timedelta(days=days)).isoformat()

    pipeline = [
        {"$match": {"date": {"$gte": cutoff}}},
        {
            "$group": {
                "_id": "$platform",
                "total_bytes": {"$sum": "$total_bytes"},
                "bytes_rx":    {"$sum": "$bytes_rx"},
                "bytes_tx":    {"$sum": "$bytes_tx"},
            }
        },
        {"$sort": {"total_bytes": -1}},
    ]

    docs = await db.global_app_metrics.aggregate(pipeline).to_list(50)

    grand_total = sum(d["total_bytes"] for d in docs) or 1
    results = []
    for d in docs:
        results.append({
            "platform":    d["_id"],
            "total_bytes": d["total_bytes"],
            "bytes_rx":    d["bytes_rx"],
            "bytes_tx":    d["bytes_tx"],
            "percent":     round(d["total_bytes"] / grand_total * 100, 2),
        })
    return results


async def get_app_traffic_history(platform: str, days: int = 7) -> list[dict]:
    """
    Ambil data historis per jam untuk satu platform (untuk line chart).
    Return: [{period_hour, total_bytes}]
    """
    db = _db()
    cutoff = (date.today() - timedelta(days=days)).isoformat()

    docs = await db.global_app_metrics.find(
        {"platform": platform, "date": {"$gte": cutoff}},
        {"period_hour": 1, "total_bytes": 1, "_id": 0}
    ).sort("period_hour", 1).to_list(1000)

    return [{"period_hour": d["period_hour"], "total_bytes": d["total_bytes"]} for d in docs]
