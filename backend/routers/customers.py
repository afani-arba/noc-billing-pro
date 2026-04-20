"""
Customers router: manage pelanggan PPPoE/Hotspot untuk billing.
Import otomatis dari MikroTik, atau tambah manual.
"""
import uuid
import csv
import io
import random
import string
from datetime import datetime, timezone
from fastapi import APIRouter, HTTPException, Depends, Query, UploadFile, File, BackgroundTasks
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel
from typing import Optional
from core.db import get_db
from core.auth import (
    get_current_user, require_admin, require_write,
    check_device_access, get_user_allowed_devices
)
from mikrotik_api import get_api_client

router = APIRouter(prefix="/customers", tags=["customers"])


def _now():
    return datetime.now(timezone.utc).isoformat()


def _generate_client_id() -> str:
    """Generate 10 digit unique client ID"""
    return ''.join(random.choices(string.digits, k=10))


# ── Models ────────────────────────────────────────────────────────────────────

class CustomerCreate(BaseModel):
    name: str
    phone: str = ""
    address: str = ""
    service_type: str = "pppoe"          # Hanya pppoe
    username: str                         # username di MikroTik
    device_id: str                        # MikroTik device
    package_id: str = ""
    due_day: int = 10                     # tanggal jatuh tempo tiap bulan
    billing_type: str = "postpaid"        # "prepaid" | "postpaid"
    active: bool = True
    password: Optional[str] = None        # Jika diisi, otomatis terbuat di MikroTik
    installation_fee: int = 0
    payment_status: str = "belum_bayar"   # "sudah_bayar" | "belum_bayar"
    payment_method: str = "transfer"      # "cash" | "transfer"
    auth_method: str = "local"            # "local" | "radius"


class CustomerUpdate(BaseModel):
    name: Optional[str] = None
    username: Optional[str] = None
    phone: Optional[str] = None
    address: Optional[str] = None
    package_id: Optional[str] = None
    due_day: Optional[int] = None
    billing_type: Optional[str] = None
    active: Optional[bool] = None
    auth_method: Optional[str] = None
    password: Optional[str] = None   # Update password (RADIUS: simpan di DB; Local: update MikroTik)
    boost_rate_limit: Optional[str] = None
    boost_duration_hours: Optional[int] = None

class CustomerBulkUpdate(BaseModel):
    customer_ids: list[str]
    package_id: str


class CustomerBulkDelete(BaseModel):
    customer_ids: list[str]
    delete_invoices: bool = True  # hapus invoice terkait juga

import httpx
import logging
logger = logging.getLogger(__name__)

async def _bg_send_customer_greeting(customer: dict, invoice_total: int = 0, package_name: str = ""):
    db = get_db()
    # Gunakan setting dari billing untuk WA dengan dukungan multi-cabang
    dev_id = customer.get("device_id")
    settings = None
    if dev_id and dev_id != "GLOBAL":
        settings = await db.billing_settings.find_one({"device_id": dev_id}, {"_id": 0})
    if not settings:
        settings = await db.billing_settings.find_one({"$or": [{"device_id": "GLOBAL"}, {"device_id": {"$exists": False}}]}, {"_id": 0}) or {}
        
    wa_type = settings.get("wa_gateway_type", "fonnte")
    url = settings.get("wa_api_url", "https://api.fonnte.com/send")
    token = settings.get("wa_token", "")

    if not url or not token:
        return

    phone = customer.get("phone", "")
    if not phone:
        return

    name = customer.get("name", "")
    username = customer.get("username", "")
    client_id = customer.get("client_id", "")
    due_day = customer.get("due_day", 10)
    
    if not package_name and customer.get("package_id"):
        pkg = await db.billing_packages.find_one({"id": customer.get("package_id")})
        if pkg:
            package_name = pkg.get("name", "")
            if not invoice_total:
                invoice_total = pkg.get("price", 0)
    
    formatted_total = f"Rp {invoice_total:,}".replace(',', '.')

    # Ambil template kustom atau gunakan default
    template = settings.get("wa_template_new_customer", "")
    if template:
        msg = template.replace("{customer_name}", name)\
                      .replace("{username}", username)\
                      .replace("{client_id}", client_id)\
                      .replace("{package_name}", package_name)\
                      .replace("{total}", formatted_total)\
                      .replace("{due_day}", str(due_day))\
                      .replace("{phone}", phone)
    else:
        msg = f"Halo *{name}*,\n\nTerima kasih telah bergabung! Layanan internet Anda dengan username *{username}* telah AKTIF.\n\nSimpan pesan ini jika butuh bantuan teknis. Selamat menggunakan layanan dari kami."
    
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            if wa_type == "fonnte":
                await client.post(url, headers={"Authorization": token}, data={"target": phone, "message": msg, "countryCode": "62"})
            elif wa_type == "wablas":
                await client.post(url, headers={"Authorization": token}, json={"phone": phone, "message": msg})
            else:
                await client.post(url, headers={"Authorization": token}, json={"phone": phone, "message": msg})
    except Exception as e:
        logger.error(f"Gagal kirim WA sambutan ke pelanggan: {e}")

# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.get("")
async def list_customers(
    search: str = Query(""),
    service_type: str = Query(""),
    active: Optional[bool] = Query(None),
    device_id: str = Query(""),
    user=Depends(get_current_user),
):
    db = get_db()
    q = {}
    if service_type:
        q["service_type"] = service_type
    if active is not None:
        q["active"] = active

    # ── RBAC: filter berdasarkan allowed_devices user ──────────────────────
    scope = get_user_allowed_devices(user)  # None = admin (semua), [] = tidak ada akses
    if scope is None:
        # Admin: gunakan device_id dari query param jika ada
        if device_id:
            q["device_id"] = device_id
    else:
        # Non-admin: batasi ke device yang diizinkan
        allowed = scope
        if device_id:
            # Filter lebih lanjut ke device tertentu jika ada dalam scope
            allowed = [d for d in scope if d == device_id]
        if not allowed:
            return []
        q["device_id"] = {"$in": allowed}

    cursor = db.customers.find(q, {"_id": 0})
    results = await cursor.to_list(length=1000)

    if search:
        s = search.lower()
        results = [c for c in results if (
            s in c.get("name", "").lower()
            or s in c.get("username", "").lower()
            or s in c.get("phone", "").lower()
        )]
    return results


@router.get("/{customer_id}")
async def get_customer(customer_id: str, user=Depends(get_current_user)):
    db = get_db()
    c = await db.customers.find_one({"id": customer_id}, {"_id": 0})
    if not c:
        raise HTTPException(404, "Customer tidak ditemukan")
    return c


