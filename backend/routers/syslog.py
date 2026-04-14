"""
Syslog router: query syslog entries from MongoDB.
"""
from fastapi import APIRouter, Depends
from typing import Optional
from datetime import datetime, timezone, timedelta
from core.db import get_db
from core.auth import get_current_user, require_admin
import os

router = APIRouter(prefix="/syslog", tags=["syslog"])
SYSLOG_PORT = int(os.environ.get("SYSLOG_PORT", "5514"))

SEVERITY_MAP = {
    "emergency": 0, "alert": 1, "critical": 2, "error": 3,
    "warning": 4, "notice": 5, "info": 6, "debug": 7
}


@router.get("/entries")
async def get_syslog_entries(
    source_ip: str = "",
    severity: str = "",
    search: str = "",
    hours: int = 24,
    limit: int = 500,
    user=Depends(get_current_user)
):
    db = get_db()
    cutoff = (datetime.now(timezone.utc) - timedelta(hours=hours)).isoformat()
    query = {"timestamp": {"$gte": cutoff}}
    if source_ip:
        query["source_ip"] = source_ip
    if severity and severity != "all":
        query["severity"] = severity
    if search:
        query["message"] = {"$regex": search, "$options": "i"}
    
    entries = await db.syslog_entries.find(query, {"_id": 0}).sort("timestamp", -1).to_list(limit)
    return entries


@router.get("/stats")
async def get_syslog_stats(hours: int = 24, user=Depends(get_current_user)):
    db = get_db()
    cutoff = (datetime.now(timezone.utc) - timedelta(hours=hours)).isoformat()
    pipeline = [
        {"$match": {"timestamp": {"$gte": cutoff}}},
        {"$group": {"_id": {"source_ip": "$source_ip", "severity": "$severity"}, "count": {"$sum": 1}}},
        {"$sort": {"count": -1}}
    ]
    results = await db.syslog_entries.aggregate(pipeline).to_list(500)
    
    # Reshape: {source_ip: {severity: count}}
    stats = {}
    for r in results:
        ip = r["_id"]["source_ip"]
        sev = r["_id"]["severity"]
        stats.setdefault(ip, {})[sev] = r["count"]
    
    total = await db.syslog_entries.count_documents({"timestamp": {"$gte": cutoff}})
    return {"total": total, "by_device": stats, "port": SYSLOG_PORT}


@router.get("/sources")
async def get_syslog_sources(user=Depends(get_current_user)):
    db = get_db()
    sources = await db.syslog_entries.distinct("source_ip")
    return sources


@router.delete("/entries")
async def clear_all_logs(user=Depends(require_admin)):
    db = get_db()
    r = await db.syslog_entries.delete_many({})
    return {"message": f"Deleted {r.deleted_count} log entries"}
