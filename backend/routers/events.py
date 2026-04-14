"""
SSE (Server-Sent Events) router — real-time push ke frontend.
Endpoint: GET /events/devices
Mengirim status semua device setiap 5 detik tanpa perlu refresh manual.
"""
import asyncio
import json
import logging
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, Request, Query, HTTPException
from sse_starlette.sse import EventSourceResponse
from core.auth import get_current_user, decode_token
from core.db import get_db

router = APIRouter(prefix="/events", tags=["events"])
logger = logging.getLogger(__name__)

# ── Broadcast manager ─────────────────────────────────────────────────────────

class DeviceEventManager:
    """
    Singleton manager yang menyimpan semua active SSE connections.
    Setiap client mendapat asyncio.Queue sendiri agar independent.
    """
    def __init__(self):
        self._queues: set[asyncio.Queue] = set()

    def add_client(self) -> asyncio.Queue:
        q: asyncio.Queue = asyncio.Queue(maxsize=10)
        self._queues.add(q)
        logger.info(f"SSE client connected. Total: {len(self._queues)}")
        return q

    def remove_client(self, q: asyncio.Queue):
        self._queues.discard(q)
        logger.info(f"SSE client disconnected. Total: {len(self._queues)}")

    async def broadcast(self, data: dict):
        """Push data ke semua connected clients."""
        dead = set()
        for q in self._queues:
            try:
                # non-blocking put: jika queue penuh, skip (client lambat)
                q.put_nowait(data)
            except asyncio.QueueFull:
                pass
            except Exception:
                dead.add(q)
        for q in dead:
            self._queues.discard(q)

    @property
    def client_count(self) -> int:
        return len(self._queues)


# Global singleton
_manager = DeviceEventManager()


async def _device_poller():
    """
    Background task yang polling DB setiap 5 detik dan broadcast ke semua SSE clients.
    Dipanggil sekali saat startup (dari server.py).
    """
    logger.info("SSE device poller started")
    while True:
        try:
            if _manager.client_count > 0:
                db = get_db()
                devices = await db.devices.find(
                    {},
                    {"_id": 0, "id": 1, "name": 1, "ip_address": 1, "status": 1,
                     "cpu_load": 1, "memory_usage": 1, "last_poll": 1,
                     "model": 1, "uptime": 1, "rx_power": 1}
                ).to_list(200)

                payload = {
                    "type": "device_status",
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "devices": [
                        {
                            "id": d.get("id", ""),
                            "name": d.get("name", ""),
                            "ip_address": d.get("ip_address", ""),
                            "status": d.get("status", "unknown"),
                            "cpu_load": d.get("cpu_load", 0),
                            "memory_usage": d.get("memory_usage", 0),
                            "last_poll": d.get("last_poll", ""),
                            "model": d.get("model", ""),
                            "uptime": d.get("uptime", ""),
                        }
                        for d in devices
                    ],
                    "summary": {
                        "total": len(devices),
                        "online": sum(1 for d in devices if d.get("status") == "online"),
                        "offline": sum(1 for d in devices if d.get("status") == "offline"),
                    }
                }
                await _manager.broadcast(payload)
        except Exception as e:
            logger.warning(f"SSE poller error: {e}")

        await asyncio.sleep(5)   # interval 5 detik


def start_poller() -> asyncio.Task:
    """Dipanggil dari server.py startup. Return task reference agar tidak di-GC."""
    # FIX BUG #3: kembalikan task reference sehingga server.py bisa menyimpannya
    task = asyncio.create_task(_device_poller())
    return task


# ── SSE Endpoint ─────────────────────────────────────────────────────────────

@router.get("/devices")
async def stream_device_events(
    request: Request,
    # FIX BUG #16 (CATATAN KEAMANAN): Token JWT di URL yang tersimpan di access log & browser history.
    # Alternatif yang aman: gunakan short-lived one-time ticket yang di-exchange sebelum SSE.
    # Untuk saat ini dipertahankan karena SSE/EventSource tidak mendukung custom headers.
    token: str = Query(..., description="JWT token (karena EventSource tidak bisa kirim header)"),
):
    """
    SSE stream — push device status events setiap 5 detik.
    Client connect dengan EventSource('/api/events/devices?token=...').
    """
    # Validasi token secara manual (tidak bisa pakai Depends karena EventSource = GET)
    try:
        user = decode_token(token)
        if not user:
            raise HTTPException(401, "Invalid token")
    except Exception:
        raise HTTPException(401, "Invalid or expired token")

    q = _manager.add_client()

    async def event_generator():
        # Kirim event awal (current snapshot) segera setelah connect
        try:
            db = get_db()
            devices = await db.devices.find(
                {},
                {"_id": 0, "id": 1, "name": 1, "ip_address": 1, "status": 1,
                 "cpu_load": 1, "memory_usage": 1, "last_poll": 1, "model": 1, "uptime": 1}
            ).to_list(200)

            initial = {
                "type": "device_status",
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "devices": [
                    {
                        "id": d.get("id", ""),
                        "name": d.get("name", ""),
                        "ip_address": d.get("ip_address", ""),
                        "status": d.get("status", "unknown"),
                        "cpu_load": d.get("cpu_load", 0),
                        "memory_usage": d.get("memory_usage", 0),
                        "last_poll": d.get("last_poll", ""),
                        "model": d.get("model", ""),
                        "uptime": d.get("uptime", ""),
                    }
                    for d in devices
                ],
                "summary": {
                    "total": len(devices),
                    "online": sum(1 for d in devices if d.get("status") == "online"),
                    "offline": sum(1 for d in devices if d.get("status") == "offline"),
                }
            }
            yield {"data": json.dumps(initial), "event": "device_status"}
        except Exception as e:
            logger.warning(f"SSE initial snapshot error: {e}")

        # Stream loop
        try:
            while True:
                if await request.is_disconnected():
                    break
                try:
                    data = await asyncio.wait_for(q.get(), timeout=6.0)
                    yield {"data": json.dumps(data), "event": "device_status"}
                except asyncio.TimeoutError:
                    # Kirim heartbeat agar koneksi tidak di-drop oleh proxy/nginx
                    yield {"data": "ping", "event": "heartbeat"}
        except asyncio.CancelledError:
            pass
        finally:
            _manager.remove_client(q)

    return EventSourceResponse(
        event_generator(),
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",   # penting untuk nginx reverse proxy
        }
    )


@router.get("/status")
async def sse_status(user=Depends(get_current_user)):
    """Info jumlah SSE client yang sedang terhubung."""
    return {"active_clients": _manager.client_count}