@router.post("", status_code=201)
async def create_customer(data: CustomerCreate, background_tasks: BackgroundTasks, user=Depends(require_write)):
    db = get_db()

    # ── RBAC: Cek hak akses user ke device yang dipilih ──────────────────
    if not check_device_access(user, data.device_id):
        raise HTTPException(403, "Anda tidak memiliki hak akses untuk menambahkan pelanggan ke router ini")

    # Cek duplicate username+device
    existing = await db.customers.find_one(
        {"username": data.username, "device_id": data.device_id}
    )
    if existing:
        raise HTTPException(409, f"Username '{data.username}' sudah terdaftar di device ini")

    mt_device = await db.devices.find_one({"id": data.device_id}, {"_id": 0})
    if not mt_device:
        raise HTTPException(404, "MikroTik device tidak ditemukan")

    pkg = None
    profile_name = ""
    if data.package_id:
        pkg = await db.billing_packages.find_one({"id": data.package_id}, {"_id": 0})
        if pkg:
            profile_name = pkg.get("profile_name", "") or pkg.get("name", "")

    # 1. Provision to MikroTik if Password is provided
    if data.password and data.auth_method != "radius":
        try:
            mt = get_api_client(mt_device)
            is_disabled = (data.billing_type == "prepaid" and data.payment_status == "belum_bayar")
            secret_data = {
                "name": data.username,
                "password": data.password,
                "service": "ppp",
                "disabled": "yes" if is_disabled else "no",
            }
            if profile_name:
                secret_data["profile"] = profile_name
            if data.name:
                secret_data["comment"] = data.name
            await mt.create_pppoe_secret(secret_data)
        except Exception as e:
            raise HTTPException(503, f"Gagal membuat user di MikroTik: {e}")

    # 2. Insert Customer directly
    customer_id = str(uuid.uuid4())
    client_id = _generate_client_id()
    doc = {
        "id": customer_id,
        "client_id": client_id,
        "name": data.name,
        "phone": data.phone,
        "address": data.address,
        "service_type": "pppoe", # Dikunci khusus untuk billing pppoe
        "username": data.username,
        "device_id": data.device_id,
        "package_id": data.package_id,
        "due_day": data.due_day,
        "billing_type": data.billing_type,
        "active": data.active,
        "auth_method": data.auth_method,
        "password": data.password,
        "start_date": _now(),
        "created_at": _now(),
        "profile": profile_name,
        "created_by": user.get("username", "") if isinstance(user, dict) else getattr(user, "username", ""),
    }
    await db.customers.insert_one(doc)

    # 3. Create Initial Invoice If Necessary (ZTP Behavior)
    if data.package_id or data.installation_fee > 0:
        try:
            from datetime import date, datetime
            def _inv_num(seq: int) -> str:
                d = date.today()
                return f"INV-{d.year}-{d.month:02d}-{seq:04d}"

            today = date.today()
            period_start = today.isoformat()
            
            from calendar import monthrange
            _, last_day = monthrange(today.year, today.month)
            period_end = f"{today.year}-{today.month:02d}-{last_day:02d}"
            due_day_safe = min(data.due_day, last_day)
            due_date = f"{today.year}-{today.month:02d}-{due_day_safe:02d}"
            
            period_prefix = f"{today.year}-{today.month:02d}"
            count = await db.invoices.count_documents(
                {"period_start": {"$regex": f"^{period_prefix}"}}
            )
            
            pkg_price = pkg.get("price", 0) if pkg else 0
            amount = pkg_price + data.installation_fee
            
            unique_code = 0
            if data.payment_method == "transfer":
                import random
                unique_code = random.randint(1, 999)
            
            total = amount + unique_code
            
            is_paid = (data.payment_status == "sudah_bayar")
            
            inv_doc = {
                "id": str(uuid.uuid4()),
                "invoice_number": _inv_num(count + 1),
                "customer_id": customer_id,
                "customer_name": data.name,
                "customer_username": data.username,
                "package_id": data.package_id,
                "package_name": pkg.get("name", "") if pkg else "",
                "amount": amount,
                "discount": 0,
                "unique_code": unique_code,
                "total": total,
                "period_start": period_start,
                "period_end": period_end,
                "due_date": due_date,
                "status": "paid" if is_paid else "unpaid",
                "notes": f"Tagihan Pertama. Paket: {pkg.get('name', '—')} (Rp {pkg_price}), Biaya Pasang: Rp {data.installation_fee}",
                "paid_at": _now() if is_paid else None,
                "payment_method": "cash" if is_paid else None,
                "created_at": _now(),
            }
            await db.invoices.insert_one(inv_doc)
        except Exception as e:
            logger.error(f"Failed creating initial invoice: {e}")

    doc.pop("_id", None)
    
    # ── Kirim Pesan Sambutan ke WA pelanggan (jika ada nomor HP) ──
    if data.phone:
        # Calculate total if not set, or pass defaults
        pkg_name = pkg.get("name", "") if pkg else ""
        pkg_price = pkg.get("price", 0) if pkg else 0
        total_amount = pkg_price + data.installation_fee
        background_tasks.add_task(_bg_send_customer_greeting, doc, total_amount, pkg_name)

    return doc


