import os
import asyncio
import jwt
from datetime import datetime, timezone, timedelta
from fastapi import APIRouter, HTTPException, Depends, Request
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel
from typing import Optional

from core.db import get_db
from core.auth import JWT_SECRET

router = APIRouter(prefix="/client-portal", tags=["client_portal"])
security = HTTPBearer()

def normPhone(phone: str) -> str:
    # Normalize phone: extract only digits
    import re
    p = re.sub(r"\D", "", str(phone))
    if p.startswith("62"):
        return "0" + p[2:]
    return p

def create_client_token(customer_id: str, phone: str) -> str:
    # Use a separate environment variable for mobile portals, default to 365 days (525600 minutes)
    # so that customers are not constantly forced to login every 24 hours.
    expire_minutes = int(os.environ.get("CLIENT_TOKEN_EXPIRE_MINUTES", "525600"))
    return jwt.encode(
        {
            "sub": customer_id,
            "phone": phone,
            "role": "client",
            "exp": datetime.now(timezone.utc) + timedelta(minutes=expire_minutes),
        },
        JWT_SECRET,
        algorithm="HS256",
    )

async def get_current_client(credentials: HTTPAuthorizationCredentials = Depends(security)):
    db = get_db()
    try:
        payload = jwt.decode(credentials.credentials, JWT_SECRET, algorithms=["HS256"])
        if payload.get("role") != "client":
            raise HTTPException(403, "Invalid role")
        
        c = await db.customers.find_one({"id": payload["sub"]}, {"_id": 0})
        if not c:
            raise HTTPException(401, "Customer not found")
        return c
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token expired")
    except jwt.InvalidTokenError:
        raise HTTPException(401, "Invalid token")


class LoginRequest(BaseModel):
    customer_id: str
    phone: str

@router.post("/login")
async def portal_login(data: LoginRequest):
    db = get_db()
    c_id_input = data.customer_id.strip()
    phone_norm = normPhone(data.phone.strip())
    
    # Try to find by client_id (friendly format e.g. CUST-1001) first, then fallback to internal id
    customer = await db.customers.find_one({"client_id": c_id_input})
    if not customer:
        # Fallback: try exact match on internal UUID id field
        customer = await db.customers.find_one({"id": c_id_input})
    if not customer:
        raise HTTPException(401, "ID Pelanggan atau Nomor WhatsApp salah")
    
    db_phone = normPhone(customer.get("phone", ""))
    if db_phone != phone_norm:
        raise HTTPException(401, "ID Pelanggan atau Nomor WhatsApp salah")
    
    if not customer.get("active", True):
        raise HTTPException(403, "Akun diblokir/dinonaktifkan")
    
    # Use the internal id for token subject
    real_id = customer.get("id", c_id_input)
    token = create_client_token(real_id, db_phone)
    return {
        "ok": True,
        "token": token,
        "customer": {
            "id": customer.get("client_id") or real_id,
            "name": customer.get("name", "Pelanggan")
        }
    }

