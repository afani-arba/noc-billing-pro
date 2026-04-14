"""
Audit Log router v3: Track all user actions in the system.
Records CREATE, UPDATE, DELETE, LOGIN actions with user context.
"""
import logging
import uuid
from datetime import datetime, timezone, timedelta
from fastapi import APIRouter, Depends, Query
from typing import Optional
from core.db import get_db
from core.auth import get_current_user, require_admin

router = APIRouter(prefix="/audit", tags=["audit"])
logger = logging.getLogger(__name__)


async def log_action(
    action: str,          # CREATE | UPDATE | DELETE | LOGIN | LOGOUT | VIEW
    resource: str,        # devices | incidents | users | settings | etc
    resource_id: str = "",
    details: str = "",
    user_id: str = "",
    username: str = "",
    ip_address: str = "",
):
    """
    Write an audit log entry to the database.
    Call this helper from other routers when performing significant actions.
    """
    try:
        db = get_db()
        await db.audit_logs.insert_one({
            "id": str(uuid.uuid4()),
            "action": action,
            "resource": resource,
            "resource_id": resource_id,
            "details": details,
            "user_id": user_id,
            "username": username,
            "ip_address": ip_address,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })
    except Exception as e:
        logger.warning(f"Audit log write failed: {e}")


@router.get("/logs")
async def list_audit_logs(
    username: Optional[str] = Query(None),
    action: Optional[str] = Query(None),   # CREATE | UPDATE | DELETE | LOGIN
    resource: Optional[str] = Query(None),
    date_from: Optional[str] = Query(None, description="YYYY-MM-DD"),
    date_to: Optional[str] = Query(None, description="YYYY-MM-DD"),
    limit: int = Query(100, ge=1, le=500),
    skip: int = Query(0, ge=0),
    user=Depends(require_admin)
):
    """List audit log entries with optional filters."""
    db = get_db()
    query: dict = {}

    if username:
        query["username"] = {"$regex": username, "$options": "i"}
    if action:
        query["action"] = action.upper()
    if resource:
        query["resource"] = {"$regex": resource, "$options": "i"}

    if date_from or date_to:
        ts_filter: dict = {}
        if date_from:
            try:
                dt = datetime.strptime(date_from, "%Y-%m-%d").replace(tzinfo=timezone.utc)
                ts_filter["$gte"] = dt.isoformat()
            except ValueError:
                pass
        if date_to:
            try:
                dt = datetime.strptime(date_to, "%Y-%m-%d").replace(tzinfo=timezone.utc) + timedelta(days=1)
                ts_filter["$lt"] = dt.isoformat()
            except ValueError:
                pass
        if ts_filter:
            query["timestamp"] = ts_filter

    total = await db.audit_logs.count_documents(query)
    logs = await db.audit_logs.find(query, {"_id": 0}).sort("timestamp", -1).skip(skip).limit(limit).to_list(limit)

    return {
        "total": total,
        "logs": logs,
        "skip": skip,
        "limit": limit,
    }


@router.get("/summary")
async def audit_summary(user=Depends(require_admin)):
    """Return a quick summary of recent audit activity."""
    db = get_db()
    since = (datetime.now(timezone.utc) - timedelta(days=7)).isoformat()
    query = {"timestamp": {"$gte": since}}

    total = await db.audit_logs.count_documents(query)
    actions = {}
    for action in ["CREATE", "UPDATE", "DELETE", "LOGIN", "LOGOUT"]:
        count = await db.audit_logs.count_documents({**query, "action": action})
        if count > 0:
            actions[action] = count

    recent = await db.audit_logs.find(query, {"_id": 0}).sort("timestamp", -1).limit(10).to_list(10)

    return {
        "total_last_7_days": total,
        "by_action": actions,
        "recent": recent,
    }


@router.delete("/logs/purge")
async def purge_old_logs(days: int = 90, user=Depends(require_admin)):
    """Delete audit logs older than N days."""
    cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
    db = get_db()
    result = await db.audit_logs.delete_many({"timestamp": {"$lt": cutoff}})

    # Log this action itself
    await log_action(
        action="DELETE",
        resource="audit_logs",
        details=f"Purged {result.deleted_count} logs older than {days} days",
        username=user.get("username", ""),
        user_id=user.get("id", ""),
    )
    return {"deleted_count": result.deleted_count, "cutoff": cutoff}