@router.put("/bulk-update")
async def bulk_update_customers(data: CustomerBulkUpdate, user=Depends(require_write)):
    """Update paket secara massal. Harus didaftarkan SEBELUM /{customer_id} agar tidak ditangkap sebagai ID."""
    db = get_db()

    if not data.customer_ids:
        raise HTTPException(400, "Tidak ada pelanggan yang dipilih")

    # Validasi package_id
    if data.package_id:
        pkg = await db.billing_packages.find_one({"id": data.package_id})
        if not pkg:
            raise HTTPException(404, "Paket berlangganan tidak ditemukan")

    # Update massal
    result = await db.customers.update_many(
        {"id": {"$in": data.customer_ids}},
        {"$set": {"package_id": data.package_id}}
    )

    return {
        "message": f"Berhasil mengupdate paket untuk {result.modified_count} pelanggan",
        "modified_count": result.modified_count
    }


@router.post("/bulk-delete")
async def bulk_delete_customers(data: CustomerBulkDelete, user=Depends(require_admin)):
    """Hapus massal pelanggan dan (opsional) semua invoice terkait."""
    db = get_db()

    if not data.customer_ids:
        raise HTTPException(400, "Tidak ada pelanggan yang dipilih")

    deleted_invoices = 0
    if data.delete_invoices:
        inv_result = await db.invoices.delete_many({"customer_id": {"$in": data.customer_ids}})
        deleted_invoices = inv_result.deleted_count

    cust_result = await db.customers.delete_many({"id": {"$in": data.customer_ids}})

    return {
        "message": f"Berhasil menghapus {cust_result.deleted_count} pelanggan dan {deleted_invoices} invoice terkait",
        "deleted_customers": cust_result.deleted_count,
        "deleted_invoices": deleted_invoices,
    }


@router.post("/{customer_id}/unsubscribe")
async def unsubscribe_customer(customer_id: str, user=Depends(require_write)):
    """
    Berhentikan langganan pelanggan:
    1. Disable user PPPoE di MikroTik
    2. Hapus (kick) active session PPPoE
    3. Set customer.active = False di database
    """
    db = get_db()
    customer = await db.customers.find_one({"id": customer_id}, {"_id": 0})
    if not customer:
        raise HTTPException(404, "Customer tidak ditemukan")

    device = await db.devices.find_one({"id": customer.get("device_id", "")}, {"_id": 0})
    if not device:
        raise HTTPException(404, "Device MikroTik tidak ditemukan untuk pelanggan ini")

    username = customer.get("username", "")
    svc = customer.get("service_type", "pppoe")

    mt = get_api_client(device)
    result_msgs = []

    # Langkah 1: Disable user di MikroTik
    try:
        if svc == "pppoe" or svc == "hotspot":  # Fallback gracefully for legacy hotspot data
            await mt.disable_pppoe_user(username)
        result_msgs.append(f"User '{username}' berhasil di-disable")
    except Exception as e:
        result_msgs.append(f"Gagal disable user: {e}")

    # Langkah 2: Hapus active session
    try:
        removed = await mt.remove_pppoe_active_session(username)
        if removed > 0:
            result_msgs.append(f"{removed} active session dihapus")
        else:
            result_msgs.append("Tidak ada active session (mungkin sudah offline)")
    except Exception as e:
        result_msgs.append(f"Gagal hapus active session: {e}")

    # Langkah 3: Set inactive di database
    await db.customers.update_one({"id": customer_id}, {"$set": {"active": False}})
    result_msgs.append("Status pelanggan diubah menjadi Non-aktif")

    return {
        "message": "Proses berhenti berlangganan selesai",
        "details": result_msgs,
        "username": username,
    }


