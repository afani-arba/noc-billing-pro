import uuid
import logging
from datetime import datetime, timezone
from typing import Optional, List
from fastapi import APIRouter, HTTPException, Depends, Query
from pydantic import BaseModel
from core.db import get_db
from core.auth import get_current_user

router = APIRouter(prefix="/technician", tags=["technician"])
logger = logging.getLogger(__name__)

# --- Dependencies ---
async def get_current_technician(user=Depends(get_current_user)):
    if user.get("role") not in ["teknisi", "super_admin", "administrator"]:
        raise HTTPException(status_code=403, detail="Akses ditolak. Membutuhkan role Teknisi.")
    return user

# --- Models ---
class WorkOrderUpdate(BaseModel):
    status: str
    notes: Optional[str] = None
    lat: Optional[float] = None
    lng: Optional[float] = None

class ProvisionRequest(BaseModel):
    name: str
    phone: Optional[str] = ""
    address: Optional[str] = ""
    username: str
    password: str
    package_id: str
    device_id: str
    work_order_id: Optional[str] = None

# --- Endpoints ---
@router.get("/work-orders")
async def list_work_orders(
    status: Optional[str] = None,
    user=Depends(get_current_technician)
):
    db = get_db()
    
    # 1. My Orders (assigned to me)
    my_query = {"assigned_to": user["username"]}
    if status:
        my_query["status"] = status
        
    my_orders = await db.work_orders.find(my_query, {"_id": 0}).sort("created_at", -1).to_list(100)
    
    # 2. Pool Orders (unassigned, pending)
    pool_query = {"assigned_to": "", "status": "pending"}
    pool_orders = await db.work_orders.find(pool_query, {"_id": 0}).sort("created_at", 1).to_list(100) # FIFO: oldest first

    # Also allow super admins to see all
    if user.get("role") in ["super_admin", "administrator"]:
        admin_query = {}
        if status:
            admin_query["status"] = status
        all_orders = await db.work_orders.find(admin_query, {"_id": 0}).sort("created_at", -1).to_list(100)
        return {"ok": True, "data": all_orders, "my_orders": my_orders, "pool_orders": pool_orders}

    return {"ok": True, "data": my_orders, "my_orders": my_orders, "pool_orders": pool_orders}

@router.post("/work-orders/{wo_id}/claim")
async def claim_work_order(wo_id: str, user=Depends(get_current_technician)):
    db = get_db()
    
    # Check current active tasks
    active_count = await db.work_orders.count_documents({
        "assigned_to": user["username"],
        "status": {"$in": ["pending", "on_the_way", "working"]}
    })
    
    if active_count >= 2:
        raise HTTPException(400, "Anda sudah memiliki batas maksimal (2) tugas aktif yang belum diselesaikan.")
        
    wo = await db.work_orders.find_one({"id": wo_id})
    if not wo:
        raise HTTPException(404, "Work Order tidak ditemukan")
    if wo.get("assigned_to"):
        raise HTTPException(400, "Work Order ini sudah diambil oleh teknisi lain")
        
    now = datetime.now(timezone.utc).isoformat()
    await db.work_orders.update_one(
        {"id": wo_id},
        {"$set": {"assigned_to": user["username"], "updated_at": now}}
    )
    
    # Update incident timeline if linked
    if wo.get("incident_id"):
        await db.incidents.update_one(
            {"id": wo["incident_id"]},
            {"$push": {
                "timeline": {
                    "action": "assigned",
                    "by": user["username"],
                    "at": now,
                    "note": f"Tiket diambil (claim) oleh teknisi {user['username']}"
                }
            }, "$set": {"assignee": user["username"], "updated_at": now}}
        )
        
    return {"ok": True, "message": "Tugas berhasil diklaim!"}

@router.get("/work-orders/{wo_id}")
async def get_work_order(wo_id: str, user=Depends(get_current_technician)):
    db = get_db()
    query = {"id": wo_id}
    # Restrict to assigned user unless admin
    if user.get("role") not in ["super_admin", "administrator"]:
        query["assigned_to"] = user["username"]
        
    wo = await db.work_orders.find_one(query, {"_id": 0})
    if not wo:
        raise HTTPException(404, "Work Order tidak ditemukan atau bukan milik Anda")
    return {"ok": True, "data": wo}

