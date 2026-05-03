import logging
from datetime import datetime, timezone, date
from typing import Optional
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from core.db import get_db
from core.auth import get_current_user

router = APIRouter(prefix="/collector", tags=["collector"])
logger = logging.getLogger(__name__)

# --- Dependencies ---
async def get_current_collector(user=Depends(get_current_user)):
    if user.get("role") not in ["kolektor", "super_admin", "administrator"]:
        raise HTTPException(status_code=403, detail="Akses ditolak. Membutuhkan role Kolektor.")
    return user

# --- Models ---
class PaymentRequest(BaseModel):
    payment_method: str = "cash"
    notes: Optional[str] = ""

class NoteRequest(BaseModel):
    notes: str

# --- Endpoints ---
@router.get("/invoices")
async def list_assigned_invoices(
    status: Optional[str] = "unpaid",
    user=Depends(get_current_collector)
):
    """Melihat tagihan yang belum dibayar."""
    db = get_db()
    query = {"status": {"$in": ["unpaid", "overdue"]}}
    
    # Normally we would filter by assigned_collector, but for now we list all unpaid
    # To restrict it, we could add assigned_to field on invoices or customers
    if user.get("role") not in ["super_admin", "administrator"]:
        # If you have area logic, filter here. For simplicity, collector sees all unpaid
        pass

    invoices = await db.invoices.find(query, {"_id": 0}).sort("due_date", 1).to_list(200)
    
    # Enrich with customer details for field collection
    customer_ids = [inv.get("customer_id") for inv in invoices if inv.get("customer_id")]
    customers = await db.customers.find({"id": {"$in": customer_ids}}, {"_id": 0, "id": 1, "address": 1, "phone": 1, "name": 1}).to_list(200)
    cust_map = {c["id"]: c for c in customers}
    
    for inv in invoices:
        cid = inv.get("customer_id")
        if cid in cust_map:
            inv["customer_address"] = cust_map[cid].get("address", "")
            inv["customer_phone"] = cust_map[cid].get("phone", "")
            inv["customer_name"] = cust_map[cid].get("name", "")
            
    return {"ok": True, "data": invoices}

@router.post("/invoices/{inv_id}/pay")
async def pay_invoice_in_field(inv_id: str, data: PaymentRequest, user=Depends(get_current_collector)):
    """Kolektor menandai lunas dari lapangan (terima cash)."""
    db = get_db()
    inv = await db.invoices.find_one({"id": inv_id})
    if not inv:
        raise HTTPException(404, "Invoice tidak ditemukan")
        
    if inv.get("status") == "paid":
        return {"ok": False, "message": "Invoice sudah lunas sebelumnya"}
        
    now = datetime.now(timezone.utc).isoformat()
    
    # Tambahkan catatan kolektor
    admin_note = inv.get("admin_notes", "")
    new_note = f"[Ditagih Kolektor {user['username']} via {data.payment_method}] {data.notes}"
    combined_note = f"{admin_note}\n{new_note}".strip()

    updates = {
        "status": "paid",
        "paid_at": now,
        "payment_method": data.payment_method,
        "admin_notes": combined_note,
        "updated_at": now,
        "collected_by": user["username"]
    }
    
    await db.invoices.update_one({"id": inv_id}, {"$set": updates})
    
    # ── Trigger After-Paid Action (Enable MikroTik dll) ──
    from routers.billing import _after_paid_actions
    try:
        mt_msg = await _after_paid_actions(inv_id, db)
    except Exception as e:
        logger.error(f"[Collector] After-paid failed: {e}")
        mt_msg = ""
        
    # TODO: Bisa tambahkan fungsi kirim WA Kuitansi dari sini (jika diaktifkan)
    
    return {"ok": True, "message": f"Tagihan berhasil ditandai Lunas. {mt_msg}"}

@router.post("/invoices/{inv_id}/note")
async def add_field_note(inv_id: str, data: NoteRequest, user=Depends(get_current_collector)):
    """Kolektor menambahkan catatan (misal: janji bayar besok, rumah kosong)."""
    db = get_db()
    inv = await db.invoices.find_one({"id": inv_id})
    if not inv:
        raise HTTPException(404, "Invoice tidak ditemukan")
        
    now = datetime.now(timezone.utc).isoformat()
    new_note = f"[{now[:16]} - Kolektor {user['username']}] {data.notes}"
    admin_note = inv.get("admin_notes", "")
    combined = f"{admin_note}\n{new_note}".strip()
    
    await db.invoices.update_one(
        {"id": inv_id},
        {"$set": {"admin_notes": combined, "updated_at": now}}
    )
    
    return {"ok": True, "message": "Catatan berhasil ditambahkan"}

@router.get("/summary")
async def get_daily_summary(user=Depends(get_current_collector)):
    """Menampilkan total tagihan yang berhasil ditarik hari ini oleh kolektor ini."""
    db = get_db()
    today_str = date.today().isoformat()
    
    query = {
        "collected_by": user["username"],
        "status": "paid",
        "paid_at": {"$regex": f"^{today_str}"}
    }
    
    if user.get("role") in ["super_admin", "administrator"]:
        query.pop("collected_by") # Admin bisa melihat semua
        
    invoices = await db.invoices.find(query, {"total": 1, "payment_method": 1}).to_list(1000)
    
    total_cash = 0
    total_transfer = 0
    
    for inv in invoices:
        amount = inv.get("total", 0)
        if inv.get("payment_method") == "cash":
            total_cash += amount
        else:
            total_transfer += amount
            
    return {
        "ok": True, 
        "data": {
            "date": today_str,
            "count": len(invoices),
            "total_cash": total_cash,
            "total_transfer": total_transfer,
            "grand_total": total_cash + total_transfer
        }
    }
