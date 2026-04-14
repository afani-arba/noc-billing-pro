"""
Incident Management router v3:
Kanban-style ticket system for NOC incidents.
Status: open → in_progress → resolved
"""
import uuid
import logging
from datetime import datetime, timezone
from typing import Optional, List
from fastapi import APIRouter, HTTPException, Depends, Query
from pydantic import BaseModel
from core.db import get_db
from core.auth import get_current_user, require_admin

router = APIRouter(prefix="/incidents", tags=["incidents"])
logger = logging.getLogger(__name__)

# ── Pydantic Models ─────────────────────────────────────────────────────────

class CommentCreate(BaseModel):
    text: str

class IncidentCreate(BaseModel):
    title: str
    description: str = ""
    device_id: str = ""
    device_name: str = ""
    severity: str = "medium"    # critical | high | medium | low
    assignee: str = ""
    site: str = ""              # location/site info

class IncidentUpdate(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    device_id: Optional[str] = None
    device_name: Optional[str] = None
    severity: Optional[str] = None
    status: Optional[str] = None   # open | in_progress | resolved
    assignee: Optional[str] = None
    site: Optional[str] = None

VALID_STATUSES = {"open", "in_progress", "resolved"}
VALID_SEVERITIES = {"critical", "high", "medium", "low"}


def _inc_id() -> str:
    """Generate a human-readable incident ID like INC-20240311-0001."""
    ts = datetime.now(timezone.utc).strftime("%Y%m%d")
    uid = str(uuid.uuid4())[:6].upper()
    return f"INC-{ts}-{uid}"


def _sanitize(inc: dict) -> dict:
    inc.pop("_id", None)
    return inc


# ── Endpoints ────────────────────────────────────────────────────────────────

@router.get("")
async def list_incidents(
    status: Optional[str] = Query(None),              # open | in_progress | resolved
    severity: Optional[str] = Query(None),
    device_id: Optional[str] = Query(None),
    assignee: Optional[str] = Query(None),
    date_from: Optional[str] = Query(None),
    date_to: Optional[str] = Query(None),
    limit: int = Query(200, ge=1, le=500),
    skip: int = Query(0, ge=0),
    user=Depends(get_current_user)
):
    """List incidents with filtering. Returns all statuses grouped for kanban."""
    db = get_db()
    query: dict = {}

    if status and status in VALID_STATUSES:
        query["status"] = status
    if severity and severity in VALID_SEVERITIES:
        query["severity"] = severity
    if device_id:
        query["device_id"] = device_id
    if assignee:
        query["assignee"] = {"$regex": assignee, "$options": "i"}
    if date_from or date_to:
        ts_filter: dict = {}
        if date_from:
            ts_filter["$gte"] = date_from
        if date_to:
            ts_filter["$lt"] = date_to + "T23:59:59"
        query["created_at"] = ts_filter

    total = await db.incidents.count_documents(query)
    incidents = await db.incidents.find(query, {"_id": 0}).sort("created_at", -1).skip(skip).limit(limit).to_list(limit)

    # Enrich with elapsed time
    now = datetime.now(timezone.utc)
    for inc in incidents:
        try:
            created = datetime.fromisoformat(inc["created_at"].replace("Z", "+00:00"))
            if created.tzinfo is None:
                created = created.replace(tzinfo=timezone.utc)
            elapsed = now - created
            total_minutes = int(elapsed.total_seconds() / 60)
            if total_minutes < 60:
                inc["elapsed_str"] = f"{total_minutes}m ago"
            elif total_minutes < 1440:
                inc["elapsed_str"] = f"{total_minutes // 60}h {total_minutes % 60}m ago"
            else:
                inc["elapsed_str"] = f"{elapsed.days}d ago"
        except Exception:
            inc["elapsed_str"] = ""

    return {"total": total, "incidents": incidents}


@router.get("/kanban")
async def kanban_board(user=Depends(get_current_user)):
    """
    Return incidents grouped by status for Kanban board rendering.
    Each column has a list of incidents sorted by severity then created_at.
    """
    db = get_db()
    severity_order = {"critical": 0, "high": 1, "medium": 2, "low": 3}

    result = {}
    for status in ["open", "in_progress", "resolved"]:
        items = await db.incidents.find(
            {"status": status}, {"_id": 0}
        ).sort("created_at", -1).to_list(100)

        # Sort within column by severity
        items.sort(key=lambda x: severity_order.get(x.get("severity", "low"), 3))

        now = datetime.now(timezone.utc)
        for inc in items:
            try:
                created = datetime.fromisoformat(inc["created_at"].replace("Z", "+00:00"))
                if created.tzinfo is None:
                    created = created.replace(tzinfo=timezone.utc)
                elapsed = now - created
                total_minutes = int(elapsed.total_seconds() / 60)
                if total_minutes < 60:
                    inc["elapsed_str"] = f"{total_minutes}m"
                elif total_minutes < 1440:
                    inc["elapsed_str"] = f"{total_minutes // 60}h {total_minutes % 60}m"
                else:
                    inc["elapsed_str"] = f"{elapsed.days}d"
            except Exception:
                inc["elapsed_str"] = ""

        result[status] = items

    return {
        "open": result["open"],
        "in_progress": result["in_progress"],
        "resolved": result["resolved"],
        "counts": {k: len(v) for k, v in result.items()},
    }


# FIX BUG #9: /stats/overview HARUS ada SEBELUM /{incident_id}
# Karena FastAPI mencocokkan route secara berurutan, jika /{incident_id}
# didaftarkan lebih dulu, /stats/overview tidak pernah bisa diakses.
@router.get("/stats/overview")
async def incident_stats(user=Depends(get_current_user)):
    """Return incident statistics for dashboard widgets."""
    db = get_db()
    open_count = await db.incidents.count_documents({"status": "open"})
    in_progress_count = await db.incidents.count_documents({"status": "in_progress"})
    resolved_count = await db.incidents.count_documents({"status": "resolved"})

    # Breakdown by severity
    severity_counts = {}
    for sev in VALID_SEVERITIES:
        severity_counts[sev] = await db.incidents.count_documents({"severity": sev, "status": {"$ne": "resolved"}})

    return {
        "open": open_count,
        "in_progress": in_progress_count,
        "resolved": resolved_count,
        "total_active": open_count + in_progress_count,
        "by_severity": severity_counts,
    }


@router.get("/{incident_id}")
async def get_incident(incident_id: str, user=Depends(get_current_user)):
    """Get a single incident with full details and timeline."""
    db = get_db()
    inc = await db.incidents.find_one({"id": incident_id}, {"_id": 0})
    if not inc:
        raise HTTPException(404, "Incident not found")
    return inc



@router.post("", status_code=201)
async def create_incident(data: IncidentCreate, user=Depends(get_current_user)):
    """Create a new incident ticket."""
    db = get_db()

    if data.severity not in VALID_SEVERITIES:
        raise HTTPException(400, f"Invalid severity. Must be one of: {', '.join(VALID_SEVERITIES)}")

    now = datetime.now(timezone.utc).isoformat()
    inc_id = _inc_id()

    doc = {
        "id": inc_id,
        "title": data.title.strip(),
        "description": data.description.strip(),
        "device_id": data.device_id,
        "device_name": data.device_name,
        "severity": data.severity,
        "status": "open",
        "assignee": data.assignee,
        "site": data.site,
        "created_at": now,
        "updated_at": now,
        "resolved_at": None,
        "created_by": user.get("username", ""),
        "comments": [],
        "timeline": [
            {
                "action": "created",
                "by": user.get("username", ""),
                "at": now,
                "note": f"Ticket dibuat oleh {user.get('username', 'system')}"
            }
        ],
    }

    await db.incidents.insert_one(doc)
    doc.pop("_id", None)

    # Write to audit log
    try:
        from routers.audit import log_action
        await log_action(
            action="CREATE",
            resource="incidents",
            resource_id=inc_id,
            details=f"Created incident: {data.title} [{data.severity}]",
            username=user.get("username", ""),
            user_id=user.get("id", ""),
        )
    except Exception:
        pass

    logger.info(f"Incident created: {inc_id} by {user.get('username')}")
    return doc


@router.put("/{incident_id}")
async def update_incident(incident_id: str, data: IncidentUpdate, user=Depends(get_current_user)):
    """Update an incident (status change, reassign, etc.)."""
    db = get_db()
    inc = await db.incidents.find_one({"id": incident_id})
    if not inc:
        raise HTTPException(404, "Incident not found")

    updates = {k: v for k, v in data.model_dump().items() if v is not None}
    if not updates:
        raise HTTPException(400, "Nothing to update")

    if "status" in updates and updates["status"] not in VALID_STATUSES:
        raise HTTPException(400, f"Invalid status. Must be one of: {', '.join(VALID_STATUSES)}")
    if "severity" in updates and updates["severity"] not in VALID_SEVERITIES:
        raise HTTPException(400, f"Invalid severity.")

    now = datetime.now(timezone.utc).isoformat()
    updates["updated_at"] = now

    # Build timeline entry
    timeline_note = []
    if "status" in updates:
        old_status = inc.get("status", "")
        new_status = updates["status"]
        timeline_note.append(f"Status: {old_status} → {new_status}")
        if new_status == "resolved":
            updates["resolved_at"] = now
    if "assignee" in updates:
        timeline_note.append(f"Assignee: {inc.get('assignee', '-')} → {updates['assignee']}")
    if "severity" in updates:
        timeline_note.append(f"Severity: {inc.get('severity', '-')} → {updates['severity']}")

    if timeline_note:
        timeline_entry = {
            "action": "updated",
            "by": user.get("username", ""),
            "at": now,
            "note": "; ".join(timeline_note),
        }
        await db.incidents.update_one(
            {"id": incident_id},
            {"$set": updates, "$push": {"timeline": timeline_entry}}
        )
    else:
        await db.incidents.update_one({"id": incident_id}, {"$set": updates})

    # Audit log
    try:
        from routers.audit import log_action
        await log_action(
            action="UPDATE",
            resource="incidents",
            resource_id=incident_id,
            details="; ".join(timeline_note) or "Updated incident",
            username=user.get("username", ""),
            user_id=user.get("id", ""),
        )
    except Exception:
        pass

    updated = await db.incidents.find_one({"id": incident_id}, {"_id": 0})
    return updated


@router.post("/{incident_id}/comments")
async def add_comment(incident_id: str, data: CommentCreate, user=Depends(get_current_user)):
    """Add a comment to an incident."""
    db = get_db()
    inc = await db.incidents.find_one({"id": incident_id})
    if not inc:
        raise HTTPException(404, "Incident not found")

    if not data.text.strip():
        raise HTTPException(400, "Comment text cannot be empty")

    now = datetime.now(timezone.utc).isoformat()
    comment = {
        "id": str(uuid.uuid4())[:8],
        "user": user.get("username", ""),
        "text": data.text.strip(),
        "timestamp": now,
    }

    await db.incidents.update_one(
        {"id": incident_id},
        {
            "$push": {
                "comments": comment,
                "timeline": {
                    "action": "comment",
                    "by": user.get("username", ""),
                    "at": now,
                    "note": f"Menambah komentar"
                }
            },
            "$set": {"updated_at": now}
        }
    )

    return comment


@router.delete("/{incident_id}")
async def delete_incident(incident_id: str, user=Depends(require_admin)):
    """Delete an incident ticket (admin only)."""
    db = get_db()
    r = await db.incidents.delete_one({"id": incident_id})
    if r.deleted_count == 0:
        raise HTTPException(404, "Incident not found")

    try:
        from routers.audit import log_action
        await log_action(
            action="DELETE",
            resource="incidents",
            resource_id=incident_id,
            details=f"Deleted incident {incident_id}",
            username=user.get("username", ""),
            user_id=user.get("id", ""),
        )
    except Exception:
        pass

    return {"message": "Incident deleted"}


# (dipindahkan ke atas /{incident_id} — lihat FIX BUG #9)

