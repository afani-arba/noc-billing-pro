"""
WA Customer Service Router
Menerima log percakapan dari n8n dan menyediakan API untuk monitoring & reply manual.
"""
import logging
import uuid
import random
import re
from datetime import datetime, timezone, date, timedelta
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Header
from pydantic import BaseModel
from bson import ObjectId
from core.db import get_db
from core.auth import require_admin
from services.notification_service import send_whatsapp

router = APIRouter(prefix="/wa-chat", tags=["wa_customer_service"])
logger = logging.getLogger(__name__)


# ── Helpers ──────────────────────────────────────────────────────────────────

def _obj_to_str(doc: dict) -> dict:
    if doc and "_id" in doc:
        doc["_id"] = str(doc["_id"])
    return doc


async def _get_fonnte_token() -> str:
    db = get_db()
    settings = await db.notification_settings.find_one({}, {"_id": 0, "fonnte_token": 1})
    return (settings or {}).get("fonnte_token", "")


async def _verify_api_key(x_api_key: Optional[str] = Header(None)):
    if not x_api_key:
        raise HTTPException(status_code=401, detail="X-Api-Key header missing")
    db = get_db()
    settings = await db.notification_settings.find_one({}, {"_id": 0, "fonnte_token": 1})
    stored_token = (settings or {}).get("fonnte_token", "")
    if not stored_token or x_api_key != stored_token:
        raise HTTPException(status_code=401, detail="Invalid API key")
    return x_api_key


# ── Pydantic Models ──────────────────────────────────────────────────────────

class ConversationLog(BaseModel):
    sender: str
    sender_name: str = ""
    message: str
    response: str
    device: Optional[str] = ""


class StatusUpdate(BaseModel):
    status: str
    notes: Optional[str] = ""


class ManualReply(BaseModel):
    sender: str
    message: str


class BuyVoucherRequest(BaseModel):
    phone: str
    name: str = ""
    package_id: str


# ── Endpoints ────────────────────────────────────────────────────────────────

