"""
Session Cache Service — PPPoE & Hotspot Active Count Background Fetcher.

Strategi:
- ROS7 (api_mode="rest"): fetch langsung via REST API — non-blocking, cepat
- ROS6 (api_mode="api"): SKIP — data sudah diupdate oleh polling.py setiap 30 detik
  menggunakan routeros_api (synchronous/threading). Session_cache tidak perlu re-fetch
  karena polling sudah menyimpan pppoe_active/hotspot_active ke DB.

Wallboard membaca nilai ini dari DB → tidak ada flicker/hilang-timbul.
Interval default: 300 detik (5 menit). Ubah via env SESSION_CACHE_INTERVAL.

API Cache:
- get_cached_pppoe(device)  → list, cached 30 detik
- get_cached_hotspot(device) → list, cached 30 detik
Tujuan: mencegah router Mikrotik di-query berkali-kali saat banyak user
membuka halaman PPPoE/Hotspot secara bersamaan.
"""
import asyncio
import logging
import os
import time
from datetime import datetime, timezone, timedelta

from core.db import get_db
from mikrotik_api import get_api_client

logger = logging.getLogger(__name__)

SESSION_CACHE_INTERVAL  = int(os.environ.get("SESSION_CACHE_INTERVAL", "90"))
SESSION_FETCH_TIMEOUT   = 20   # detik — untuk REST API ROS7
SESSION_MAX_CONCURRENT  = 15   # concurrent untuk ROS7 (REST - lebih ringan)
SESSION_IP_SYNC_INTERVAL = int(os.environ.get("SESSION_IP_SYNC_INTERVAL", "30"))  # detik

# ── In-Memory API Cache (per-device, TTL 30 detik) ───────────────────────────
# Format: { device_id: {"pppoe": [...], "hotspot": [...], "ts": float} }
_API_CACHE: dict = {}
_API_CACHE_TTL = 30  # detik


def _cache_get(device_id: str, key: str):
    """Ambil data dari cache jika belum expired. Return None jika tidak ada/expired."""
    entry = _API_CACHE.get(device_id)
    if entry and (time.time() - entry.get("ts", 0)) < _API_CACHE_TTL:
        return entry.get(key)
    return None


def _cache_set(device_id: str, key: str, data):
    """Simpan data ke cache untuk device_id tertentu."""
    if device_id not in _API_CACHE:
        _API_CACHE[device_id] = {"ts": time.time()}
    _API_CACHE[device_id][key] = data
    _API_CACHE[device_id]["ts"] = time.time()


async def get_cached_pppoe(device: dict) -> list:
    """
    Ambil daftar sesi PPPoE aktif — dari cache jika tersedia (TTL 30 detik).
    Jika cache kosong/expired, query langsung ke MikroTik dan update cache.
    Gunakan fungsi ini di endpoint API agar router tidak di-query tiap request.
    """
    dev_id = device.get("id", "")
    cached = _cache_get(dev_id, "pppoe")
    if cached is not None:
        return cached
    try:
        mt = get_api_client(device)
        result = await asyncio.wait_for(mt.list_pppoe_active(), timeout=SESSION_FETCH_TIMEOUT)
        data = result if isinstance(result, list) else []
        _cache_set(dev_id, "pppoe", data)
        return data
    except Exception as e:
        logger.debug(f"[session_cache] get_cached_pppoe gagal {dev_id}: {e}")
        return []


async def get_cached_hotspot(device: dict) -> list:
    """
    Ambil daftar sesi Hotspot aktif — dari cache jika tersedia (TTL 30 detik).
    Jika cache kosong/expired, query langsung ke MikroTik dan update cache.
    Gunakan fungsi ini di endpoint API agar router tidak di-query tiap request.
    """
    dev_id = device.get("id", "")
    cached = _cache_get(dev_id, "hotspot")
    if cached is not None:
        return cached
    try:
        mt = get_api_client(device)
        result = await asyncio.wait_for(mt.list_hotspot_active(), timeout=SESSION_FETCH_TIMEOUT)
        data = result if isinstance(result, list) else []
        _cache_set(dev_id, "hotspot", data)
        return data
    except Exception as e:
        logger.debug(f"[session_cache] get_cached_hotspot gagal {dev_id}: {e}")
        return []




