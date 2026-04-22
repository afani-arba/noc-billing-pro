"""
DNS Feed Broadcaster — Real-time WebSocket Event Distribution

Menyediakan asyncio.Queue global untuk mendistribusikan event DNS real-time
ke semua klien WebSocket yang aktif.

Arsitektur:
  - syslog_server._dns_processor → push ke _broadcaster_queue
  - WebSocket endpoint /ws/dns-feed → subscribe ke queue per-connection
  - Throttle: max 20 event/detik per koneksi (drop jika overflow)

Cara pakai:
  from services.dns_feed_broadcaster import push_dns_event, subscribe, unsubscribe
"""
import asyncio
import logging
import time
from collections import deque
from typing import Set, Optional

logger = logging.getLogger(__name__)

# ── Global broadcaster state ──────────────────────────────────────────────────
# Set of per-connection asyncio.Queue objects
_subscribers: Set[asyncio.Queue] = set()
# Lazy-initialize lock saat pertama kali dibutuhkan di dalam async context
# Menghindari RuntimeError: no current event loop saat import di luar event loop
_subscriber_lock: Optional[asyncio.Lock] = None

# Throttle: max events per connection per second
_WS_MAX_EVENTS_PER_SEC = 20
# Max queue size per connection
_WS_QUEUE_SIZE = 500


def _get_lock() -> asyncio.Lock:
    """Lazy-initialize asyncio.Lock di dalam event loop yang sedang berjalan."""
    global _subscriber_lock
    if _subscriber_lock is None:
        _subscriber_lock = asyncio.Lock()
    return _subscriber_lock


async def push_dns_event(event: dict) -> None:
    """
    Push a DNS event to all active WebSocket subscribers.
    Non-blocking: jika subscriber queue penuh, event di-drop untuk subscriber itu.
    """
    if not _subscribers:
        return
    async with _get_lock():
        subs = set(_subscribers)  # copy agar tidak berubah saat iterasi

    for q in subs:
        try:
            q.put_nowait(event)
        except asyncio.QueueFull:
            pass  # Drop untuk subscriber yang lambat


async def subscribe() -> asyncio.Queue:
    """Buat subscription baru dan return queue-nya."""
    q: asyncio.Queue = asyncio.Queue(maxsize=_WS_QUEUE_SIZE)
    async with _get_lock():
        _subscribers.add(q)
    logger.debug(f"[DNSFeed] New subscriber. Total: {len(_subscribers)}")
    return q


async def unsubscribe(q: asyncio.Queue) -> None:
    """Hapus subscription."""
    async with _get_lock():
        _subscribers.discard(q)
    logger.debug(f"[DNSFeed] Subscriber removed. Total: {len(_subscribers)}")


def get_subscriber_count() -> int:
    """Return jumlah subscriber aktif (non-async helper)."""
    return len(_subscribers)