@router.post("/log", summary="Log percakapan dari n8n")
async def log_conversation(data: ConversationLog, api_key: str = Depends(_verify_api_key)):
    db = get_db()
    doc = {
        "sender": data.sender,
        "sender_name": data.sender_name or data.sender,
        "message": data.message,
        "response": data.response,
        "device": data.device,
        "status": "pending",
        "notes": "",
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    result = await db.wa_conversations.insert_one(doc)
    return {"success": True, "id": str(result.inserted_id)}


@router.get("/conversations", summary="Daftar percakapan per pelanggan")
async def list_conversations(status: Optional[str] = None, user=Depends(require_admin)):
    db = get_db()
    match = {}
    if status:
        match["status"] = status

    pipeline = [
        {"$match": match},
        {"$sort": {"timestamp": -1}},
        {"$group": {
            "_id": "$sender",
            "sender_name": {"$first": "$sender_name"},
            "last_message": {"$first": "$message"},
            "last_response": {"$first": "$response"},
            "last_timestamp": {"$first": "$timestamp"},
            "total_messages": {"$sum": 1},
            "pending_count": {"$sum": {"$cond": [{"$eq": ["$status", "pending"]}, 1, 0]}},
            "has_escalated": {"$max": {"$cond": [{"$eq": ["$status", "escalated"]}, 1, 0]}},
            "thread_status": {"$first": "$status"},
        }},
        {"$sort": {"last_timestamp": -1}},
    ]

    results = []
    async for doc in db.wa_conversations.aggregate(pipeline):
        results.append({
            "sender": doc["_id"],
            "sender_name": doc.get("sender_name", doc["_id"]),
            "last_message": doc.get("last_message", ""),
            "last_response": doc.get("last_response", ""),
            "last_timestamp": doc.get("last_timestamp", ""),
            "total_messages": doc.get("total_messages", 0),
            "pending_count": doc.get("pending_count", 0),
            "has_escalated": bool(doc.get("has_escalated", 0)),
            "thread_status": doc.get("thread_status", "pending"),
        })
    return results


@router.get("/conversations/{sender}", summary="Riwayat percakapan 1 pelanggan")
async def get_conversation_history(sender: str, user=Depends(require_admin)):
    db = get_db()
    cursor = db.wa_conversations.find(
        {"sender": sender},
        {"_id": 1, "sender": 1, "sender_name": 1, "message": 1,
         "response": 1, "status": 1, "notes": 1, "timestamp": 1}
    ).sort("timestamp", 1)
    messages = []
    async for doc in cursor:
        messages.append(_obj_to_str(doc))
    return messages


@router.put("/conversations/{conv_id}/status")
async def update_status(conv_id: str, data: StatusUpdate, user=Depends(require_admin)):
    if data.status not in ("pending", "resolved", "escalated"):
        raise HTTPException(400, "Status harus: pending | resolved | escalated")
    db = get_db()
    update_doc = {"status": data.status}
    if data.notes is not None:
        update_doc["notes"] = data.notes
    result = await db.wa_conversations.update_one(
        {"_id": ObjectId(conv_id)}, {"$set": update_doc}
    )
    if result.matched_count == 0:
        raise HTTPException(404, "Conversation tidak ditemukan")
    return {"success": True, "message": f"Status diupdate ke {data.status}"}


@router.put("/conversations/sender/{sender}/status")
async def update_sender_status(sender: str, data: StatusUpdate, user=Depends(require_admin)):
    if data.status not in ("pending", "resolved", "escalated"):
        raise HTTPException(400, "Status harus: pending | resolved | escalated")
    db = get_db()
    update_doc = {"status": data.status}
    if data.notes is not None:
        update_doc["notes"] = data.notes
    await db.wa_conversations.update_many({"sender": sender}, {"$set": update_doc})
    return {"success": True, "message": f"Semua pesan dari {sender} diupdate ke {data.status}"}


@router.post("/reply", summary="Kirim balasan manual dari admin")
async def manual_reply(data: ManualReply, user=Depends(require_admin)):
    token = await _get_fonnte_token()
    if not token:
        raise HTTPException(400, "Fonnte token belum dikonfigurasi")
    ok = await send_whatsapp(data.sender, data.message, token)
    if not ok:
        raise HTTPException(503, "Gagal mengirim pesan via Fonnte")
    db = get_db()
    await db.wa_conversations.insert_one({
        "sender": data.sender,
        "sender_name": "Admin (Manual)",
        "message": f"[ADMIN REPLY]: {data.message}",
        "response": data.message,
        "device": "",
        "status": "resolved",
        "notes": f"Manual reply from admin",
        "timestamp": datetime.now(timezone.utc).isoformat(),
    })
    return {"success": True, "message": f"Pesan berhasil dikirim ke {data.sender}"}


@router.delete("/conversations/{conv_id}")
async def delete_conversation(conv_id: str, user=Depends(require_admin)):
    db = get_db()
    result = await db.wa_conversations.delete_one({"_id": ObjectId(conv_id)})
    if result.deleted_count == 0:
        raise HTTPException(404, "Conversation tidak ditemukan")
    return {"success": True}


@router.delete("/conversations/sender/{sender}")
async def delete_sender_conversations(sender: str, user=Depends(require_admin)):
    db = get_db()
    result = await db.wa_conversations.delete_many({"sender": sender})
    return {"success": True, "deleted": result.deleted_count}


@router.get("/stats")
async def get_stats(user=Depends(require_admin)):
    db = get_db()
    today_start = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0).isoformat()
    return {
        "total": await db.wa_conversations.count_documents({}),
        "pending": await db.wa_conversations.count_documents({"status": "pending"}),
        "resolved": await db.wa_conversations.count_documents({"status": "resolved"}),
        "escalated": await db.wa_conversations.count_documents({"status": "escalated"}),
        "today_total": await db.wa_conversations.count_documents({"timestamp": {"$gte": today_start}}),
        "unique_customers": len(await db.wa_conversations.distinct("sender")),
    }


# ── AI CS: Buy Voucher ───────────────────────────────────────────────────────