@router.get("/dashboard")
async def get_dashboard(customer=Depends(get_current_client)):
    db = get_db()
    from datetime import date
    from calendar import monthrange
    today = date.today()
    
    # Fetch unpaid invoices
    unpaid = await db.invoices.find({
        "customer_id": customer["id"],
        "status": {"$in": ["unpaid", "overdue"]}
    }).to_list(None)
    
    # Enrich unpaid invoices with days_overdue
    for u in unpaid:
        u.pop("_id", None)
        try:
            due = date.fromisoformat(str(u.get("due_date", "")).split("T")[0])
            u["days_overdue"] = max(0, (today - due).days)
        except Exception:
            u["days_overdue"] = 0
        
    pkg = {}
    if customer.get("package_id"):
        pkg_db = await db.billing_packages.find_one({"id": customer["package_id"]})
        if pkg_db:
            pkg = {
                "name": pkg_db.get("name"), 
                "price": pkg_db.get("price"),
                "fup_enabled": pkg_db.get("fup_enabled", False),
                "fup_limit_gb": pkg_db.get("fup_limit_gb", 0)
            }

    upcoming_invoice = None
    if not unpaid and pkg:
        due_day = customer.get("due_day", 10)
        m = today.month
        y = today.year
        if today.day >= due_day:
            m += 1
            if m > 12:
                m = 1
                y += 1
        _, last_day = monthrange(y, m)
        safe_due_day = min(due_day, last_day)
        upcoming_date = f"{y}-{m:02d}-{safe_due_day:02d}"
        due_obj = date.fromisoformat(upcoming_date)
        days_until_due = (due_obj - today).days
        
        upcoming_invoice = {
            "due_date": upcoming_date,
            "package_name": pkg.get("name", "Paket Internet"),
            "amount": pkg.get("price", 0),
            "days_until_due": days_until_due
        }

    settings = await db.settings.find_one({"id": "global"}) or {}
    raw_bank = settings.get("bank_account", "BCA 8520480189 a.n PT ARSYA BAROKAH ABADI")
    
    # Parsing string seperti "BCA 8520480189 a.n PT ARSYA BAROKAH ABADI"
    import re
    bank_name = "Bank"
    account_number = "-"
    account_name = "-"
    
    # Ekstrak rekening (kumpulan angka minimal 4 digit)
    acc_match = re.search(r'\d{4,}', raw_bank)
    if acc_match:
        account_number = acc_match.group()
        bank_name = raw_bank[:acc_match.start()].strip()
    
    # Ekstrak nama (setelah "a.n" atau "A.N")
    an_match = re.search(r'a\.?\s*n\.?', raw_bank, re.IGNORECASE)
    if an_match:
        account_name = raw_bank[an_match.end():].strip()
        # Jika belum dapat bank_name karena tidak ada spasi sblm angka, fallback
        if bank_name == "Bank" or bank_name == "":
            bank_name = raw_bank[:an_match.start()].replace(account_number, "").strip()

    ai_cfg = await db.system_settings.find_one({"_id": "ai_chat_config"}) or {}

    platform_settings = {
        "company_name": settings.get("company_name", "NOC Sentinel"),
        "bank_name": bank_name or "Bank",
        "bank_account": account_number,
        "bank_account_name": account_name,
        "ai_name": ai_cfg.get("ai_name") or "AI"
    }

    return {
        "ok": True,
        "customer": {
            "id": customer.get("client_id") or customer["id"],
            "name": customer.get("name"),
            "status": "active" if customer.get("active", True) else "isolated",
            "pppoe_username": customer.get("username"),
            "username": customer.get("username"),
            "phone": customer.get("phone", ""),
            "address": customer.get("address", ""),
            "due_day": customer.get("due_day", 10),
        },
        "package": pkg,
        "unpaid_invoices": unpaid,
        "upcoming_invoice": upcoming_invoice,
        "platform_settings": platform_settings
    }

@router.get("/wifi")
async def get_client_wifi(customer=Depends(get_current_client)):
    db = get_db()
    pppoe_user = customer.get("username")
    if not pppoe_user:
        return {"ok": False, "error": "Tidak ada PPPoE Username"}
        
    try:
        # Fetch 0ms delay snapshot dari sinkronisasi background 
        dev = await db.genieacs_devices.find_one({"pppoe_username": pppoe_user})
        if not dev:
            return {"ok": False, "error": "Router belum tersinkronisasi atau Offline (Modem tidak ditemukan di sistem auto-sync)."}
            
        ssid = dev.get("ssid", "")
        password = dev.get("wifi_password", "")
        
        # Coba hit API GenieACS langsung kalau data di DB belum punya SSID/Password
        if not ssid or not password:
            from services.genieacs_service import get_wifi_settings
            try:
                wifi_data = await asyncio.to_thread(get_wifi_settings, dev.get("id"))
                if wifi_data:
                    ssid = wifi_data.get("ssid") or ssid
                    password = wifi_data.get("password") or password
            except:
                pass

        if not ssid:
            return {"ok": False, "error": "Parameter WiFi tidak ditemukan di Modem Anda."}
        
        # ── Real-time Connected Devices dari GenieACS NBI ───────────────
        # Cache DB mungkin stale (sync 30 menit), fetch langsung agar akurat
        device_id = dev.get("id", "")
        cached_devices = int(dev.get("active_devices") or 0)
        live_devices = cached_devices  # default fallback ke cache
        if device_id:
            try:
                from services.genieacs_service import get_connected_devices_realtime
                rt_count = await asyncio.to_thread(get_connected_devices_realtime, device_id)
                if rt_count >= 0:  # -1 berarti GenieACS tidak bisa dihubungi
                    live_devices = rt_count
                    # Update cache DB agar sync loop tidak perlu nunggu 30 menit
                    await db.genieacs_devices.update_one(
                        {"id": device_id},
                        {"$set": {"active_devices": str(rt_count)}}
                    )
            except Exception:
                pass  # fallback ke nilai cache

        return {
            "ok": True,
            "device_id": device_id,
            "ssid": ssid,
            "password": password,
            "connected_devices": live_devices,
            "status": "online" if dev.get("online") else "offline",
            "rx_power": dev.get("rx_power", ""),
            "uptime": dev.get("uptime", ""),
            "ont_temp": dev.get("ont_temp", ""),
            "last_sync": dev.get("last_sync_time")
        }
    except Exception as e:
        return {"ok": False, "error": str(e)}

