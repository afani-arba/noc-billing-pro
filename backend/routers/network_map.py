"""
Network Map router: FTTH Topology Management
Supports: MikroTik → OLT → ODC → ODP → Splitter → ONT
"""
import uuid
import logging
from datetime import datetime, timezone
from typing import Optional, List
from fastapi import APIRouter, HTTPException, Depends, Query
from pydantic import BaseModel
from core.auth import get_current_user, require_admin
from core.db import get_db

router = APIRouter(prefix="/network-map", tags=["network-map"])
logger = logging.getLogger(__name__)

VALID_NODE_TYPES = {"mikrotik", "olt", "odc", "odp", "splitter", "ont", "fat", "joint_closure"}
VALID_LINK_TYPES = {"fo_core", "fo_distribution", "fo_drop", "ethernet", "pon"}


def _now():
    return datetime.now(timezone.utc).isoformat()


# ═══════════════════════════════════════════════════════════════════════════════
# NODE MODELS
# ═══════════════════════════════════════════════════════════════════════════════

class NodeCreate(BaseModel):
    type: str
    name: str
    label: str = ""
    parent_id: Optional[str] = None
    x: float = 0
    y: float = 0
    lat: Optional[float] = None
    lng: Optional[float] = None
    meta: dict = {}
    color: str = ""
    icon: str = ""
    notes: str = ""


class NodeUpdate(BaseModel):
    name: Optional[str] = None
    label: Optional[str] = None
    parent_id: Optional[str] = None
    x: Optional[float] = None
    y: Optional[float] = None
    lat: Optional[float] = None
    lng: Optional[float] = None
    meta: Optional[dict] = None
    color: Optional[str] = None
    icon: Optional[str] = None
    notes: Optional[str] = None


class NodePosition(BaseModel):
    lat: float
    lng: float


class LinkCreate(BaseModel):
    source_id: str
    target_id: str
    link_type: str = "fo_core"
    meta: dict = {}
    label: str = ""
    color: str = ""
    notes: str = ""


# ═══════════════════════════════════════════════════════════════════════════════
# NODES CRUD
# ═══════════════════════════════════════════════════════════════════════════════

@router.get("/nodes")
async def list_nodes(
    type: str = Query("", description="Filter by node type"),
    parent_id: str = Query("", description="Filter by parent"),
    mikrotik_device_id: str = Query("", description="Filter by MikroTik device ID (lock per device)"),
    user=Depends(get_current_user),
):
    """List all nodes, optionally filtered by type, parent, or MikroTik device."""
    db = get_db()
    query = {}
    if type:
        query["type"] = type
    if parent_id:
        query["parent_id"] = parent_id
    if mikrotik_device_id:
        query["meta.mikrotik_device_id"] = mikrotik_device_id

    nodes = await db.network_map_nodes.find(query, {"_id": 0}).to_list(5000)
    return nodes


@router.post("/nodes", status_code=201)
async def create_node(data: NodeCreate, user=Depends(get_current_user)):
    """Create a new network map node."""
    if data.type not in VALID_NODE_TYPES:
        raise HTTPException(400, f"Tipe node tidak valid: {data.type}. Pilihan: {VALID_NODE_TYPES}")

    db = get_db()
    doc = data.model_dump()
    doc["id"] = str(uuid.uuid4())
    doc["created_at"] = _now()
    doc["updated_at"] = _now()

    # Default colors per type
    if not doc["color"]:
        colors = {
            "mikrotik": "#3b82f6", "olt": "#8b5cf6", "odc": "#f59e0b",
            "odp": "#10b981", "splitter": "#6366f1", "ont": "#06b6d4",
            "fat": "#ec4899", "joint_closure": "#ef4444",
        }
        doc["color"] = colors.get(data.type, "#6b7280")

    await db.network_map_nodes.insert_one(doc)
    doc.pop("_id", None)
    return doc