@router.post("/buy-voucher", summary="AI otomatis membuat tagihan hotspot untuk pengirim WA")
async def buy_voucher_from_ai(data: BuyVoucherRequest):
    """
    DESAIN PENTING:
    - Invoice voucher WA TIDAK terikat ke collection 'customers' (PPPoE).
    - Nama & nomor HP disimpan LANGSUNG di dokumen hotspot_invoice.
    - Satu nomor HP bisa beli voucher meski sudah terdaftar sebagai pelanggan PPPoE.
    - Kode voucher di-pre-generate dan DIKIRIM OTOMATIS via WA setelah Moota konfirmasi bayar.
    """
    db = get_db()

    # 1. Normalisasi nomor telepon
    clean_phone = re.sub(r'\D', '', data.phone)
    if clean_phone.startswith('62'):
        clean_phone = '0' + clean_phone[2:]
    customer_name = data.name.strip() if data.name else f'Pelanggan {clean_phone[-4:]}'

    # 2. Cari paket
    pkg = await db.billing_packages.find_one({'id': data.package_id})
    if not pkg:
        pkg = await db.billing_packages.find_one({'name': {'$regex': data.package_id, '$options': 'i'}})
    if not pkg:
        raise HTTPException(status_code=404, detail=f'Paket "{data.package_id}" tidak ditemukan.')

    # 3. Anti-spam: cek tagihan pending — cari by PHONE langsung (bukan customer_id)
    unpaid = await db.hotspot_invoices.find_one({
        'customer_phone': clean_phone,
        'status': {'$in': ['unpaid', 'overdue']}
    })
    if unpaid:
        try:
            created_time = datetime.fromisoformat(unpaid['created_at'].replace('Z', '+00:00'))
            if created_time.tzinfo is None:
                created_time = created_time.replace(tzinfo=timezone.utc)
            age = datetime.now(timezone.utc) - created_time
        except Exception:
            age = timedelta(hours=2)

        if age < timedelta(hours=1):
            settings = await db.system_settings.find_one({'_id': 'company_profile'})
            bank_info = (settings or {}).get('bank_account', 'BCA 8520480189 a.n PT ARSYA BAROKAH ABADI')
            return {
                'success': True,
                'invoice_number': unpaid['invoice_number'],
                'package_name': unpaid.get('package_name', '-'),
                'total': unpaid['total'],
                'unique_code': unpaid.get('unique_code', 0),
                'bank_account': bank_info,
                'status': 'existing',
                'message': (
                    f'Kakak masih punya tagihan voucher BELUM DIBAYAR sebesar Rp {unpaid["total"]:,} '
                    f'(No. {unpaid["invoice_number"]}). '
                    f'Transfer tepat Rp {unpaid["total"]:,} ke: {bank_info}. '
                    f'Kode voucher dikirim otomatis setelah pembayaran terverifikasi.'
                )
            }
        else:
            await db.hotspot_invoices.delete_one({'_id': unpaid['_id']})
            logger.info(f'[AI CS] Tagihan voucher basi dihapus: {unpaid["invoice_number"]}')

    # 4. Hitung nomor invoice
    today = date.today()
    period_prefix = f'{today.year}-{today.month:02d}'
    count = await db.hotspot_invoices.count_documents({'period_start': {'$regex': f'^{period_prefix}'}})

    # 5. Kode unik Moota (1–500)
    unique_code = random.randint(1, 500)
    price = pkg.get('price', 0)
    total = price + unique_code
    due_date = (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat()
    invoice_number = f'VCH-{today.year}-{today.month:02d}-{(count + 1):04d}'

    # 6. Pre-generate kode voucher (dikirim ke pelanggan setelah bayar)
    chars = 'ABCDEFGHJKLMNPQRSTUVWXYZ23456789'
    vc_user = 'VC' + ''.join(random.choices(chars, k=6))
    vc_pass = vc_user

    # 7. Simpan invoice STANDALONE di hotspot_invoices
    invoice = {
        'id': str(uuid.uuid4()),
        'invoice_number': invoice_number,
        'customer_name': customer_name,       # Langsung di sini
        'customer_phone': clean_phone,         # Langsung di sini
        'customer_id': None,                   # SENGAJA None — tidak terikat PPPoE
        'package_id': pkg['id'],
        'package_name': pkg.get('name', '-'),
        'profile_name': pkg.get('profile_name') or pkg.get('profile') or 'default', 
        'uptime_limit': pkg.get('uptime_limit') or pkg.get('validity_seconds') or '',
        'validity': pkg.get('validity', ''),
        'amount': price,
        'discount': 0,
        'unique_code': unique_code,
        'total': total,
        'voucher_username': vc_user,           # Kode voucher — dikirim setelah bayar
        'voucher_password': vc_pass,
        'voucher_sent': False,
        'period_start': today.isoformat(),
        'period_end': today.isoformat(),
        'due_date': due_date,
        'status': 'unpaid',
        'payment_method': None,
        'source': 'ai_cs_wa',
        'notes': f'Pesanan WA — {customer_name} ({clean_phone})',
        'created_at': datetime.now(timezone.utc).isoformat(),
        'updated_at': datetime.now(timezone.utc).isoformat(),
    }
    await db.hotspot_invoices.insert_one(invoice)
    logger.info(f'[AI CS] {invoice_number} → {customer_name} ({clean_phone}) | Rp {total} | VC: {vc_user}/{vc_pass}')

    # 8. Rekening bank dari settings
    settings = await db.system_settings.find_one({'_id': 'company_profile'})
    bank_info = (settings or {}).get('bank_account', 'BCA 8520480189 a.n PT ARSYA BAROKAH ABADI')

    return {
        'success': True,
        'invoice_number': invoice_number,
        'package_name': pkg['name'],
        'total': total,
        'unique_code': unique_code,
        'bank_account': bank_info,
        'status': 'created',
        'message': (
            f'Tagihan voucher berhasil dibuat!\n'
            f'No. Invoice: *{invoice_number}*\n'
            f'Paket: {pkg["name"]}\n'
            f'Total Transfer: *Rp {total:,}* (sudah termasuk kode unik {unique_code})\n'
            f'Rekening: *{bank_info}*\n\n'
            f'PENTING: Transfer TEPAT *Rp {total:,}* dalam waktu *1 JAM*.\n'
            f'Kode voucher akan dikirim otomatis ke WhatsApp ini setelah pembayaran terverifikasi.'
        )
    }