class WifiUpdate(BaseModel):
    device_id: str
    ssid: Optional[str] = None
    password: Optional[str] = None

@router.post("/wifi")
async def update_client_wifi(data: WifiUpdate, customer=Depends(get_current_client)):
    if data.password and len(data.password) < 8:
        raise HTTPException(400, "Password minimal 8 karakter")
    
    try:
        from services.genieacs_service import set_parameter
        
        commands = []
        if data.ssid:
            commands.append({"name": "InternetGatewayDevice.LANDevice.1.WLANConfiguration.1.SSID", "value": data.ssid, "type": "xsd:string"})
            commands.append({"name": "InternetGatewayDevice.LANDevice.1.WLANConfiguration.5.SSID", "value": data.ssid + "_5G", "type": "xsd:string"})
        if data.password:
            commands.append({"name": "InternetGatewayDevice.LANDevice.1.WLANConfiguration.1.PreSharedKey.1.KeyPassphrase", "value": data.password, "type": "xsd:string"})
            commands.append({"name": "InternetGatewayDevice.LANDevice.1.WLANConfiguration.5.PreSharedKey.1.KeyPassphrase", "value": data.password, "type": "xsd:string"})
            
        for cmd in commands:
            try:
                await asyncio.to_thread(set_parameter, data.device_id, cmd["name"], cmd["value"], cmd["type"])
            except: pass
            
        return {"ok": True, "message": "Konfigurasi WiFi sedang dikirim ke Router. Tunggu +- 2 menit agar diterapkan."}
    except Exception as e:
        raise HTTPException(500, str(e))

class DeviceTokenRequest(BaseModel):
    token: str
    device_type: Optional[str] = "android"

@router.post("/device-token")
async def register_device_token(data: DeviceTokenRequest, customer=Depends(get_current_client)):
    """Menyimpan FCM Device Token unik per akun klien untuk Push Notification"""
    db = get_db()
    # Field yang benar dari get_current_client adalah 'id' (internal UUID)
    c_id = customer.get("id")
    if not c_id:
        raise HTTPException(401, "Customer ID missing")
        
    await db.customers.update_one(
        {"id": c_id},          # ← query field yang benar
        {"$set": {
            "fcm_token": data.token,
            "fcm_device_type": data.device_type,
            "fcm_last_updated": datetime.now(timezone.utc).isoformat()
        }}
    )
    return {"ok": True, "message": "Device token saved for Push Notifications"}

@router.delete("/device-token")
async def remove_device_token(customer=Depends(get_current_client)):
    """Menghapus FCM Token saat pelanggan logout dari aplikasi Mobile"""
    db = get_db()
    c_id = customer.get("id")
    if not c_id:
        raise HTTPException(401, "Customer ID missing")
        
    await db.customers.update_one(
        {"id": c_id},
        {"$unset": {
            "fcm_token": "",
            "fcm_device_type": "",
            "fcm_last_updated": ""
        }}
    )
    return {"ok": True, "message": "Device token removed successfully"}


@router.post("/reboot")
async def reboot_client_device(customer=Depends(get_current_client)):
    """Izinkan pelanggan restart modem sendiri via TR-069 (max 1x per 10 menit)."""
    db = get_db()
    pppoe_user = customer.get("username")
    if not pppoe_user:
        return {"ok": False, "error": "Tidak ada PPPoE Username pada akun Anda."}
    
    try:
        dev = await db.genieacs_devices.find_one({"pppoe_username": pppoe_user})
        if not dev:
            return {"ok": False, "error": "Modem tidak ditemukan dalam sistem. Pastikan modem sudah terdaftar."}
        
        # Rate limit: maks 1 reboot per 10 menit
        last_reboot = dev.get("last_client_reboot")
        if last_reboot:
            from datetime import datetime, timezone
            try:
                last_dt = datetime.fromisoformat(str(last_reboot).replace("Z", "+00:00"))
                elapsed = (datetime.now(timezone.utc) - last_dt).total_seconds()
                if elapsed < 600:
                    sisa = int(600 - elapsed)
                    menit = sisa // 60
                    detik = sisa % 60
                    return {"ok": False, "error": f"Tunggu {menit}m {detik}dtk lagi sebelum bisa restart kembali."}
            except Exception:
                pass
        
        # Kirim perintah reboot via GenieACS
        from services.genieacs_service import reboot_device
        await asyncio.to_thread(reboot_device, dev.get("id"))
        
        # Catat waktu reboot terakhir
        from datetime import datetime, timezone
        await db.genieacs_devices.update_one(
            {"pppoe_username": pppoe_user},
            {"$set": {"last_client_reboot": datetime.now(timezone.utc).isoformat()}}
        )
        
        return {"ok": True, "message": "✅ Perintah restart dikirim. Modem akan kembali online dalam ±2 menit."}
    except Exception as e:
        return {"ok": False, "error": f"Gagal mengirim perintah restart: {str(e)}"}

