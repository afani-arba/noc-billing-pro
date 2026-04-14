"""
Reports router: generate traffic and device summary reports.
"""
from fastapi import APIRouter, Depends
from pydantic import BaseModel
from typing import Optional
from datetime import datetime, timezone, timedelta
from core.db import get_db
from core.auth import get_current_user
from mikrotik_api import get_api_client
import asyncio
import logging

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/reports", tags=["reports"])


class ReportRequest(BaseModel):
    period: str
    device_id: Optional[str] = None
    client_name: Optional[str] = ""
    engineer_name: Optional[str] = ""
    company_name: Optional[str] = "PT ARSYA BAROKAH ABADI"


@router.post("/generate")
async def generate_report(data: ReportRequest, user=Depends(get_current_user)):
    db = get_db()
    now = datetime.now()  # local server time (avoid UTC "yesterday" bug for WIB users)
    now_utc = datetime.now(timezone.utc)
    hours_map = {"daily": 24, "weekly": 168, "monthly": 720}
    h = hours_map.get(data.period, 24)
    start = now_utc - timedelta(hours=h)   # query DB dengan UTC
    label_map = {"daily": "Laporan Monitoring Harian", "weekly": "Laporan Monitoring Mingguan", "monthly": "Laporan Monitoring Bulanan"}
    label = label_map.get(data.period, "Laporan Monitoring")

    all_devs = await db.devices.find(
        {}, {"_id": 0, "snmp_community": 0, "api_password": 0, "last_poll_data": 0}
    ).to_list(200)

    query = {"timestamp": {"$gte": start.isoformat()}}
    if data.device_id:
        query["device_id"] = data.device_id
    history = await db.traffic_history.find(query, {"_id": 0}).sort("timestamp", 1).to_list(5000)

    trend = []
    for h_item in history:
        try:
            dt = datetime.fromisoformat(h_item["timestamp"])
            tl = dt.strftime("%H:%M") if data.period == "daily" else dt.strftime("%d/%m %H:%M")
        except Exception:
            tl = ""
        bw = h_item.get("bandwidth", {})
        dl = sum(v.get("download_bps", 0) for v in bw.values())
        ul = sum(v.get("upload_bps", 0) for v in bw.values())
        trend.append({
            "time": tl, "download": round(dl / 1e6, 2), "upload": round(ul / 1e6, 2),
            "ping": h_item.get("ping_ms", 0), "jitter": h_item.get("jitter_ms", 0)
        })

    if trend:
        avg_dl = round(sum(t["download"] for t in trend) / len(trend), 2)
        avg_ul = round(sum(t["upload"] for t in trend) / len(trend), 2)
        peak_dl = round(max(t["download"] for t in trend), 2)
        peak_ul = round(max(t["upload"] for t in trend), 2)
        avg_ping = round(sum(t["ping"] for t in trend) / len(trend), 1)
        avg_jitter = round(sum(t["jitter"] for t in trend) / len(trend), 1)
    else:
        avg_dl = avg_ul = peak_dl = peak_ul = avg_ping = avg_jitter = 0

    # Build per-device latest bandwidth from history
    dev_bw: dict = {}
    for h_item in history:
        did = h_item.get("device_id", "")
        bw = h_item.get("bandwidth", {})
        dl = sum(v.get("download_bps", 0) for v in bw.values())
        ul = sum(v.get("upload_bps", 0) for v in bw.values())
        dev_bw[did] = {"dl": round(dl / 1e6, 0), "ul": round(ul / 1e6, 0)}

    # Filter devices for summary (if specific device chosen)
    if data.device_id and data.device_id != "all":
        report_devs = [d for d in all_devs if d.get("id") == data.device_id]
    else:
        report_devs = all_devs

    # CPU/memory categorization
    cpu_normal = cpu_warn = cpu_crit = 0
    mem_normal = mem_warn = mem_crit = 0

    dev_summary = []
    for d in report_devs:
        dev_id = d.get("id", "")
        cpu = d.get("cpu_load", 0)
        mem = d.get("memory_usage", 0)

        if cpu <= 60: cpu_normal += 1
        elif cpu <= 80: cpu_warn += 1
        else: cpu_crit += 1

        if mem <= 70: mem_normal += 1
        elif mem <= 85: mem_warn += 1
        else: mem_crit += 1

        bw_entry = dev_bw.get(dev_id, {"dl": 0, "ul": 0})
        status = d.get("status", "unknown")

        # Determine action hint
        action = "OK"
        if status != "online":
            action = "URGENT"
        elif cpu > 80:
            action = "Investigate"
        elif cpu > 60 or mem > 85:
            action = "Check RAM" if mem > 85 else "Monitor"

        dev_summary.append({
            "name": d.get("name", ""), "ip_address": d.get("ip_address", ""),
            "location": d.get("location", d.get("group", "")),
            "model": d.get("model", ""),
            "status": status,
            "cpu": cpu, "memory": mem,
            "uptime": d.get("uptime", "99.9%"),
            "bw_in": bw_entry["dl"],
            "bw_out": bw_entry["ul"],
            "action": action,
        })

    # Incidents from syslog (last 24h)
    syslog_incidents = []
    try:
        syslogs = await db.syslog_messages.find(
            {"timestamp": {"$gte": start.isoformat()}}, {"_id": 0}
        ).sort("timestamp", -1).to_list(50)
        for s in syslogs[:10]:
            syslog_incidents.append({
                "time": datetime.fromisoformat(s.get("timestamp", now.isoformat())).strftime("%I:%M %p") if s.get("timestamp") else "",
                "device": s.get("source_ip", s.get("hostname", "Unknown")),
                "severity": s.get("severity", "INFO"),
                "description": s.get("message", "")[:80],
                "action": "Check logs",
                "status": "OPEN",
                "pic": user.get("full_name", "NOC") if isinstance(user, dict) else "NOC",
            })
    except Exception:
        pass

    # Availability stats
    online_devs = [d for d in all_devs if d.get("status") == "online"]
    total_devs = len(all_devs)
    online_count = len(online_devs)
    uptime_pct = round((online_count / total_devs * 100) if total_devs > 0 else 100, 1)

    # ── PPPoE & Hotspot active user count (query MikroTik per device) ──
    pppoe_active = pppoe_total = hotspot_active = hotspot_total = 0
    target_devs = report_devs if data.device_id else all_devs
    for dev in target_devs:
        if dev.get("status") != "online":
            continue
        try:
            mt = get_api_client(dev)
            # MT client sudah async — await langsung, tidak perlu asyncio.to_thread
            results = await asyncio.gather(
                mt.list_pppoe_secrets(),
                mt.list_pppoe_active(),
                mt.list_hotspot_users(),
                mt.list_hotspot_active(),
                return_exceptions=True
            )
            secrets_res, active_res, hs_users_res, hs_active_res = results
            pppoe_total   += len(secrets_res)   if isinstance(secrets_res,   list) else 0
            pppoe_active  += len(active_res)    if isinstance(active_res,    list) else 0
            hotspot_total += len(hs_users_res)  if isinstance(hs_users_res,  list) else 0
            hotspot_active += len(hs_active_res) if isinstance(hs_active_res, list) else 0
        except Exception as e:
            logger.debug(f"PPPoE/Hotspot count failed for {dev.get('name')}: {e}")

    return {
        "label": label, "period": data.period,
        "generated_at": now.isoformat(),
        "start_date": start.isoformat(), "end_date": now.isoformat(),
        "company_name": data.company_name or "PT ARSYA BAROKAH ABADI",
        "client_name": data.client_name or "",
        "engineer_name": data.engineer_name or "",
        "pppoe_stats": {"active": pppoe_active, "total": pppoe_total},
        "hotspot_stats": {"active": hotspot_active, "total": hotspot_total},
        "summary": {
            "devices": {"total": total_devs, "online": online_count},
            "avg_bandwidth": {"download": avg_dl, "upload": avg_ul},
            "peak_bandwidth": {"download": peak_dl, "upload": peak_ul},
            "avg_ping": avg_ping, "avg_jitter": avg_jitter,
            "cpu_categories": {"normal": cpu_normal, "warning": cpu_warn, "critical": cpu_crit},
            "mem_categories": {"normal": mem_normal, "warning": mem_warn, "critical": mem_crit},
        },
        "traffic_trend": trend[-300:],
        "device_summary": dev_summary,
        "incidents": syslog_incidents,
        "availability": {
            "uptime_pct": uptime_pct,
            "sla_target": 99.5,
            "total_downtime_mins": round((100 - uptime_pct) * 14.4, 0),  # 24h * 60min
            "full_uptime_devices": sum(1 for d in all_devs if d.get("status") == "online"),
        },
    }
