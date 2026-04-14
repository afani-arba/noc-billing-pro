"""
Wallboard router: NOC Wall Display endpoints.
Provides aggregated device status, live metrics, and event ticker
for NOC wall display screens.
"""
import asyncio
import logging
from datetime import datetime, timezone, timedelta
from fastapi import APIRouter, Depends
from core.db import get_db
from core.auth import get_current_user

router = APIRouter(prefix="/wallboard", tags=["wallboard"])
logger = logging.getLogger(__name__)


@router.get("/status")
async def wallboard_status(user=Depends(get_current_user)):
    """
    Return devices with full real-time metrics for wall display grid.
    - administrator / viewer: melihat SEMUA device
    - user: hanya melihat device yang di-tag di allowed_devices
    """
    db = get_db()
    # Fetch tanpa credentials untuk response (aman dikirim ke client)
    devices_all = await db.devices.find({}, {"_id": 0, "snmp_community": 0, "api_password": 0}).to_list(200)

    # Filter berdasarkan role
    role = user.get("role", "user")
    if role == "user":
        allowed = set(user.get("allowed_devices") or [])
        devices = [d for d in devices_all if d["id"] in allowed]
    else:
        devices = devices_all

    enriched = []

    for d in devices:
        # Get last bandwidth from polling cache (last_traffic) instead of querying the DB 60 times
        last_bw = d.get("last_traffic", {})

        download_bps = 0
        upload_bps = 0
        isp_interfaces = d.get("isp_interfaces", [])

        # ── Konstanta filter virtual interface ───────────────────────────────────
        VIRTUAL_PREFIXES = (
            "bridge", "vlan", "lo", "loopback", "ovpn", "pppoe-", "pptp",
            "l2tp", "eoip", "gre", "sstp-", "veth", "docker",
            "ip6tnl", "sit", "tun", "tap", "dummy", "VPN",
        )

        def is_physical(name: str) -> bool:
            """Return True jika interface bukan virtual."""
            n = name.lower()
            return not any(n.startswith(p) for p in VIRTUAL_PREFIXES)

        if last_bw:
            bw = last_bw.get("bandwidth") or {}
            
            # Helper to deduplicate interface summations
            parsed_ifaces = set()

            # ── PRIORITAS 1: isp_bandwidth (field baru, paling akurat) ────────
            # Diisi oleh polling.py berdasarkan comment "ISP1..20/WAN/INPUT" di MikroTik
            isp_bw_stored = last_bw.get("isp_bandwidth") or {}
            if isp_bw_stored:
                for iface_name, iface_bw in isp_bw_stored.items():
                    if isinstance(iface_bw, dict) and iface_name not in parsed_ifaces:
                        download_bps += iface_bw.get("download_bps", 0)
                        upload_bps   += iface_bw.get("upload_bps",   0)
                        parsed_ifaces.add(iface_name)

            # ── PRIORITAS 2: Fallback — filter bw dengan isp_interfaces ──────
            elif bw and isp_interfaces:
                for iface in isp_interfaces:
                    iface_bw = bw.get(iface, {})
                    if isinstance(iface_bw, dict) and iface not in parsed_ifaces:
                        download_bps += iface_bw.get("download_bps", 0)
                        upload_bps   += iface_bw.get("upload_bps",   0)
                        parsed_ifaces.add(iface)

            # ── PRIORITAS 3: Fallback — sum semua interface fisik saja ────────
            # (Digunakan jika MikroTik belum diberi comment ISP/WAN/INPUT)
            elif bw:
                for iface_name, iface_bw in bw.items():
                    if isinstance(iface_bw, dict) and is_physical(iface_name) and iface_name not in parsed_ifaces:
                        download_bps += iface_bw.get("download_bps", 0)
                        upload_bps   += iface_bw.get("upload_bps",   0)
                        parsed_ifaces.add(iface_name)


        # Determine alert level
        alert_level = "normal"
        cpu = d.get("cpu_load", 0)
        mem = d.get("memory_usage", 0)
        ping = last_bw.get("ping_ms", 0) if last_bw else 0

        if d.get("status") == "offline":
            alert_level = "critical"
        elif cpu > 90 or mem > 90:
            alert_level = "critical"
        elif cpu > 75 or mem > 75 or ping > 100:
            alert_level = "warning"

        pppoe_count   = d.get("pppoe_active", 0)
        hotspot_count = d.get("hotspot_active", 0)

        # ── ISP Interface Status (untuk badge ISP Down) ─────────────────────────
        ISP_DOWN_THRESHOLD_BPS = 1_000_000   # 1 Mbps
        isp_status = []
        # isp_interface_comments: {iface_name: comment} — disimpan oleh polling.py dari MikroTik
        isp_name_map = d.get("isp_interface_comments", {}) or {}

        if d.get("status") == "online":
            isp_bw_stored = last_bw.get("isp_bandwidth") if last_bw else None
            bw_data       = last_bw.get("bandwidth")      if last_bw else None

            if isp_bw_stored:
                for iface_name, iface_bw in isp_bw_stored.items():
                    if not isinstance(iface_bw, dict):
                        continue
                    dl_bps = iface_bw.get("download_bps", 0)
                    ul_bps = iface_bw.get("upload_bps",   0)
                    is_down = (
                        (dl_bps < ISP_DOWN_THRESHOLD_BPS and ul_bps < ISP_DOWN_THRESHOLD_BPS)
                        or iface_bw.get("status") == "down"
                    )
                    isp_status.append({
                        "name":          iface_name,
                        "comment":       isp_name_map.get(iface_name, ""),  # comment dari MikroTik
                        "download_mbps": round(dl_bps / 1_000_000, 2),
                        "upload_mbps":   round(ul_bps / 1_000_000, 2),
                        "is_down":       is_down,
                    })
            elif bw_data and isp_interfaces:
                for iface_name in isp_interfaces:
                    iface_bw = bw_data.get(iface_name)
                    if iface_bw is None:
                        isp_status.append({
                            "name":          iface_name,
                            "comment":       isp_name_map.get(iface_name, ""),
                            "download_mbps": 0,
                            "upload_mbps":   0,
                            "is_down":       True,
                        })
                    elif isinstance(iface_bw, dict):
                        dl_bps = iface_bw.get("download_bps", 0)
                        ul_bps = iface_bw.get("upload_bps",   0)
                        is_down = (dl_bps < ISP_DOWN_THRESHOLD_BPS and ul_bps < ISP_DOWN_THRESHOLD_BPS)
                        isp_status.append({
                            "name":          iface_name,
                            "comment":       isp_name_map.get(iface_name, ""),
                            "download_mbps": round(dl_bps / 1_000_000, 2),
                            "upload_mbps":   round(ul_bps / 1_000_000, 2),
                            "is_down":       is_down,
                        })

        enriched.append({
            "id": d.get("id"),
            "name": d.get("name", ""),
            "identity": d.get("identity", d.get("sys_name", d.get("name", ""))),
            "ip_address": d.get("ip_address", ""),
            "status": d.get("status", "unknown"),
            "model": d.get("model", ""),
            "ros_version": d.get("ros_version", ""),
            "uptime": d.get("uptime", ""),
            "cpu_load": cpu,
            "memory_usage": mem,
            "cpu_temp": d.get("cpu_temp", 0),
            "board_temp": d.get("board_temp", 0),
            "ping_ms": round(ping, 1),
            "download_mbps": round(download_bps / 1_000_000, 2),
            "upload_mbps": round(upload_bps / 1_000_000, 2),
            "last_poll": d.get("last_poll", ""),
            "alert_level": alert_level,
            "isp_interfaces": d.get("isp_interfaces", []),
            "isp_status": isp_status,    # per-interface ISP status untuk wallboard badge
            # Session counters dari DB cache
            "pppoe_active":   pppoe_count,
            "hotspot_active": hotspot_count,
        })


    # Sort: critical first, then warning, then normal; within each group: alphabetical
    order = {"critical": 0, "warning": 1, "normal": 2}
    enriched.sort(key=lambda x: (order.get(x["alert_level"], 3), x["name"]))

    # Summary stats
    total = len(enriched)
    online = sum(1 for d in enriched if d["status"] == "online")
    offline = sum(1 for d in enriched if d["status"] == "offline")
    warning = sum(1 for d in enriched if d["alert_level"] == "warning")
    # Akumulasi session counters dari semua device online
    total_pppoe   = sum(d["pppoe_active"]   for d in enriched if d["status"] == "online")
    total_hotspot = sum(d["hotspot_active"] for d in enriched if d["status"] == "online")

    return {
        "devices": enriched,
        "summary": {
            "total": total,
            "online": online,
            "offline": offline,
            "warning": warning,
            "total_pppoe":   total_pppoe,
            "total_hotspot": total_hotspot,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
    }


@router.get("/events")
async def wallboard_events(limit: int = 30, user=Depends(get_current_user)):
    """
    Return recent NOC events for the bottom ticker.
    Sources: sla_events (online/offline transitions) + recent alerts.
    """
    db = get_db()
    now = datetime.now(timezone.utc)
    cutoff = (now - timedelta(hours=24)).isoformat()

    # Get recent SLA events (online/offline transitions)
    sla_events = await db.sla_events.find(
        {"timestamp": {"$gte": cutoff}},
        {"_id": 0}
    ).sort("timestamp", -1).to_list(limit)

    # Get recent incidents
    incidents = await db.incidents.find(
        {"created_at": {"$gte": cutoff}},
        {"_id": 0, "id": 1, "title": 1, "severity": 1, "device_name": 1, "created_at": 1, "status": 1}
    ).sort("created_at", -1).to_list(10)

    events = []

    for e in sla_events:
        event_type = e.get("event_type", "")
        color = "green" if event_type == "online" else "red"
        events.append({
            "id": str(e.get("_id", "")),
            "type": event_type,
            "device_name": e.get("device_name", ""),
            "device_id": e.get("device_id", ""),
            "message": f"{e.get('device_name', 'Device')} went {event_type.upper()}",
            "timestamp": e.get("timestamp", ""),
            "color": color,
        })

    for inc in incidents:
        sev = inc.get("severity", "medium")
        color_map = {"critical": "red", "high": "orange", "medium": "yellow", "low": "blue"}
        events.append({
            "id": inc.get("id", ""),
            "type": "incident",
            "device_name": inc.get("device_name", ""),
            "message": f"INC: {inc.get('title', 'Incident')} [{sev.upper()}]",
            "timestamp": inc.get("created_at", ""),
            "color": color_map.get(sev, "yellow"),
        })

    # Sort by timestamp descending
    events.sort(key=lambda x: x.get("timestamp", ""), reverse=True)

    return {"events": events[:limit]}