# ── Misi 5: Real-time Traffic Graph ─────────────────────────────────────────────
@router.get("/traffic")
async def get_client_traffic(customer=Depends(get_current_client)):
    from mikrotik_api import get_api_client
    from core.db import get_db
    db = get_db()
    
    pppoe_user = customer.get("username")
    if not pppoe_user:
        return {"ok": False, "error": "Tidak ada PPPoE Username"}
        
    device_id = customer.get("device_id")
    if not device_id:
        return {"ok": False, "rx_bps": 0, "tx_bps": 0}
        
    device = await db.devices.find_one({"id": device_id})
    if not device:
        return {"ok": False, "rx_bps": 0, "tx_bps": 0}
        
    try:
        mt = get_api_client(device)
        iface_name = f"<pppoe-{pppoe_user}>"
        
        if customer.get("auth_method") == "hotspot":
            return {"ok": True, "rx_bps": 0, "tx_bps": 0}
            
        try:
            from routers.pppoe import _get_pppoe_bps_ros7, _get_pppoe_bps_ros6
            if device.get("api_mode", "rest") == "rest":
                bps_map = await _get_pppoe_bps_ros7(mt, [iface_name])
                data = bps_map.get(iface_name.lower(), {})
                return {"ok": True, "rx_bps": int(data.get("rx-bits-per-second", 0)), "tx_bps": int(data.get("tx-bits-per-second", 0))}
            else:
                interfaces = await mt.list_interfaces()
                iface_map = {}
                if isinstance(interfaces, list):
                    for iface in interfaces:
                        iname = str(iface.get("name", ""))
                        if iname.lower() == iface_name.lower():
                            iface_map[iname.lower()] = iface
                bps_map = await _get_pppoe_bps_ros6(mt, iface_map, device.get("host", ""))
                data = bps_map.get(iface_name.lower(), {})
                return {"ok": True, "rx_bps": int(data.get("rx-bits-per-second", 0)), "tx_bps": int(data.get("tx-bits-per-second", 0))}
        except Exception:
            pass

    except Exception as e:
        return {"ok": False, "error": str(e)}

    return {"ok": True, "rx_bps": 0, "tx_bps": 0}

# ── Misi 1: In-App Chat Support & Self Healing AI ──────────────────────────────
class TicketRequest(BaseModel):
    category: str
    message: str
    image_url: Optional[str] = None

@router.post("/ticket")
async def create_client_ticket(data: TicketRequest, customer=Depends(get_current_client)):
    from core.db import get_db
    import uuid
    import httpx
    db = get_db()
    
    ticket_id = str(uuid.uuid4())
    doc = {
        "id": ticket_id,
        "customer_id": customer.get("id"),
        "customer_name": customer.get("name"),
        "category": data.category,
        "status": "open",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "messages": [
            {
                "sender": "client",
                "message": data.message,
                "image_url": data.image_url,
                "timestamp": datetime.now(timezone.utc).isoformat()
            }
        ]
    }
    await db.tickets.insert_one(doc)
    
    settings = await db.settings.find_one({"id": "global"}) or {}
    webhook_url = settings.get("n8n_ticket_webhook", "")
    
    if webhook_url:
        try:
            async with httpx.AsyncClient() as client:
                await client.post(webhook_url, json={
                    "event": "new_ticket",
                    "ticket_id": ticket_id,
                    "customer_name": customer.get("name"),
                    "customer_id": customer.get("id"),
                    "pppoe_username": customer.get("username"),
                    "category": data.category,
                    "message": data.message,
                    "image_url": data.image_url
                }, timeout=5)
        except:
            pass
            
    return {"ok": True, "message": "Tiket berhasil dibuat. AI / Teknisi kami akan segera merespon."}

@router.get("/ticket")
async def get_client_tickets(customer=Depends(get_current_client)):
    from core.db import get_db
    db = get_db()
    tickets = await db.tickets.find({"customer_id": customer.get("id")}).sort("created_at", -1).to_list(100)
    for t in tickets: t.pop("_id", None)
    return {"ok": True, "tickets": tickets}