@router.get("/nodes/{node_id}")
async def get_node(node_id: str, user=Depends(get_current_user)):
    """Get a single node by ID."""
    db = get_db()
    node = await db.network_map_nodes.find_one({"id": node_id}, {"_id": 0})
    if not node:
        raise HTTPException(404, "Node tidak ditemukan")
    return node


@router.put("/nodes/{node_id}")
async def update_node(node_id: str, data: NodeUpdate, user=Depends(get_current_user)):
    """Update a network map node."""
    db = get_db()
    raw = data.model_dump(exclude_unset=True)
    if not raw:
        raise HTTPException(400, "Tidak ada data untuk diupdate")

    raw["updated_at"] = _now()
    r = await db.network_map_nodes.update_one({"id": node_id}, {"$set": raw})
    if r.matched_count == 0:
        raise HTTPException(404, "Node tidak ditemukan")
    return await db.network_map_nodes.find_one({"id": node_id}, {"_id": 0})


@router.patch("/nodes/{node_id}/position")
async def update_node_position(node_id: str, data: NodePosition, user=Depends(get_current_user)):
    """Update node geographic position (lat/lng)."""
    db = get_db()
    r = await db.network_map_nodes.update_one(
        {"id": node_id},
        {"$set": {"lat": data.lat, "lng": data.lng, "updated_at": _now()}}
    )
    if r.matched_count == 0:
        raise HTTPException(404, "Node tidak ditemukan")
    return {"ok": True, "lat": data.lat, "lng": data.lng}


@router.delete("/nodes/{node_id}")
async def delete_node(node_id: str, user=Depends(require_admin)):
    """Delete a node and all its links."""
    db = get_db()
    r = await db.network_map_nodes.delete_one({"id": node_id})
    if r.deleted_count == 0:
        raise HTTPException(404, "Node tidak ditemukan")
    # Delete related links
    await db.network_map_links.delete_many({
        "$or": [{"source_id": node_id}, {"target_id": node_id}]
    })
    # Nullify parent_id of children
    await db.network_map_nodes.update_many(
        {"parent_id": node_id},
        {"$set": {"parent_id": None}}
    )
    return {"message": "Node dan link terkait berhasil dihapus"}


# ═══════════════════════════════════════════════════════════════════════════════
# LINKS CRUD
# ═══════════════════════════════════════════════════════════════════════════════

@router.get("/links")
async def list_links(user=Depends(get_current_user)):
    """List all links/connections."""
    db = get_db()
    return await db.network_map_links.find({}, {"_id": 0}).to_list(10000)


@router.post("/links", status_code=201)
async def create_link(data: LinkCreate, user=Depends(get_current_user)):
    """Create a connection between two nodes."""
    if data.link_type not in VALID_LINK_TYPES:
        raise HTTPException(400, f"Tipe link tidak valid: {data.link_type}")

    db = get_db()
    # Validate both nodes exist
    src = await db.network_map_nodes.find_one({"id": data.source_id})
    tgt = await db.network_map_nodes.find_one({"id": data.target_id})
    if not src:
        raise HTTPException(404, f"Source node tidak ditemukan: {data.source_id}")
    if not tgt:
        raise HTTPException(404, f"Target node tidak ditemukan: {data.target_id}")

    # Check duplicate
    existing = await db.network_map_links.find_one({
        "$or": [
            {"source_id": data.source_id, "target_id": data.target_id},
            {"source_id": data.target_id, "target_id": data.source_id},
        ]
    })
    if existing:
        raise HTTPException(409, "Koneksi antara kedua node ini sudah ada")

    doc = data.model_dump()
    doc["id"] = str(uuid.uuid4())
    doc["created_at"] = _now()

    # Default color per link type
    if not doc["color"]:
        link_colors = {
            "fo_core": "#f59e0b", "fo_distribution": "#3b82f6",
            "fo_drop": "#10b981", "ethernet": "#6b7280", "pon": "#8b5cf6",
        }
        doc["color"] = link_colors.get(data.link_type, "#6b7280")

    await db.network_map_links.insert_one(doc)
    doc.pop("_id", None)
    return doc


