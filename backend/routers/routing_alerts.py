"""
Routing Alerts router: API untuk history dan current state BGP/OSPF alerts.
"""
import logging
from fastapi import APIRouter, Depends
from core.db import get_db
from core.auth import get_current_user, require_admin

router = APIRouter(prefix="/routing-alerts", tags=["routing-alerts"])
logger = logging.getLogger(__name__)


@router.get("/history")
async def get_routing_alert_history(limit: int = 50, user=Depends(get_current_user)):
    """History alert BGP/OSPF — down dan recover events."""
    db = get_db()
    history = await db.routing_alert_history.find(
        {},
        {"_id": 0}
    ).sort("timestamp", -1).limit(limit).to_list(limit)
    return history


@router.get("/state")
async def get_routing_state(user=Depends(get_current_user)):
    """State terkini semua BGP peer dan OSPF neighbor di semua device."""
    db = get_db()
    states = await db.bgp_alert_state.find({}, {"_id": 0}).to_list(500)
    bgp = [s for s in states if not s.get("type") or s.get("type") == "bgp"]
    ospf = [s for s in states if s.get("type") == "ospf"]
    return {
        "bgp": bgp,
        "ospf": ospf,
        "total_bgp_peers": len(bgp),
        "bgp_established": sum(1 for s in bgp if s.get("state") == "established"),
        "bgp_down": sum(1 for s in bgp if s.get("state") != "established"),
        "total_ospf_neighbors": len(ospf),
        "ospf_full": sum(1 for s in ospf if "full" in (s.get("state") or "")),
    }


@router.get("/history/{device_id}")
async def get_device_routing_alerts(device_id: str, limit: int = 30, user=Depends(get_current_user)):
    """History alert BGP/OSPF untuk device tertentu."""
    db = get_db()
    history = await db.routing_alert_history.find(
        {"device_id": device_id},
        {"_id": 0}
    ).sort("timestamp", -1).limit(limit).to_list(limit)
    return history


@router.delete("/history")
async def clear_routing_alert_history(user=Depends(require_admin)):
    """Hapus semua history alert BGP/OSPF."""
    db = get_db()
    result = await db.routing_alert_history.delete_many({})
    return {"message": f"Deleted {result.deleted_count} alert history records"}