@router.put("/{customer_id}")
async def update_customer(customer_id: str, data: CustomerUpdate, background_tasks: BackgroundTasks, user=Depends(require_write)):
    db = get_db()
    customer = await db.customers.find_one({"id": customer_id}, {"_id": 0})
    if not customer:
        raise HTTPException(404, "Customer tidak ditemukan")

    # ── RBAC: cek apakah user memiliki hak akses ke device customer ini ───
    if not check_device_access(user, customer.get("device_id", "")):
        raise HTTPException(403, "Anda tidak memiliki hak akses untuk mengubah pelanggan pada router ini")

    update = {k: v for k, v in data.dict().items() if v is not None}
    if not update:
        raise HTTPException(400, "Tidak ada data yang diupdate")

    # ── Booster Handling ──
    boost_rate = update.pop("boost_rate_limit", None)
    boost_hours = update.pop("boost_duration_hours", None)
    trigger_sync = False

    if boost_rate is not None:
        if boost_rate.strip() == "":
            # Matikan booster — kembali ke rate normal
            update["booster_active"] = False
            update["current_rate_limit"] = None   # Force re-evaluasi ke normal
            update["boost_rate_limit"] = ""
            trigger_sync = True
            logger.info(f"[Booster] Admin mematikan booster untuk {customer.get('username')}")
        else:
            # Aktifkan booster — cek mutual exclusivity dengan Night Mode
            pkg_id = update.get("package_id") or customer.get("package_id", "")
            if pkg_id:
                pkg_check = await db.billing_packages.find_one({"id": pkg_id}, {"_id": 0})
            else:
                pkg_check = None

            if pkg_check and pkg_check.get("day_night_enabled"):
                from datetime import datetime as _dt
                now_time_str = _dt.now().strftime("%H:%M")
                n_start = pkg_check.get("night_start", "22:00")
                n_end   = pkg_check.get("night_end",   "06:00")
                is_night = False
                if n_start > n_end:
                    is_night = now_time_str >= n_start or now_time_str < n_end
                else:
                    is_night = n_start <= now_time_str < n_end
                if is_night:
                    raise HTTPException(400,
                        f"Night Mode sedang aktif ({n_start}\u2013{n_end}). "
                        "Booster tidak dapat dijalankan bersamaan dengan Night Mode."
                    )

            update["booster_active"] = True
            update["boost_rate_limit"] = boost_rate   # Simpan di customer untuk scheduler
            dur = boost_hours if boost_hours and boost_hours > 0 else 1
            from datetime import timedelta
            exp_at = (datetime.now(timezone.utc) + timedelta(hours=dur)).isoformat()
            update["booster_expires_at"] = exp_at
            update["current_rate_limit"] = None        # Force re-evaluasi
            trigger_sync = True
            logger.info(f"[Booster] Admin mengaktifkan booster {boost_rate} ({dur}j) untuk {customer.get('username')}")

    # Ambil field khusus yang perlu intervensi MikroTik
    new_password = update.pop("password", None)
    new_username = update.get("username", None)
    
    auth_method = update.get("auth_method") or customer.get("auth_method", "local")
    old_username = customer.get("username", "")
    
    # 1. Update Password di MongoDB
    if new_password:
        update["password"] = new_password
        
    # 2. Update di MikroTik jika mode local
    if auth_method != "radius" and (new_password or (new_username and new_username != old_username)):
        device = await db.devices.find_one({"id": customer.get("device_id", "")}, {"_id": 0})
        if device:
            try:
                mt = get_api_client(device)
                secrets = await mt.list_pppoe_secrets()
                mt_id = None
                for s in secrets:
                    if s.get("name") == old_username:
                        mt_id = s.get(".id") or s.get("id")
                        break
                
                if mt_id:
                    mt_update = {}
                    if new_username and new_username != old_username:
                        mt_update["name"] = new_username
                    if new_password:
                        mt_update["password"] = new_password
                    
                    if mt_update:
                        await mt.update_pppoe_secret(mt_id, mt_update)
            except Exception as e:
                import logging
                logging.getLogger(__name__).warning(f"[UpdateCustomer] Gagal sync MikroTik untuk '{old_username}': {e}")

    result = await db.customers.update_one({"id": customer_id}, {"$set": update})
    if result.matched_count == 0:
        raise HTTPException(404, "Customer tidak ditemukan")

    if trigger_sync:
        async def _trigger_coa(cust_id: str):
            try:
                from services.bandwidth_scheduler import run_day_night_and_booster_sync
                # Targeted: hanya sync pelanggan ini, tidak mempengaruhi lain
                await run_day_night_and_booster_sync(customer_id=cust_id)
            except Exception as e:
                logger.error(f"[Booster] Gagal sync CoA: {e}")
        background_tasks.add_task(_trigger_coa, customer_id)

    return {"message": "Customer berhasil diupdate"}