# ── Misi 2: Logika Cuti Langganan (Pause) ──────────────────────────────────────
@router.post("/pause")
async def pause_subscription(customer=Depends(get_current_client)):
    from core.db import get_db
    db = get_db()
    
    unpaid = await db.invoices.find_one({
        "customer_id": customer.get("id"),
        "status": {"$in": ["unpaid", "overdue"]}
    })
    
    if unpaid:
        return {"ok": False, "error": "Maaf, tagihan periode ini sudah terbit atau Anda masih memiliki tunggakan. Tidak dapat mengajukan cuti."}
        
    if not customer.get("active", True):
         return {"ok": False, "error": "Layanan Anda sudah dalam keadaan tidak aktif."}
         
    await db.customers.update_one(
        {"id": customer.get("id")},
        {"$set": {"is_paused": True, "active": False}}
    )
    
    device_id = customer.get("device_id")
    if device_id:
        from mikrotik_api import get_api_client
        device = await db.devices.find_one({"id": device_id})
        if device:
            try:
                mt = get_api_client(device)
                username = customer.get("username")
                if customer.get("auth_method", "local") != "radius":
                     await mt.disable_pppoe_user(username)
                try:
                     await mt.remove_pppoe_active_session(username)
                except: pass
            except: pass
                
    return {"ok": True, "message": "Layanan berhasil di-pause (Cuti). Invoice selanjutnya tidak akan dicetak."}

# ── Misi 3: Penjadwalan Upgrade / Downgrade Mandiri ────────────────────────────
class ChangePackageRequest(BaseModel):
    package_id: str

@router.post("/change-package")
async def schedule_package_change(data: ChangePackageRequest, customer=Depends(get_current_client)):
    from core.db import get_db
    db = get_db()
    
    pkg = await db.billing_packages.find_one({"id": data.package_id})
    if not pkg:
        return {"ok": False, "error": "Paket tidak ditemukan."}
        
    await db.customers.update_one(
        {"id": customer.get("id")},
        {"$set": {"scheduled_package_id": data.package_id}}
    )
    
    return {"ok": True, "message": f"Permintaan berhasil! Layanan akan beroperasi dengan paket {pkg.get('name')} pada siklus mendatang."}

@router.get("/packages")
async def get_client_packages(customer=Depends(get_current_client)):
    from core.db import get_db
    db = get_db()
    # Filter public packages only if needed, mostly we just show active ones
    packages = await db.billing_packages.find({"active": True}).to_list(100)
    for p in packages: 
        p.pop("_id", None)
    return {"ok": True, "packages": packages}

# ── Webhook Rahasia N8N AI Self-Healing Backend ────────────────────────────────
class N8NAutoInjectRequest(BaseModel):
    ticket_id: str
    pppoe_username: str
    action: str 

@router.post("/webhook/n8n/self-healing")
async def n8n_self_healing_webhook(data: N8NAutoInjectRequest):
    from core.db import get_db
    from mikrotik_api import get_api_client
    db = get_db()
    
    customer = await db.customers.find_one({"username": data.pppoe_username})
    if not customer:
        return {"ok": False, "error": "Customer not found"}
        
    device = await db.devices.find_one({"id": customer.get("device_id")})
    if not device:
        return {"ok": False, "error": "Device not found"}
        
    try:
        mt = get_api_client(device)
        
        if data.action == "check-pppoe":
            aktif = False
            try:
                active_sessions = await mt.list_pppoe_active()
                aktif = any(s.get("name") == data.pppoe_username for s in active_sessions)
            except: pass
            return {"ok": True, "is_pppoe_active": aktif}
            
        elif data.action == "inject":
             from services.genieacs_service import provision_new_device
             dev = await db.genieacs_devices.find_one({"pppoe_username": data.pppoe_username})
             if not dev:
                  return {"ok": False, "error": "GenieACS device tidak tercatat untuk user ini."}
                  
             password = customer.get("password", "")
             await asyncio.to_thread(
                  provision_new_device, dev.get("id"), 
                  data.pppoe_username, password, 
                  dev.get("ssid", data.pppoe_username), 
                  dev.get("wifi_password", "12345678"),
                  "internet" 
             )
             return {"ok": True, "message": "Re-Inject perintah dikirim ke GenieACS"}
             
    except Exception as e:
         return {"ok": False, "error": str(e)}


# ══════════════════════════════════════════════════════════════════════════════
# IN-APP CHAT: Admin Endpoints (CS Command Center)
# ══════════════════════════════════════════════════════════════════════════════

from core.auth import get_current_user, require_admin

@router.get("/admin/inapp-chats")
async def admin_list_inapp_chats(user=Depends(get_current_user)):
    """List semua tiket In-App Chat untuk CS Command Center."""
    db = get_db()
    tickets = await db.tickets.find({}).sort("created_at", -1).to_list(500)
    result = []
    for t in tickets:
        t.pop("_id", None)
        # Hitung pesan belum dibalas (tanpa ai_reply dan cs_reply)
        msgs = t.get("messages", [])
        unread = sum(1 for m in msgs if m.get("sender") == "client" and not m.get("ai_reply") and not m.get("cs_reply"))
        t["unread_count"] = unread
        t["last_message"] = msgs[-1].get("message", "") if msgs else ""
        t["last_ts"] = msgs[-1].get("timestamp", t.get("created_at", "")) if msgs else t.get("created_at", "")
        result.append(t)
    return {"ok": True, "tickets": result}