async def _sync_sessions_to_db(device: dict, pppoe_list: list, hotspot_list: list) -> None:
    """
    Simpan mapping IP → nama user ke MongoDB (pppoe_sessions, hotspot_sessions).
    Ini yang dibaca oleh peering_eye.get_active_ip_mapping() untuk resolusi IP client.
    Data di-upsert berdasarkan (device_id, ip) agar selalu fresh.
    """
    try:
        db      = get_db()
        dev_id  = device.get("id", "")
        dev_name = device.get("name", dev_id)
        now_iso = datetime.now(timezone.utc).isoformat()

        from pymongo import UpdateOne

        # ── PPPoE Sessions ────────────────────────────────────────────────────
        pppoe_ops = []
        for s in pppoe_list:
            ip = s.get("address") or s.get("ip-address") or ""
            name = s.get("name") or s.get("caller-id") or ""
            mac  = s.get("caller-id", "") if not s.get("address") else s.get("mac", "")
            if not ip or not name:
                continue
            pppoe_ops.append(UpdateOne(
                {"device_id": dev_id, "ip": ip},
                {"$set": {
                    "device_id":   dev_id,
                    "device_name": dev_name,
                    "ip":          ip,
                    "name":        name,
                    "mac":         mac,
                    "type":        "pppoe",
                    "updated_at":  now_iso,
                }},
                upsert=True,
            ))
        if pppoe_ops:
            await db.pppoe_sessions.bulk_write(pppoe_ops)

        # ── Hotspot Sessions ──────────────────────────────────────────────────
        hotspot_ops = []
        for s in hotspot_list:
            ip   = s.get("address") or s.get("ip-address") or ""
            name = s.get("user") or s.get("name") or ""
            mac  = s.get("mac-address") or s.get("mac", "")
            if not ip or not name:
                continue
            hotspot_ops.append(UpdateOne(
                {"device_id": dev_id, "ip": ip},
                {"$set": {
                    "device_id":   dev_id,
                    "device_name": dev_name,
                    "ip":          ip,
                    "name":        name,
                    "mac":         mac,
                    "type":        "hotspot",
                    "updated_at":  now_iso,
                }},
                upsert=True,
            ))
        if hotspot_ops:
            await db.hotspot_sessions.bulk_write(hotspot_ops)

        # Hapus sesi lama (lebih dari 15 menit tidak diupdate = sudah disconnect)
        # 15 menit = buffer yang aman untuk SESSION_CACHE_INTERVAL=90s & IP_SYNC=30s
        cutoff = (datetime.now(timezone.utc) - timedelta(minutes=15)).isoformat()
        r_pppoe = await db.pppoe_sessions.delete_many({"device_id": dev_id, "updated_at": {"$lt": cutoff}})
        r_hs    = await db.hotspot_sessions.delete_many({"device_id": dev_id, "updated_at": {"$lt": cutoff}})

        deleted = r_pppoe.deleted_count + r_hs.deleted_count
        logger.debug(
            f"[session_cache] {dev_name}: sync {len(pppoe_ops)} pppoe + {len(hotspot_ops)} hotspot"
            + (f" | cleaned {deleted} stale sessions" if deleted > 0 else "")
        )
    except Exception as e:
        logger.debug(f"[session_cache] _sync_sessions_to_db error: {e}")



async def _fetch_rest_device(device: dict) -> tuple[str, int, int]:
    """
    Fetch PPPoE + Hotspot count via REST API untuk device ROS7.
    Returns (device_id, pppoe_count, hotspot_count).
    -1 = gagal → pertahankan nilai DB lama.
    """
    dev_id   = device.get("id", "")
    dev_name = device.get("name", dev_id)

    try:
        mt = get_api_client(device)

        pppoe_count   = 0
        hotspot_count = 0
        pppoe_data    = []
        hotspot_data  = []

        try:
            pppoe_list = await asyncio.wait_for(
                mt.list_pppoe_active(), timeout=SESSION_FETCH_TIMEOUT
            )
            pppoe_data  = pppoe_list if isinstance(pppoe_list, list) else []
            pppoe_count = len(pppoe_data)
        except asyncio.TimeoutError:
            logger.warning(f"[session_cache] Timeout PPPoE {dev_name}")
            pppoe_count = -1
        except NotImplementedError:
            pass
        except Exception as e:
            logger.debug(f"[session_cache] PPPoE gagal {dev_name}: {e}")

        try:
            hs_list = await asyncio.wait_for(
                mt.list_hotspot_active(), timeout=SESSION_FETCH_TIMEOUT
            )
            hotspot_data  = hs_list if isinstance(hs_list, list) else []
            hotspot_count = len(hotspot_data)
        except asyncio.TimeoutError:
            logger.warning(f"[session_cache] Timeout Hotspot {dev_name}")
            hotspot_count = -1
        except NotImplementedError:
            pass
        except Exception as e:
            logger.debug(f"[session_cache] Hotspot gagal {dev_name}: {e}")

        logger.info(f"[session_cache] {dev_name}: pppoe={pppoe_count} hs={hotspot_count}")

        # Sync IP → nama ke MongoDB (non-blocking)
        if pppoe_data or hotspot_data:
            asyncio.create_task(_sync_sessions_to_db(device, pppoe_data, hotspot_data))

        return dev_id, pppoe_count, hotspot_count

    except Exception as e:
        logger.warning(f"[session_cache] Error {dev_name}: {e}")
        return dev_id, -1, -1


