"""
InfluxDB Time-Series metrics service for NOC-Sentinel.

Writes device metrics (CPU, memory, ping, bandwidth) to InfluxDB 2.x
for high-resolution historical queries.

Falls back gracefully if InfluxDB is not configured.

Environment variables required:
  INFLUXDB_URL    - e.g. http://localhost:8086
  INFLUXDB_TOKEN  - InfluxDB API token (all-access or write+read)
  INFLUXDB_ORG    - Organization name
  INFLUXDB_BUCKET - Bucket name (e.g. noc-sentinel)
"""
import os
import logging
from datetime import datetime, timezone, timedelta
from typing import Optional, List, Dict, Any

logger = logging.getLogger(__name__)

# Lazy-initialize client to avoid startup crash if InfluxDB not installed
_write_client = None
_query_client = None
_write_api = None
_influx_enabled = None
_error_logged = False


def _get_config() -> dict:
    return {
        "url": os.environ.get("INFLUXDB_URL", ""),
        "token": os.environ.get("INFLUXDB_TOKEN", ""),
        "org": os.environ.get("INFLUXDB_ORG", ""),
        "bucket": os.environ.get("INFLUXDB_BUCKET", "noc-sentinel"),
    }


def is_enabled() -> bool:
    """Check if InfluxDB is properly configured."""
    cfg = _get_config()
    return bool(cfg["url"] and cfg["token"] and cfg["org"])


def _init_clients():
    """Initialize InfluxDB clients lazily."""
    global _write_client, _query_client, _write_api, _influx_enabled, _error_logged
    if _influx_enabled is not None:
        return _influx_enabled
    if not is_enabled():
        _influx_enabled = False
        return False
    try:
        from influxdb_client import InfluxDBClient
        from influxdb_client.client.write_api import SYNCHRONOUS
        cfg = _get_config()
        _write_client = InfluxDBClient(url=cfg["url"], token=cfg["token"], org=cfg["org"])
        _write_api = _write_client.write_api(write_options=SYNCHRONOUS)
        _query_client = _write_client.query_api()
        _influx_enabled = True
        logger.info(f"InfluxDB client initialized: {cfg['url']}")
        return True
    except ImportError:
        if not _error_logged:
            logger.warning("influxdb-client not installed. Run: pip install influxdb-client==3.7.0")
            _error_logged = True
        _influx_enabled = False
        return False
    except Exception as e:
        if not _error_logged:
            logger.error(f"InfluxDB connection failed: {e}")
            _error_logged = True
        _influx_enabled = False
        return False


def write_device_metrics(device_id: str, device_name: str, metrics: dict):
    """
    Write device polling metrics to InfluxDB.
    Called from core/polling.py after each successful poll.

    Metrics structure expected:
      metrics["cpu"] -> int (CPU %)
      metrics["memory"] -> {"percent": int}
      metrics["ping"] -> {"avg": float, "jitter": float, "loss": int}
      metrics["health"] -> {"cpu_temp": float, "board_temp": float, ...}
      metrics["bandwidth"] -> {iface: {"download_bps": int, "upload_bps": int}}
    """
    if not _init_clients():
        return
    cfg = _get_config()
    try:
        from influxdb_client import Point, WritePrecision
        now = datetime.now(timezone.utc)
        points = []

        # System metrics point
        sys_point = (
            Point("device_metrics")
            .tag("device_id", device_id)
            .tag("device_name", device_name)
            .field("cpu_percent", float(metrics.get("cpu", 0)))
            .field("memory_percent", float(metrics.get("memory", {}).get("percent", 0)))
            .time(now, WritePrecision.SECONDS)
        )
        ping = metrics.get("ping", {})
        if ping.get("reachable"):
            sys_point = (
                sys_point
                .field("ping_ms", float(ping.get("avg", 0)))
                .field("jitter_ms", float(ping.get("jitter", 0)))
                .field("packet_loss", float(ping.get("loss", 0)))
            )
        health = metrics.get("health", {})
        if health.get("cpu_temp"):
            sys_point = sys_point.field("cpu_temp", float(health.get("cpu_temp", 0)))
        if health.get("board_temp"):
            sys_point = sys_point.field("board_temp", float(health.get("board_temp", 0)))
        if health.get("voltage"):
            sys_point = sys_point.field("voltage", float(health.get("voltage", 0)))
        points.append(sys_point)

        # Bandwidth per interface
        for iface, bw in metrics.get("bandwidth", {}).items():
            bw_point = (
                Point("interface_bandwidth")
                .tag("device_id", device_id)
                .tag("device_name", device_name)
                .tag("interface", iface)
                .field("download_bps", int(bw.get("download_bps", 0)))
                .field("upload_bps", int(bw.get("upload_bps", 0)))
                .time(now, WritePrecision.SECONDS)
            )
            points.append(bw_point)

        _write_api.write(bucket=cfg["bucket"], org=cfg["org"], record=points)
    except Exception as e:
        logger.error(f"InfluxDB write error for {device_name}: {e}")