@router.get("/admin/inapp-chats/{ticket_id}/messages")
async def admin_get_chat_messages(ticket_id: str, user=Depends(get_current_user)):
    """Ambil semua pesan dari satu tiket."""
    db = get_db()
    ticket = await db.tickets.find_one({"id": ticket_id})
    if not ticket:
        raise HTTPException(404, "Tiket tidak ditemukan")
    ticket.pop("_id", None)
    return {"ok": True, "ticket": ticket}


class AdminReplyRequest(BaseModel):
    message: str

@router.post("/admin/inapp-chats/{ticket_id}/reply")
async def admin_reply_chat(ticket_id: str, data: AdminReplyRequest, user=Depends(get_current_user)):
    """CS Admin membalas chat pelanggan + kirim FCM push notification."""
    db = get_db()
    ticket = await db.tickets.find_one({"id": ticket_id})
    if not ticket:
        raise HTTPException(404, "Tiket tidak ditemukan")

    reply_msg = {
        "sender": "cs",
        "cs_name": user.get("name", "CS NOC"),
        "message": data.message,
        "timestamp": datetime.now(timezone.utc).isoformat()
    }

    await db.tickets.update_one(
        {"id": ticket_id},
        {
            "$push": {"messages": reply_msg},
            "$set": {"status": "replied", "updated_at": datetime.now(timezone.utc).isoformat()}
        }
    )

    # Kirim FCM Push ke pelanggan
    customer_id = ticket.get("customer_id")
    if customer_id:
        try:
            customer = await db.customers.find_one({"id": customer_id})
            fcm_token = customer.get("fcm_token") if customer else None
            if fcm_token:
                from services.firebase_service import send_push_notification
                cust_name = customer.get("name", "Pelanggan")
                await send_push_notification(
                    [fcm_token],
                    "💬 Balasan dari CS NOC",
                    f"Tim kami menjawab pertanyaan Anda: {data.message[:80]}..."
                )
        except Exception as e:
            pass  # FCM gagal tidak block reply

    return {"ok": True, "message": "Balasan berhasil dikirim ke pelanggan"}


@router.patch("/admin/inapp-chats/{ticket_id}/status")
async def admin_update_chat_status(ticket_id: str, data: dict, user=Depends(get_current_user)):
    """Update status tiket: open / replied / closed / escalated."""
    db = get_db()
    status = data.get("status", "open")
    await db.tickets.update_one(
        {"id": ticket_id},
        {"$set": {"status": status, "updated_at": datetime.now(timezone.utc).isoformat()}}
    )
    return {"ok": True, "message": f"Status tiket diupdate ke '{status}'"}


# ══════════════════════════════════════════════════════════════════════════════
# IN-APP CHAT: Customer Endpoints — kirim pesan lanjutan & baca riwayat
# ══════════════════════════════════════════════════════════════════════════════

@router.get("/chat/history")
async def get_chat_history(customer=Depends(get_current_client)):
    """Ambil riwayat chat aktif pelanggan (tiket terbuka terakhir)."""
    db = get_db()
    ticket = await db.tickets.find_one(
        {"customer_id": customer.get("id"), "status": {"$in": ["open", "replied", "escalated"]}},
        sort=[("created_at", -1)]
    )
    if not ticket:
        return {"ok": True, "ticket": None, "messages": []}
    ticket.pop("_id", None)
    return {"ok": True, "ticket": ticket, "messages": ticket.get("messages", [])}


class ChatMessageRequest(BaseModel):
    message: str
    image_base64: Optional[str] = None