@router.patch("/work-orders/{wo_id}")
async def update_work_order(wo_id: str, data: WorkOrderUpdate, user=Depends(get_current_technician)):
    db = get_db()
    query = {"id": wo_id}
    if user.get("role") not in ["super_admin", "administrator"]:
        query["assigned_to"] = user["username"]
        
    wo = await db.work_orders.find_one(query)
    if not wo:
        raise HTTPException(404, "Work Order tidak ditemukan")
        
    now = datetime.now(timezone.utc).isoformat()
    updates = {"status": data.status, "updated_at": now}
    
    if data.notes:
        updates["notes"] = data.notes
        
    if data.status == "on_the_way":
        updates["departed_at"] = now
    elif data.status == "working":
        updates["arrived_at"] = now
    elif data.status == "completed":
        updates["completed_at"] = now
        
    # If there is an associated incident, update it as well
    if data.status == "completed" and wo.get("incident_id"):
        await db.incidents.update_one(
            {"id": wo["incident_id"]},
            {
                "$set": {"status": "resolved", "resolved_at": now, "updated_at": now},
                "$push": {
                    "timeline": {
                        "action": "resolved",
                        "by": user["username"],
                        "at": now,
                        "note": "Diselesaikan oleh teknisi di lapangan"
                    }
                }
            }
        )
        
    await db.work_orders.update_one({"id": wo_id}, {"$set": updates})
    return {"ok": True, "message": f"Status diperbarui menjadi {data.status}"}

@router.post("/provision")
async def provision_pppoe(data: ProvisionRequest, user=Depends(get_current_technician)):
    """Membuat pelanggan baru + PPPoE rahasia langsung dari lapangan."""
    db = get_db()
    
    # Validasi package
    pkg = await db.billing_packages.find_one({"id": data.package_id})
    if not pkg:
        raise HTTPException(404, "Paket tidak ditemukan")
        
    # Validasi device
    device = await db.devices.find_one({"id": data.device_id})
    if not device:
        raise HTTPException(404, "Device/Router tidak ditemukan")
        
    # Cek duplikat username
    existing = await db.customers.find_one({"username": data.username, "device_id": data.device_id})
    if existing:
        raise HTTPException(400, "Username PPPoE sudah ada di router tersebut")

    # 1. Panggil API MikroTik
    from mikrotik_api import get_api_client
    try:
        mt = get_api_client(device)
        secret_data = {
            "name": data.username,
            "password": data.password,
            "service": "ppp",
            "disabled": "no",
            "profile": pkg.get("profile_name", ""),
            "comment": data.name
        }
        await mt.create_pppoe_secret(secret_data)
    except Exception as e:
        raise HTTPException(500, f"Gagal membuat PPPoE di router: {str(e)}")

    # 2. Simpan ke database customers
    import random, string
    customer_id = str(uuid.uuid4())
    client_id = ''.join(random.choices(string.digits, k=10))
    now = datetime.now(timezone.utc).isoformat()
    
    cust_doc = {
        "id": customer_id,
        "client_id": client_id,
        "name": data.name,
        "phone": data.phone,
        "address": data.address,
        "service_type": "pppoe",
        "username": data.username,
        "device_id": data.device_id,
        "package_id": data.package_id,
        "due_day": 10,
        "billing_type": "postpaid",
        "active": True,
        "auth_method": "local",
        "password": data.password,
        "start_date": now,
        "created_at": now,
        "profile": pkg.get("profile_name", ""),
        "created_by": user["username"],
    }
    await db.customers.insert_one(cust_doc)
    
    # 3. Update WO jika ada
    if data.work_order_id:
        await db.work_orders.update_one(
            {"id": data.work_order_id},
            {"$set": {"customer_id": customer_id, "status": "completed", "completed_at": now}}
        )

    return {"ok": True, "message": "PPPoE berhasil dibuat dan pelanggan didaftarkan", "customer_id": customer_id}