@router.delete("/{customer_id}")
async def delete_customer(customer_id: str, user=Depends(require_admin)):
    db = get_db()
    customer = await db.customers.find_one({"id": customer_id}, {"_id": 0})
    if not customer:
        raise HTTPException(404, "Customer tidak ditemukan")

    # ── RBAC: admin non-super hanya bisa hapus pelanggan dari routernya sendiri ─
    if not check_device_access(user, customer.get("device_id", "")):
        raise HTTPException(403, "Anda tidak memiliki hak akses untuk menghapus pelanggan pada router ini")

    result = await db.customers.delete_one({"id": customer_id})
    if result.deleted_count == 0:
        raise HTTPException(404, "Customer tidak ditemukan")
    return {"message": "Customer dihapus"}


# ── Import dari MikroTik ──────────────────────────────────────────────────────

@router.post("/import/pppoe")
async def import_from_pppoe(
    device_id: str,
    due_day: int = 10,
    user=Depends(require_write),
):
    """
    Import PPPoE secrets dari MikroTik sebagai customers.
    Skip yang sudah ada.
    """
    db = get_db()
    device = await db.devices.find_one({"id": device_id}, {"_id": 0})
    if not device:
        raise HTTPException(404, "Device tidak ditemukan")

    try:
        mt = get_api_client(device)
        secrets = await mt.list_pppoe_secrets()
    except Exception as e:
        raise HTTPException(503, f"Gagal terhubung ke MikroTik: {e}")

    imported = 0
    skipped = 0

    # Buat peta profile_name -> package_id dari billing_packages
    all_packages = await db.billing_packages.find({}, {"_id": 0, "id": 1, "profile_name": 1, "source_device_id": 1}).to_list(500)
    # Prioritaskan paket dari device yang sama, fallback ke paket manapun
    profile_to_pkg = {}
    for pkg in all_packages:
        pn = pkg.get("profile_name", "")
        if not pn:
            continue
        # Paket dari device yang sama punya prioritas lebih tinggi
        if pkg.get("source_device_id") == device_id or pn not in profile_to_pkg:
            profile_to_pkg[pn] = pkg["id"]

    for secret in secrets:
        username = secret.get("name", "")
        if not username:
            continue
        existing = await db.customers.find_one(
            {"username": username, "device_id": device_id}
        )
        if existing:
            skipped += 1
            continue

        # Gunakan comment MikroTik sebagai nama pelanggan jika ada
        comment = secret.get("comment", "")
        name = comment if comment else username
        profile = secret.get("profile", "")

        # MikroTik mengembalikan password di field "password" pada PPPoE secret
        mt_password = secret.get("password", "") or None

        doc = {
            "id": str(uuid.uuid4()),
            "client_id": _generate_client_id(),
            "name": name,
            "phone": "",
            "address": "",
            "service_type": "pppoe",
            "username": username,
            "device_id": device_id,
            "package_id": profile_to_pkg.get(profile, ""),  # Auto-assign jika profile cocok
            "due_day": due_day,
            "billing_type": "postpaid",
            "active": secret.get("disabled", "false") != "true",
            "created_at": _now(),
            "profile": profile,
            "password": mt_password,      # Simpan password dari MikroTik jika tersedia
            "auth_method": "local",
        }
        await db.customers.insert_one(doc)
        imported += 1

    return {
        "message": f"Import selesai: {imported} baru, {skipped} sudah ada",
        "imported": imported,
        "skipped": skipped,
    }