@router.delete("/links/{link_id}")
async def delete_link(link_id: str, user=Depends(get_current_user)):
    """Delete a connection."""
    db = get_db()
    r = await db.network_map_links.delete_one({"id": link_id})
    if r.deleted_count == 0:
        raise HTTPException(404, "Link tidak ditemukan")
    return {"message": "Link berhasil dihapus"}


# ═══════════════════════════════════════════════════════════════════════════════
# TREE & STATS
# ═══════════════════════════════════════════════════════════════════════════════

@router.get("/tree")
async def get_tree(
    mikrotik_device_id: str = Query("", description="Filter tree by MikroTik device ID"),
    user=Depends(get_current_user),
):
    """Get hierarchical tree of all nodes."""
    db = get_db()
    node_query = {}
    if mikrotik_device_id:
        node_query["meta.mikrotik_device_id"] = mikrotik_device_id
    nodes = await db.network_map_nodes.find(node_query, {"_id": 0}).to_list(5000)
    # Filter links to only include those between filtered nodes
    node_ids = {n["id"] for n in nodes}
    all_links = await db.network_map_links.find({}, {"_id": 0}).to_list(10000)
    links = [l for l in all_links if l["source_id"] in node_ids and l["target_id"] in node_ids]

    # Build adjacency from links
    children_map = {}
    for link in links:
        src = link["source_id"]
        tgt = link["target_id"]
        children_map.setdefault(src, []).append(tgt)

    # Find root nodes (nodes that are never a target)
    all_targets = {l["target_id"] for l in links}
    all_ids = {n["id"] for n in nodes}
    roots = all_ids - all_targets

    node_map = {n["id"]: n for n in nodes}

    def build_subtree(nid, depth=0):
        node = node_map.get(nid)
        if not node or depth > 10:
            return None
        children = []
        for child_id in children_map.get(nid, []):
            child = build_subtree(child_id, depth + 1)
            if child:
                children.append(child)
        return {**node, "children": children}

    tree = []
    for rid in sorted(roots, key=lambda x: node_map.get(x, {}).get("type", "")):
        t = build_subtree(rid)
        if t:
            tree.append(t)

    # Add orphan nodes (not in any link)
    linked_ids = all_targets | {l["source_id"] for l in links}
    for n in nodes:
        if n["id"] not in linked_ids:
            tree.append({**n, "children": []})

    return tree


@router.get("/stats")
async def get_stats(
    mikrotik_device_id: str = Query("", description="Filter stats by MikroTik device ID"),
    user=Depends(get_current_user),
):
    """Get statistics about the network map."""
    db = get_db()
    node_query = {}
    if mikrotik_device_id:
        node_query["meta.mikrotik_device_id"] = mikrotik_device_id
    nodes = await db.network_map_nodes.find(node_query, {"_id": 0, "type": 1, "meta": 1}).to_list(5000)
    node_ids = {n.get("id") for n in nodes}
    all_links = await db.network_map_links.find({}, {"_id": 0, "link_type": 1, "source_id": 1, "target_id": 1}).to_list(10000)
    links = [l for l in all_links if not mikrotik_device_id or (l["source_id"] in node_ids and l["target_id"] in node_ids)]

    type_counts = {}
    for n in nodes:
        t = n.get("type", "unknown")
        type_counts[t] = type_counts.get(t, 0) + 1

    link_type_counts = {}
    for l in links:
        lt = l.get("link_type", "unknown")
        link_type_counts[lt] = link_type_counts.get(lt, 0) + 1

    # ODP/ODC capacity stats
    total_odp_capacity = 0
    total_odp_used = 0
    for n in nodes:
        if n.get("type") in ("odp", "odc"):
            m = n.get("meta", {})
            total_odp_capacity += m.get("capacity", 0)
            total_odp_used += m.get("used", 0)

    return {
        "total_nodes": len(nodes),
        "total_links": len(links),
        "by_type": type_counts,
        "by_link_type": link_type_counts,
        "total_capacity": total_odp_capacity,
        "total_used": total_odp_used,
        "utilization_pct": round(total_odp_used / total_odp_capacity * 100, 1) if total_odp_capacity else 0,
    }


