"""
Metrics router: query time-series data from InfluxDB.
Falls back to MongoDB traffic_history if InfluxDB is not configured.
"""
import logging
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from typing import Optional
from core.auth import get_current_user, require_admin
from core.db import get_db
from datetime import datetime, timezone, timedelta

router = APIRouter(prefix="/metrics", tags=["metrics"])
logger = logging.getLogger(__name__)


@router.get("/history")
async def get_metrics_history(
    device_id: str,
    hours: int = 6,
    interface: str = "all",
    user=Depends(get_current_user)
):
    """
    Get historical bandwidth + system metrics.
    Uses InfluxDB if configured, falls back to MongoDB.
    """
    from services.metrics_service import is_enabled, query_bandwidth_history, query_device_metrics

    if is_enabled():
        # ── InfluxDB path ──
        try:
            bw_data = query_bandwidth_history(device_id, hours, interface)
            sys_data = query_device_metrics(device_id, hours)

            # Merge by timestamp (approx match by rounding to minute)
            sys_by_time = {}
            for s in sys_data:
                try:
                    t = datetime.fromisoformat(s["time"].replace("Z", "+00:00"))
                    key = t.strftime("%Y-%m-%dT%H:%M")
                    sys_by_time[key] = s
                except Exception:
                    pass

            result = []
            seen_times = set()
            for bw in bw_data:
                try:
                    t = datetime.fromisoformat(bw["time"].replace("Z", "+00:00"))
                    # Convert to WIB (+7)
                    local = t + timedelta(hours=7)
                    label = local.strftime("%H:%M")
                    key = t.strftime("%Y-%m-%dT%H:%M")
                except Exception:
                    label = bw["time"][:16]
                    key = label

                if key in seen_times:
                    continue
                seen_times.add(key)

                sys = sys_by_time.get(key, {})
                result.append({
                    "time": label,
                    "download": bw.get("download_mbps", 0),
                    "upload": bw.get("upload_mbps", 0),
                    "ping": sys.get("ping_ms", 0),
                    "jitter": sys.get("jitter_ms", 0),
                    "cpu": sys.get("cpu_percent", 0),
                    "memory": sys.get("memory_percent", 0),
                    "source": "influxdb",
                })
            return result

        except Exception as e:
            logger.error(f"InfluxDB query failed, falling back to MongoDB: {e}")

    # ── MongoDB fallback ──
    db = get_db()
    cutoff = (datetime.now(timezone.utc) - timedelta(hours=hours)).isoformat()
    query = {"device_id": device_id, "timestamp": {"$gte": cutoff}}
    history = await db.traffic_history.find(query, {"_id": 0}).sort("timestamp", 1).to_list(1000)

    result = []
    for h in history:
        try:
            t = datetime.fromisoformat(h["timestamp"].replace("Z", "+00:00"))
            local = t + timedelta(hours=7)
            label = local.strftime("%H:%M")
        except Exception:
            label = ""

        bw = h.get("bandwidth", {})
        if interface and interface != "all":
            ib = bw.get(interface, {})
            dl = ib.get("download_bps", 0)
            ul = ib.get("upload_bps", 0)
        else:
            dl = sum(v.get("download_bps", 0) for v in bw.values())
            ul = sum(v.get("upload_bps", 0) for v in bw.values())

        result.append({
            "time": label,
            "download": round(dl / 1e6, 3),
            "upload": round(ul / 1e6, 3),
            "ping": h.get("ping_ms", 0),
            "jitter": h.get("jitter_ms", 0),
            "cpu": h.get("cpu", 0),
            "memory": h.get("memory_percent", 0),
            "source": "mongodb",
        })
    return result


@router.get("/status")
async def influx_status(user=Depends(require_admin)):
    """Check InfluxDB connection status."""
    from services.metrics_service import is_enabled, test_connection
    if not is_enabled():
        return {
            "enabled": False,
            "connected": False,
            "message": "InfluxDB belum dikonfigurasi. Isi URL, Token, Org di Pengaturan."
        }
    result = test_connection()
    result["enabled"] = True
    return result


@router.post("/test-connection")
async def test_influx_connection(user=Depends(require_admin)):
    """Test InfluxDB connection with current env vars."""
    from services.metrics_service import test_connection
    result = test_connection()
    if result["connected"]:
        return result
    raise HTTPException(503, result.get("error", "Connection failed"))