@router.get("/template.csv")
async def download_csv_template():
    """Download template file CSV untuk import pelanggan"""
    # Kolom: name, phone, address, service_type, username, device_id, profile, due_day, active
    content = "name,phone,address,service_type,username,device_id,profile,due_day,active\n"
    content += "Budi Santoso,08123456789,Jl. Merdeka No 1,pppoe,budi_net,router_pusat,Paket 10M,10,true\n"
    return PlainTextResponse(
        content,
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=template_import_pelanggan.csv"}
    )


@router.post("/import-csv")
async def import_csv_customers(
    file: UploadFile = File(...),
    user=Depends(require_write)
):
    """Import pelanggan dari file CSV hasil export Excel."""
    db = get_db()
    content = await file.read()
    try:
        text = content.decode("utf-8-sig")  # sig for BOM created by Excel
    except UnicodeDecodeError:
        text = content.decode("latin-1")
        
    reader = csv.DictReader(io.StringIO(text))
    if not reader.fieldnames:
        raise HTTPException(400, "File CSV kosong atau format tidak valid")
        
    required_cols = ["username", "device_id"]
    for c in required_cols:
        if c not in reader.fieldnames:
            raise HTTPException(400, f"Kolom wajib '{c}' tidak ditemukan di CSV")
            
    # Buat peta profile_name -> package_id
    all_packages = await db.billing_packages.find({}, {"_id": 0, "id": 1, "profile_name": 1}).to_list(1000)
    profile_to_pkg = {}
    for p in all_packages:
        pn = p.get("profile_name", "")
        if pn:
            profile_to_pkg[pn] = p["id"]
            
    imported = 0
    skipped = 0
    errors = []
    
    for i, row in enumerate(reader):
        username = row.get("username", "").strip()
        device_id = row.get("device_id", "").strip()
        name = row.get("name", "").strip() or username
        
        if not username or not device_id:
            skipped += 1
            errors.append(f"Baris {i+2}: dilewati karena username atau device_id kosong.")
            continue
            
        existing = await db.customers.find_one({"username": username, "device_id": device_id})
        if existing:
            skipped += 1
            continue
            
        profile = row.get("profile", "").strip()
        
        due_day_str = row.get("due_day", "10").strip()
        try: 
            due_day = int(due_day_str)
        except ValueError: 
            due_day = 10
            
        active_str = str(row.get("active", "true")).strip().lower()
        active = active_str in ["true", "1", "yes", "ya", "y"]
        service_type = "pppoe" # Force PPPoE for monthly customers
            
        csv_password = row.get("password", "").strip() or None

        doc = {
            "id": str(uuid.uuid4()),
            "client_id": _generate_client_id(),
            "name": name,
            "phone": row.get("phone", "").strip(),
            "address": row.get("address", "").strip(),
            "service_type": service_type,
            "username": username,
            "device_id": device_id,
            "package_id": profile_to_pkg.get(profile, ""),
            "due_day": due_day,
            "billing_type": "postpaid",
            "active": active,
            "created_at": _now(),
            "profile": profile,
            "password": csv_password,     # Simpan password dari CSV jika ada
            "auth_method": "local",
        }
        await db.customers.insert_one(doc)
        imported += 1
        
    return {
        "message": f"Import CSV selesai: {imported} pelanggan baru ditambahkan, {skipped} dilewati",
        "imported": imported,
        "skipped": skipped,
        "errors": errors
    }