# ═══════════════════════════════════════════════════════════════════════════════
# AUTO-IMPORT
# ═══════════════════════════════════════════════════════════════════════════════

@router.post("/import-devices")
async def import_mikrotik_devices(user=Depends(require_admin)):
    """Auto-import MikroTik devices from Device Hub as network map nodes."""
    db = get_db()
    devices = await db.devices.find({}, {"_id": 0, "id": 1, "name": 1, "ip_address": 1, "lat": 1, "lng": 1}).to_list(200)

    imported = 0
    skipped = 0
    for dev in devices:
        # Check if already imported
        existing = await db.network_map_nodes.find_one({
            "type": "mikrotik", "meta.device_id": dev["id"]
        })
        if existing:
            skipped += 1
            continue

        doc = {
            "id": str(uuid.uuid4()),
            "type": "mikrotik",
            "name": dev.get("name", "MikroTik"),
            "label": dev.get("name", ""),
            "parent_id": None,
            "x": 0, "y": 0,
            "lat": dev.get("lat"),
            "lng": dev.get("lng"),
            "address": "",
            "meta": {
                "device_id": dev["id"],
                "management_ip": dev.get("ip_address", ""),
            },
            "color": "#3b82f6",
            "icon": "router",
            "notes": f"Auto-imported from Device Hub",
            "created_at": _now(),
            "updated_at": _now(),
        }
        await db.network_map_nodes.insert_one(doc)
        imported += 1

    return {"message": f"Import selesai: {imported} ditambahkan, {skipped} sudah ada", "imported": imported, "skipped": skipped}


@router.post("/import-onts")
async def import_onts_from_genieacs(user=Depends(require_admin)):
    """Auto-import ONTs from GenieACS as network map nodes."""
    db = get_db()
    try:
        import asyncio
        from services import genieacs_service as svc
        devices = await asyncio.to_thread(svc.get_devices, 500, "", "")
    except Exception as e:
        raise HTTPException(503, f"Gagal mengambil data dari GenieACS: {e}")

    imported = 0
    skipped = 0
    for dev in devices:
        device_id = dev.get("_id", "")
        serial = dev.get("_deviceId", {}).get("_SerialNumber", "") if isinstance(dev.get("_deviceId"), dict) else ""

        # Check if already imported
        existing = await db.network_map_nodes.find_one({
            "type": "ont", "meta.genieacs_id": device_id
        })
        if existing:
            skipped += 1
            continue

        # Extract useful info
        model = ""
        if isinstance(dev.get("_deviceId"), dict):
            model = dev["_deviceId"].get("_ProductClass", "")

        # Try to find linked customer
        customer_name = ""
        pppoe_user = ""
        customer_doc = await db.customers.find_one(
            {"ont_device_id": device_id},
            {"_id": 0, "name": 1, "username": 1}
        )
        if customer_doc:
            customer_name = customer_doc.get("name", "")
            pppoe_user = customer_doc.get("username", "")

        doc = {
            "id": str(uuid.uuid4()),
            "type": "ont",
            "name": customer_name or serial or device_id[:20],
            "label": pppoe_user or serial,
            "parent_id": None,
            "x": 0, "y": 0,
            "lat": None, "lng": None,
            "address": "",
            "meta": {
                "genieacs_id": device_id,
                "serial_number": serial,
                "model": model,
                "customer_name": customer_name,
                "pppoe_username": pppoe_user,
            },
            "color": "#06b6d4",
            "icon": "ont",
            "notes": "Auto-imported from GenieACS",
            "created_at": _now(),
            "updated_at": _now(),
        }
        await db.network_map_nodes.insert_one(doc)
        imported += 1

    return {"message": f"Import ONT selesai: {imported} ditambahkan, {skipped} sudah ada", "imported": imported, "skipped": skipped}