@router.post("/chat/send")
async def send_chat_message(data: ChatMessageRequest, customer=Depends(get_current_client)):
    """
    Kirim pesan chat dari pelanggan.
    - Jika ada tiket aktif: lanjutkan di tiket yang sama
    - Jika tidak ada: buat tiket baru
    - AI (Gemini) akan membalas otomatis jika API key tersedia
    - Deteksi modem reset → re-provision via GenieACS
    - Deteksi kabel putus (foto lampu merah) → alert Telegram NOC
    """
    import uuid
    import httpx
    db = get_db()
    now = datetime.now(timezone.utc).isoformat()

    # Cari tiket aktif
    ticket = await db.tickets.find_one(
        {"customer_id": customer.get("id"), "status": {"$in": ["open", "replied"]}},
        sort=[("created_at", -1)]
    )

    msg_doc = {
        "sender": "client",
        "message": data.message,
        "image_base64": data.image_base64,
        "timestamp": now
    }

    # ── Panggil Gemini AI (non-blocking) ──────────────────────────────────────
    ai_reply = None
    action_taken = None
    settings = await db.system_settings.find_one({"_id": "integrations"}) or {}
    gemini_key = settings.get("gemini_api_key", "")

    if gemini_key:
        try:
            # ── Ambil konfigurasi AI dari DB (customizable oleh admin) ──────────
            ai_cfg = await db.system_settings.find_one({"_id": "ai_chat_config"}) or {}
            gemini_model   = ai_cfg.get("model", "gemini-2.5-flash") # Default to newer model if not set
            feat_modem     = ai_cfg.get("feature_modem_reprovision", True)
            feat_cable     = ai_cfg.get("feature_cable_alert", True)
            feat_needs_cs  = ai_cfg.get("feature_needs_cs", True)
            company_name   = ai_cfg.get("company_name", settings.get("company_name", "ISP kami"))
            payment_info   = ai_cfg.get("payment_info", "")
            extra_context  = ai_cfg.get("extra_context", "")

            # 1. Base personality user or default
            user_base = ai_cfg.get("system_prompt", "").strip()
            if not user_base:
                user_base = (
                    f"Kamu adalah asisten CS (Customer Service) untuk {company_name}, penyedia layanan internet. "
                    "Jawab dengan ramah, singkat, dan dalam Bahasa Indonesia. "
                    + (f"Info pembayaran: {payment_info}. " if payment_info else "")
                    + (f"{extra_context} " if extra_context else "")
                )
            
            # 2. Tambahkan aturan sistem teknis secara paksa (agar automasi jalan terus)
            system_rules = []
            if feat_needs_cs:
                system_rules.append("Jika pertanyaan tidak bisa dijawab tanpa bantuan teknisi manusia, akhiri persis dengan kata: [NEEDS_CS]")
            if feat_modem:
                system_rules.append("Jika mendeteksi modem pelanggan kemungkinan ter-reset (lupa password wifi, internet putus, minta akun PPPoE), akhiri dengan: [MODEM_RESET]")
            if feat_cable:
                system_rules.append("Jika pelanggan mengirim foto dan terlihat lampu merah/LOS menyala di perangkat, akhiri dengan: [CABLE_ISSUE]")

            system_prompt = user_base
            if system_rules:
                system_prompt += "\n\nATURAN SISTEM WAJIB:\n- " + "\n- ".join(system_rules)

            # Ambil konteks pelanggan
            invoices = await db.invoices.find(
                {"customer_id": customer.get("id"), "status": {"$in": ["unpaid", "overdue"]}},
                {"_id": 0, "total": 1, "due_date": 1, "status": 1}
            ).to_list(3)
            pkg = await db.billing_packages.find_one({"id": customer.get("package_id")}) or {}
            company_profile = await db.system_settings.find_one({"_id": "company_profile"}) or {}
            bank_account = company_profile.get("bank_account", "")

            context = (
                f"Nama pelanggan: {customer.get('name')}\n"
                f"Paket internet: {pkg.get('name', '-')} (Rp {pkg.get('price', '-')}/bulan)\n"
                f"Tagihan belum dibayar: {len(invoices)} tagihan\n"
                f"Username PPPoE: {customer.get('username', '-')}\n"
                + (f"Info rekening pembayaran: {bank_account}\n" if bank_account else "")
            )

            # ── Susun riwayat obrolan (History Context) ──
            contents = []
            if ticket and "messages" in ticket:
                # Ambil 8 pesan terakhir agar AI ingat percakapan sebelumnya
                history = ticket["messages"][-8:]
                for m in history:
                    if m.get("sender") == "client":
                        contents.append({"role": "user", "parts": [{"text": m.get("message", "")}]})
                        if m.get("ai_reply"):
                            contents.append({"role": "model", "parts": [{"text": m.get("ai_reply", "")}]})
                    elif m.get("sender") == "cs":
                        contents.append({"role": "model", "parts": [{"text": f"(Pesan dari Manusia/CS): {m.get('message', '')}"}]})

            # ── Pesan paling baru ──
            latest_parts = [{"text": f"Konteks Sistem (Hanya untukmu, JANGAN baca ini ke user):\n{context}\n\nPesan Pelanggan:\n{data.message}"}]
            if data.image_base64:
                img_data = data.image_base64.split(",")[-1] if "," in data.image_base64 else data.image_base64
                latest_parts = [
                    {"inline_data": {"mime_type": "image/jpeg", "data": img_data}},
                    {"text": f"Konteks Sistem:\n{context}\n\nPesan Pelanggan:\n{data.message}"}
                ]
            
            contents.append({"role": "user", "parts": latest_parts})

            payload = {
                "system_instruction": {"parts": [{"text": system_prompt}]},
                "contents": contents,
                "generationConfig": {
                    "temperature": float(ai_cfg.get("temperature", 0.7)),
                    "maxOutputTokens": int(ai_cfg.get("max_tokens", 1000)),
                }
            }

            async with httpx.AsyncClient(timeout=30) as client:
                resp = await client.post(
                    f"https://generativelanguage.googleapis.com/v1beta/models/{gemini_model}:generateContent?key={gemini_key}",
                    json=payload
                )
                if resp.status_code == 200:
                    candidates = resp.json().get("candidates", [])
                    if candidates:
                        parts = candidates[0].get("content", {}).get("parts", [])
                        ai_reply = "".join([p.get("text", "") for p in parts])

            # ── Tindak lanjut berdasarkan deteksi AI ──────────────────────────
            if ai_reply:
                if "[MODEM_RESET]" in ai_reply:
                    action_taken = "modem_reset"
                    ai_reply = ai_reply.replace("[MODEM_RESET]", "").strip()
                    # Auto re-provision modem via GenieACS
                    try:
                        genieacs_dev = await db.genieacs_devices.find_one(
                            {"pppoe_username": customer.get("username")}
                        )
                        if genieacs_dev:
                            from services.genieacs_service import provision_cpe
                            pkg_doc = await db.billing_packages.find_one({"id": customer.get("package_id")}) or {}
                            await asyncio.to_thread(
                                provision_cpe,
                                genieacs_dev["id"],
                                customer.get("username", ""),
                                customer.get("password", ""),
                                genieacs_dev.get("ssid", customer.get("username", "")),
                                genieacs_dev.get("wifi_password", "12345678"),
                            )
                            ai_reply += "\n\n✅ Sistem telah mengirim ulang konfigurasi ke modem Anda secara otomatis. Mohon tunggu 2-3 menit."
                            action_taken = "modem_reprovisioned"
                    except Exception as e:
                        pass

                elif "[CABLE_ISSUE]" in ai_reply:
                    action_taken = "cable_issue"
                    ai_reply = ai_reply.replace("[CABLE_ISSUE]", "").strip()
                    # Alert Telegram NOC
                    telegram_token = settings.get("telegram_bot_token", "")
                    telegram_chat_id = settings.get("telegram_chat_id_noc", "")
                    if telegram_token and telegram_chat_id:
                        try:
                            alert_msg = (
                                f"🚨 *ALERT GANGGUAN FISIK*\n"
                                f"Pelanggan: *{customer.get('name')}*\n"
                                f"Username: `{customer.get('username')}`\n"
                                f"Pesan: {data.message}\n"
                                f"⚠️ AI mendeteksi kemungkinan kabel putus atau lampu merah pada perangkat."
                            )
                            async with httpx.AsyncClient(timeout=10) as client:
                                await client.post(
                                    f"https://api.telegram.org/bot{telegram_token}/sendMessage",
                                    json={"chat_id": telegram_chat_id, "text": alert_msg, "parse_mode": "Markdown"}
                                )
                            ai_reply += "\n\n📡 Tim NOC kami sudah mendapat notifikasi dan segera memeriksa kondisi jaringan di lokasi Anda."
                        except Exception:
                            pass

                elif "[NEEDS_CS]" in ai_reply:
                    action_taken = "needs_cs"
                    ai_reply = ai_reply.replace("[NEEDS_CS]", "").strip()
                    # Update tiket jadi escalated agar CS tahu
                    if ticket:
                        await db.tickets.update_one(
                            {"id": ticket["id"]},
                            {"$set": {"status": "escalated"}}
                        )

        except Exception as ai_err:
            pass  # AI gagal — lanjut tanpa reply

    # Tambahkan ai_reply ke msg_doc
    if ai_reply:
        msg_doc["ai_reply"] = ai_reply
    if action_taken:
        msg_doc["action_taken"] = action_taken

    if ticket:
        # Lanjutkan tiket yang ada
        await db.tickets.update_one(
            {"id": ticket["id"]},
            {
                "$push": {"messages": msg_doc},
                "$set": {"updated_at": now, "status": ticket.get("status", "open")}
            }
        )
        ticket_id = ticket["id"]
    else:
        # Buat tiket baru
        ticket_id = str(uuid.uuid4())
        await db.tickets.insert_one({
            "id": ticket_id,
            "customer_id": customer.get("id"),
            "customer_name": customer.get("name"),
            "category": "chat",
            "status": "open",
            "created_at": now,
            "updated_at": now,
            "messages": [msg_doc]
        })

    return {
        "ok": True,
        "ticket_id": ticket_id,
        "ai_reply": ai_reply,
        "action_taken": action_taken,
        "message": "Pesan terkirim"
    }