def query_device_metrics(
    device_id: str,
    hours: int = 6,
    measurement: str = "device_metrics",
) -> List[Dict[str, Any]]:
    """
    Query historical metrics from InfluxDB.
    Returns list of {time, cpu_percent, memory_percent, ping_ms, jitter_ms}
    """
    if not _init_clients():
        return []
    cfg = _get_config()
    try:
        query = f'''
from(bucket: "{cfg["bucket"]}")
  |> range(start: -{hours}h)
  |> filter(fn: (r) => r._measurement == "{measurement}")
  |> filter(fn: (r) => r.device_id == "{device_id}")
  |> pivot(rowKey: ["_time"], columnKey: ["_field"], valueColumn: "_value")
  |> sort(columns: ["_time"])
'''
        tables = _query_client.query(query=query, org=cfg["org"])
        result = []
        for table in tables:
            for record in table.records:
                row = {"time": record.get_time().isoformat()}
                for field in ["cpu_percent", "memory_percent", "ping_ms", "jitter_ms", "packet_loss", "cpu_temp", "board_temp", "voltage"]:
                    val = record.values.get(field)
                    if val is not None:
                        row[field] = round(float(val), 2)
                result.append(row)
        return result
    except Exception as e:
        logger.error(f"InfluxDB query error: {e}")
        return []


def query_bandwidth_history(
    device_id: str,
    hours: int = 6,
    interface: str = "all",
) -> List[Dict[str, Any]]:
    """
    Query bandwidth history for a device/interface from InfluxDB.
    Returns list of {time, interface, download_bps, upload_bps}
    """
    if not _init_clients():
        return []
    cfg = _get_config()
    try:
        iface_filter = ""
        if interface and interface != "all":
            iface_filter = f'  |> filter(fn: (r) => r.interface == "{interface}")'

        query = f'''
from(bucket: "{cfg["bucket"]}")
  |> range(start: -{hours}h)
  |> filter(fn: (r) => r._measurement == "interface_bandwidth")
  |> filter(fn: (r) => r.device_id == "{device_id}")
{iface_filter}
  |> pivot(rowKey: ["_time", "interface"], columnKey: ["_field"], valueColumn: "_value")
  |> sort(columns: ["_time"])
'''
        tables = _query_client.query(query=query, org=cfg["org"])
        result = []
        for table in tables:
            for record in table.records:
                result.append({
                    "time": record.get_time().isoformat(),
                    "interface": record.values.get("interface", ""),
                    "download_bps": record.values.get("download_bps", 0),
                    "upload_bps": record.values.get("upload_bps", 0),
                    "download_mbps": round(record.values.get("download_bps", 0) / 1e6, 3),
                    "upload_mbps": round(record.values.get("upload_bps", 0) / 1e6, 3),
                })
        return result
    except Exception as e:
        logger.error(f"InfluxDB bandwidth query error: {e}")
        return []


def test_connection() -> dict:
    """Test InfluxDB connection and return status."""
    global _influx_enabled
    _influx_enabled = None  # Reset to force re-init
    if not is_enabled():
        return {"connected": False, "error": "InfluxDB tidak dikonfigurasi (URL/Token/Org kosong)"}
    ok = _init_clients()
    if not ok:
        return {"connected": False, "error": "Gagal koneksi ke InfluxDB. Cek URL, token, dan pastikan InfluxDB sedang berjalan."}
    try:
        cfg = _get_config()
        health = _write_client.health()
        return {
            "connected": True,
            "status": health.status,
            "version": health.version,
            "url": cfg["url"],
            "org": cfg["org"],
            "bucket": cfg["bucket"],
        }
    except Exception as e:
        return {"connected": False, "error": str(e)}