async def refresh_session_cache():
    """
    Fetch session counts dari device ROS7 (REST API) online secara paralel.
    ROS6 device di-skip — polling.py sudah handle mereka setiap 30 detik.
    """
    db = get_db()
    # Hanya ambil device online dengan api_mode REST (ROS7)
    # ROS6 (api_mode="api") tidak di-fetch — sudah dihandle polling.py
    all_online = await db.devices.find(
        {"status": "online"},
        {"_id": 0}
    ).to_list(500)

    # Filter: hanya REST API devices
    rest_devices = [d for d in all_online if d.get("api_mode", "rest") != "api"]
    ros6_devices = [d for d in all_online if d.get("api_mode", "rest") == "api"]

    if not all_online:
        logger.info("[session_cache] Tidak ada device online.")
        return

    logger.info(
        f"[session_cache] Refresh: {len(rest_devices)} REST (akan di-fetch), "
        f"{len(ros6_devices)} ROS6 (skip - dihandle polling.py)"
    )

    if not rest_devices:
        return

    sem = asyncio.Semaphore(SESSION_MAX_CONCURRENT)

    async def throttled(idx, device):
        await asyncio.sleep(idx * 0.5)
        async with sem:
            return await _fetch_rest_device(device)

    results = await asyncio.gather(
        *[throttled(i, d) for i, d in enumerate(rest_devices)],
        return_exceptions=True,
    )

    updated = 0
    skipped = 0
    now = datetime.now(timezone.utc).isoformat()

    for result in results:
        if not isinstance(result, tuple) or len(result) != 3:
            skipped += 1
            continue

        dev_id, pppoe, hotspot = result
        if not dev_id:
            skipped += 1
            continue

        set_fields: dict = {"session_cache_at": now}
        if pppoe >= 0:
            set_fields["pppoe_active"] = pppoe
        if hotspot >= 0:
            set_fields["hotspot_active"] = hotspot

        if len(set_fields) <= 1:
            skipped += 1
            continue

        await db.devices.update_one({"id": dev_id}, {"$set": set_fields})
        updated += 1

    logger.info(
        f"[session_cache] Selesai: {updated} REST diupdate, {skipped} skip. "
        f"Interval berikutnya {SESSION_CACHE_INTERVAL}s."
    )


async def session_cache_loop():
    """Background loop: refresh setiap SESSION_CACHE_INTERVAL detik."""
    logger.info(
        f"[session_cache] Service dimulai (REST-only). "
        f"Interval: {SESSION_CACHE_INTERVAL}s. ROS6 dihandle polling.py."
    )
    while True:
        try:
            await refresh_session_cache()
        except Exception as e:
            logger.error(f"[session_cache] Error: {e}")
        await asyncio.sleep(SESSION_CACHE_INTERVAL)


async def session_ip_mapping_loop():
    """
    Background loop yang lebih cepat (30 detik) khusus untuk sync
    PPPoE + Hotspot IP → nama ke MongoDB (untuk top-clients Peering Eye).
    Ini terpisah dari session_cache_loop yang lebih lambat (90 detik).
    """
    logger.info(
        f"[session_cache] IP mapping sync dimulai "
        f"(interval={SESSION_IP_SYNC_INTERVAL}s)"
    )
    await asyncio.sleep(15)  # Delay awal
    while True:
        try:
            db = get_db()
            devices = await db.devices.find(
                {"status": "online"},
                {"_id": 0}
            ).to_list(200)

            sem = asyncio.Semaphore(SESSION_MAX_CONCURRENT)

            async def _sync_one(device):
                dev_id = device.get("id", "")
                try:
                    mt = get_api_client(device)
                    pppoe_data   = []
                    hotspot_data = []
                    try:
                        pppoe_list = await asyncio.wait_for(
                            mt.list_pppoe_active(), timeout=SESSION_FETCH_TIMEOUT
                        )
                        pppoe_data = pppoe_list if isinstance(pppoe_list, list) else []
                    except Exception:
                        pass
                    try:
                        hs_list = await asyncio.wait_for(
                            mt.list_hotspot_active(), timeout=SESSION_FETCH_TIMEOUT
                        )
                        hotspot_data = hs_list if isinstance(hs_list, list) else []
                    except Exception:
                        pass
                    if pppoe_data or hotspot_data:
                        await _sync_sessions_to_db(device, pppoe_data, hotspot_data)
                except Exception as e:
                    logger.debug(f"[session_cache] _sync_one {dev_id}: {e}")

            async def throttled(device):
                async with sem:
                    return await _sync_one(device)

            await asyncio.gather(
                *[throttled(d) for d in devices],
                return_exceptions=True,
            )

        except asyncio.CancelledError:
            logger.info("[session_cache] IP mapping sync dihentikan")
            break
        except Exception as e:
            logger.error(f"[session_cache] IP mapping sync error: {e}")
        await asyncio.sleep(SESSION_IP_SYNC_INTERVAL)
