"""
billing_scheduler.py
─────────────────────────────────────────────────────────────────────────────
Background scheduler untuk billing PPPoE:
  1. Auto-Overdue  : setiap jam, scan semua invoice 'unpaid' yang sudah lewat
                     due_date → ubah ke 'overdue'.
  2. Auto-Isolir   : setiap hari (dikendalikan setting billing_settings),
                     kirim WA reminder & disable MikroTik user utk invoice
                     yang overdue + grace period terlampaui.
  3. Reminder H-3  : setiap hari jam 08:00 WIB, kirim WA reminder ke
                     pelanggan yang jatuh tempo 3 hari lagi.
─────────────────────────────────────────────────────────────────────────────
"""
import asyncio
import logging
from datetime import date, timedelta, datetime, timezone

logger = logging.getLogger(__name__)

async def _send_notification(
    customer, msg: str, wa_url: str, wa_token: str, wa_type: str,
    title: str = "Pemberitahuan NOC Sentinel",
    fcm_body: str = None,         # <-- teks khusus untuk FCM; fallback ke `msg` jika None
    send_wa: bool = True          # <-- flag untuk blokir WA jika diperlukan
):
    """Fungsi helper terpusat untuk menembak Notifikasi ke FCM (Aplikasi) dan WhatsApp."""
    # 1. FCM Push Notification (hanya jika firebase-admin tersedia)
    fcm_token = customer.get("fcm_token")
    if fcm_token:
        push_body = fcm_body if fcm_body is not None else msg
        try:
            from services.firebase_service import send_push_notification
            success = await send_push_notification([fcm_token], title, push_body)
            if success:
                logger.info(f"Push Notification FCM terkirim ke pelanggan '{customer.get('name')}'")
        except ImportError:
            logger.debug("firebase-admin not installed, skipping FCM push notification")
        except Exception as fcm_err:
            logger.warning(f"FCM push failed: {fcm_err}")
    
    # 2. WhatsApp Notification (Backup/Konvensional)
    if send_wa:
        phone = customer.get("phone", "")
        if phone and wa_url and wa_token:
            if phone.startswith("0"): phone = "62" + phone[1:]
            elif not phone.startswith("62"): phone = "62" + phone
            import httpx
            try:
                async with httpx.AsyncClient(timeout=10) as client:
                    if wa_type == "fonnte":
                        await client.post(
                            wa_url, headers={"Authorization": wa_token},
                            data={"target": phone, "message": msg, "countryCode": "62"}
                        )
                    else:
                        await client.post(
                            wa_url, headers={"Authorization": wa_token},
                            json={"phone": phone, "message": msg}
                        )
            except Exception as e:
                logger.warning(f"Gagal kirim WA ke {phone}: {e}")

# ── Helper: ambil db ──────────────────────────────────────────────────────────

def _db():
    from core.db import get_db
    return get_db()


def _now_iso():
    return datetime.now(timezone.utc).isoformat()


def _rupiah(amount: int) -> str:
    return f"Rp {amount:,.0f}".replace(",", ".")


def _dtfmt(dt_str: str) -> str:
    """Format YYYY-MM-DD ke DD/MM/YYYY."""
    if not dt_str: return ""
    p = dt_str[:10].split("-")
    return f"{p[2]}/{p[1]}/{p[0]}" if len(p) == 3 else dt_str



# ── 1. Auto-Overdue Scanner ───────────────────────────────────────────────────

async def run_auto_overdue():
    """
    Scan seluruh invoice 'unpaid' di MongoDB.
    Jika due_date sudah lewat dari hari ini → ubah status ke 'overdue'.
    Dipanggil setiap jam dari billing_scheduler_loop().
    """
    try:
        db = _db()
        today = date.today().isoformat()

        # Cari semua invoice unpaid yang due_date-nya sudah lewat
        result = await db.invoices.update_many(
            {
                "status": "unpaid",
                "due_date": {"$lt": today},
            },
            {"$set": {"status": "overdue"}}
        )

        if result.modified_count > 0:
            logger.info(
                f"[BillingScheduler] Auto-overdue: {result.modified_count} "
                f"invoice ditandai OVERDUE (due_date < {today})"
            )
    except Exception as e:
        logger.error(f"[BillingScheduler] run_auto_overdue error: {e}")


# ── 2. Auto-Isolir + WA (overdue + grace period) ──────────────────────────────

def _calculate_prorata(price: int, start_date_str: str, period_year: int, period_month: int) -> tuple[int, int, str]:
    """
    Hitung harga prorata untuk bulan pertama pelanggan baru.
    Return: (amount_prorata, days_active, description_str)
    """
    from calendar import monthrange
    try:
        start = date.fromisoformat(start_date_str[:10])
    except (ValueError, TypeError):
        return price, 0, ""

    # Hanya hitung prorata jika start_date ada di bulan tagihan
    if start.year == period_year and start.month == period_month:
        _, last_day = monthrange(period_year, period_month)
        days_active = last_day - start.day + 1
        prorata_amount = round(price * days_active / last_day)
        desc = f"Prorata {days_active}/{last_day} hari (mulai {start_date_str[:10]})"
        return prorata_amount, days_active, desc

    return price, 0, ""


async def run_auto_isolir():
    """
    Untuk setiap invoice OVERDUE yang grace period-nya sudah berakhir:
      - Kirim WA notifikasi isolir (jika belum dikirim hari ini)
      - Disable PPPoE/Hotspot user di MikroTik
    Grace period diambil dari billing_settings.auto_isolir_grace_days.
    """
    try:
        db = _db()
        settings = await db.billing_settings.find_one({}, {"_id": 0}) or {}
        if not settings.get("auto_isolir_enabled", False):
            return  # Fitur dimatikan dari pengaturan

        grace_days = int(settings.get("auto_isolir_grace_days", 1))
        cutoff = (date.today() - timedelta(days=grace_days)).isoformat()

        # Cari invoice overdue yang due_date + grace sudah terlampaui
        today_iso = date.today().isoformat()
        overdue_invoices = await db.invoices.find(
            {
                "status": "overdue",
                "due_date": {"$lte": cutoff},
                "mt_disabled": {"$ne": True},   # Belum di-disable
            }
        ).to_list(1000)

        if not overdue_invoices:
            return

        # Filter: skip invoice yang masih dalam masa Janji Bayar
        overdue_invoices = [
            inv for inv in overdue_invoices
            if not (inv.get("promise_date") and inv["promise_date"] >= today_iso)
        ]
        if not overdue_invoices:
            logger.info("[BillingScheduler] Auto-isolir: semua invoice overdue masih dalam masa Janji Bayar, dilewati.")
            return

        wa_url = settings.get("wa_api_url", "")
        wa_token = settings.get("wa_token", "")
        wa_type = settings.get("wa_gateway_type", "fonnte")
        wa_template = settings.get(
            "wa_template_isolir",
            "Yth. {customer_name}, layanan internet Anda (Invoice: {invoice_number}, "
            "Paket: {package_name}) telah DIISOLIR karena tagihan {total} belum "
            "dibayar sampai jatuh tempo {due_date}. Segera lakukan pembayaran."
        )

        import httpx
        from mikrotik_api import get_api_client

        for inv in overdue_invoices:
            try:
                customer = await db.customers.find_one({"id": inv["customer_id"]})
                if not customer:
                    continue

                pkg = await db.billing_packages.find_one({"id": inv["package_id"]}) or {}
                device = await db.devices.find_one({"id": customer.get("device_id", "")})

                # Build pesan notifikasi
                msg = (wa_template
                       .replace("{customer_name}", customer.get("name", ""))
                       .replace("{invoice_number}", inv.get("invoice_number", ""))
                       .replace("{package_name}", pkg.get("name", ""))
                       .replace("{total}", _rupiah(inv.get("total", 0)))
                       .replace("{period}", f"{_dtfmt(inv.get('period_start', ''))} s/d {_dtfmt(inv.get('period_end', ''))}")
                       .replace("{due_date}", _dtfmt(inv.get("due_date", ""))))

                # Cek batas WA Isolir untuk PPPoE (Maksimal 2x)
                wa_isolir_count = inv.get("wa_isolir_count", 0)
                send_wa = True
                if customer.get("service_type") == "pppoe":
                    if wa_isolir_count >= 2:
                        send_wa = False
                    else:
                        await db.invoices.update_one({"id": inv["id"]}, {"$inc": {"wa_isolir_count": 1}})

                # Kirim gabungan WA & Push Notification
                await _send_notification(
                    customer, msg, wa_url, wa_token, wa_type, title="Layanan Terisolir", send_wa=send_wa
                )

                # Disable MikroTik user
                if device:
                    try:
                        mt = get_api_client(device)
                        username = customer.get("username", "")
                        auth_method = customer.get("auth_method", "local")
                        
                        if auth_method == "radius":
                            try:
                                await mt.remove_pppoe_active_session(username)
                            except Exception:
                                pass
                            logger.info(
                                f"[BillingScheduler] Auto-isolir: user '{username}' (RADIUS) active session "
                                f"dihapus (Invoice {inv.get('invoice_number')})"
                            )
                        else:
                            await mt.disable_pppoe_user(username)
                            # Kick active session agar koneksi langsung terputus
                            try:
                                await mt.remove_pppoe_active_session(username)
                            except Exception:
                                pass  # non-fatal
                            logger.info(
                                f"[BillingScheduler] Auto-isolir: user '{username}' di-disable "
                                f"dan active session dihapus (Invoice {inv.get('invoice_number')})"
                            )
                    except Exception as mt_err:
                        logger.warning(f"[BillingScheduler] Gagal isolir di MikroTik ({inv['id']}): {mt_err}")

                # ── Ganti SSID via GenieACS (jika tersedia) ──────────────────────────────
                original_ssid = None
                genieacs_device_id = None
                username_for_genie = customer.get("username", "")

                try:
                    from services import genieacs_service as genie_svc
                    g_devs = await asyncio.to_thread(genie_svc.get_devices, 1, username_for_genie, "")
                    if g_devs:
                        g_dev = g_devs[0]
                        genieacs_device_id = g_dev.get("_id")

                        # Ambil SSID saat ini
                        lan1 = g_dev.get("InternetGatewayDevice", {}).get("LANDevice", {}).get("1", {})
                        wlan = lan1.get("WLANConfiguration", {}).get("1", {})
                        ssid_obj = wlan.get("SSID", {})
                        if isinstance(ssid_obj, dict):
                            original_ssid = ssid_obj.get("_value")
                        elif isinstance(ssid_obj, (str, int)):
                            original_ssid = str(ssid_obj)

                        # Ganti SSID hanya jika belum diubah sebelumnya
                        if original_ssid and "ISOLIR" not in str(original_ssid).upper():
                            new_ssid = f"ISOLIR_{str(original_ssid)[:20]}"
                            await asyncio.to_thread(
                                genie_svc.set_parameter,
                                genieacs_device_id,
                                "InternetGatewayDevice.LANDevice.1.WLANConfiguration.1.SSID",
                                new_ssid,
                            )
                            logger.info(
                                f"[BillingScheduler] SSID diubah: '{original_ssid}' → '{new_ssid}' "
                                f"(GenieACS: {genieacs_device_id})"
                            )
                except Exception as ge:
                    logger.warning(f"[BillingScheduler] GenieACS SSID isolir error ({username_for_genie}): {ge}")

                # Tandai sudah di-disable + simpan snapshot SSID ke invoice
                update_fields = {
                    "mt_disabled": True,
                    "auto_isolir_at": _now_iso(),
                }
                if original_ssid and genieacs_device_id:
                    update_fields["original_ssid"] = str(original_ssid)
                    update_fields["genieacs_device_id"] = genieacs_device_id

                await db.invoices.update_one(
                    {"id": inv["id"]},
                    {"$set": update_fields}
                )

            except Exception as inv_err:
                logger.error(f"[BillingScheduler] Error isolir invoice {inv.get('id')}: {inv_err}")

        logger.info(f"[BillingScheduler] Auto-isolir selesai: {len(overdue_invoices)} invoice diproses")

    except Exception as e:
        logger.error(f"[BillingScheduler] run_auto_isolir error: {e}")


# ── 3. Auto Generate Invoices H-3 ────────────────────────────────────────────

async def run_auto_generate_invoices():
    """
    Buat tagihan otomatis 3 hari sebelum jatuh tempo pelanggan.
    Juga kirim WA notifikasi ke pelanggan setelah dibuat.
    """
    try:
        db = _db()
        import uuid
        import httpx
        from calendar import monthrange
        import random
        
        today = date.today()
        target_date = today + timedelta(days=3)
        target_year = target_date.year
        target_month = target_date.month
        target_day = target_date.day
        
        _, last_day = monthrange(target_year, target_month)
        
        customers = await db.customers.find({
            "active": True,
            "package_id": {"$exists": True, "$ne": None}
        }).to_list(5000)
        
        created = 0
        
        settings = await db.billing_settings.find_one({}, {"_id": 0}) or {}
        wa_url = settings.get("wa_api_url", "")
        wa_token = settings.get("wa_token", "")
        wa_type = settings.get("wa_gateway_type", "fonnte")
        wa_template = settings.get(
            "wa_template_unpaid",
            "Yth. {customer_name}, tagihan internet Anda sebesar {total} "
            "(Invoice: {invoice_number}, Paket: {package_name}) jatuh tempo "
            "pada {due_date}. Mohon segera melakukan pembayaran."
        )

        for c in customers:
            c_due_day = c.get("due_day", 10)
            effective_due_day = min(c_due_day, last_day)
            
            if effective_due_day != target_day:
                continue
                
            # Cek apakah sudah ada invoice untuk periode tsb
            period_prefix = f"{target_year}-{target_month:02d}"
            existing = await db.invoices.find_one({
                "customer_id": c["id"],
                "period_start": {"$regex": f"^{period_prefix}"}
            })
            if existing:
                continue
                
            # ── Check Scheduled Package Change (Misi 3) ──
            if c.get("scheduled_package_id"):
                sched_pkg = await db.billing_packages.find_one({"id": c["scheduled_package_id"]})
                if sched_pkg:
                    c["package_id"] = c["scheduled_package_id"]
                    await db.customers.update_one(
                        {"id": c["id"]},
                        {"$set": {"package_id": c["package_id"]}, "$unset": {"scheduled_package_id": ""}}
                    )
                
            pkg = await db.billing_packages.find_one({"id": c["package_id"]})
            if not pkg:
                continue

            # ── Prorata: hitung jika pelanggan baru bergabung bulan ini ──────────
            base_price = pkg["price"]
            is_prorata = False
            prorata_days = 0
            prorata_desc = ""
            start_date_str = c.get("start_date", "")
            if start_date_str:
                prorata_amount, prorata_days, prorata_desc = _calculate_prorata(
                    base_price, start_date_str, target_year, target_month
                )
                if prorata_days > 0 and prorata_amount < base_price:
                    base_price = prorata_amount
                    is_prorata = True

            # ── Promo Early Bird (Misi 4) ──
            discount = 0
            if pkg.get("enable_early_promo") and pkg.get("promo_amount", 0) > 0:
                recent_invoices = await db.invoices.find({
                    "customer_id": c["id"],
                    "status": {"$ne": "cancelled"}
                }).sort("due_date", -1).limit(3).to_list(3)
                
                has_late_payment = False
                for ri in recent_invoices:
                    # telat jika due_date < today dan belum lunas
                    if ri.get("status") in ["unpaid", "overdue"] and ri.get("due_date", "") < today.isoformat():
                        has_late_payment = True
                    # telat jika lunas tapi paid_at > due_date
                    elif ri.get("status") == "paid" and ri.get("paid_at", "")[:10] > ri.get("due_date", "")[:10]:
                        has_late_payment = True
                        
                if not has_late_payment and len(recent_invoices) > 0:
                    discount = pkg.get("promo_amount", 0)
                    base_price = max(0, base_price - discount)

            # Buat invoice
            count = await db.invoices.count_documents(
                {"period_start": {"$regex": f"^{period_prefix}"}}
            ) + created
            
            unique_code = random.randint(1, 999)
            total = base_price + unique_code
            
            due_date_str = f"{target_year}-{target_month:02d}-{target_day:02d}"
            inv_num = f"INV-{target_year}-{target_month:02d}-{count+1:04d}"
            
            period_start = f"{target_year}-{target_month:02d}-01"
            period_end = f"{target_year}-{target_month:02d}-{last_day:02d}"
            
            doc = {
                "id": str(uuid.uuid4()),
                "invoice_number": inv_num,
                "customer_id": c["id"],
                "package_id": c["package_id"],
                "amount": base_price + discount,
                "discount": discount,
                "unique_code": unique_code,
                "total": total,
                "period_start": period_start,
                "period_end": period_end,
                "due_date": due_date_str,
                "status": "unpaid",
                "payment_method": None,
                "paid_at": None,
                "created_at": _now_iso(),
                # Prorata fields
                "is_prorata": is_prorata,
                "prorata_days": prorata_days if is_prorata else None,
                "prorata_description": prorata_desc if is_prorata else None,
            }
            await db.invoices.insert_one(doc)
            created += 1
            
            # Send WA & FCM Note
            if wa_template:
                msg = (wa_template
                       .replace("{customer_name}", c.get("name", ""))
                       .replace("{invoice_number}", inv_num)
                       .replace("{package_name}", pkg.get("name", ""))
                       .replace("{total}", _rupiah(total))
                       .replace("{period}", f"{_dtfmt(period_start)} s/d {_dtfmt(period_end)}")
                       .replace("{due_date}", _dtfmt(due_date_str)))
                
                # Jangan kirim WA jika service_type PPPoE (hanya FCM)
                send_wa = (c.get("service_type") != "pppoe")
                await _send_notification(c, msg, wa_url, wa_token, wa_type, title="Tagihan Baru Diterbitkan", send_wa=send_wa)

                    
        if created > 0:
            logger.info(f"[BillingScheduler] Auto-Generate Tagihan H-3: {created} invoice baru telah dibuat dan dikirim WA")

    except Exception as e:
        logger.error(f"[BillingScheduler] run_auto_generate_invoices error: {e}")


# ── 4. Helper Waktu & Throttle ───────────────────────────────────────────────

def _is_throttled(last_sent_iso: str, min_hours: int) -> bool:
    if not last_sent_iso:
        return False
    try:
        from datetime import datetime, timezone
        last = datetime.fromisoformat(last_sent_iso)
        now = datetime.now(timezone.utc)
        diff = (now - last).total_seconds() / 3600.0
        return diff < min_hours
    except Exception:
        return False

# ── 5. Reminder H-3, H-2, H-1, Due, Overdue ──────────────────────────────────

async def process_reminders():
    """
    Memproses semua reminder tagihan (multi-frekuensi):
    - H-3 & H-2: 1x sehari
    - H-1: 4x sehari (>= 6 jam interval)
    - H=0 (Due Date): 6x sehari (>= 4 jam interval)
    - H+1 / Overdue: 2x sehari (08:00 & 16:00 WIB / 01:00 & 09:00 UTC)
    """
    try:
        db = _db()
        settings = await db.billing_settings.find_one({}, {"_id": 0}) or {}
        wa_url = settings.get("wa_api_url", "")
        wa_token = settings.get("wa_token", "")
        wa_type = settings.get("wa_gateway_type", "fonnte")
        
        now = datetime.now(timezone.utc)
        today_date = now.date()
        today_str = today_date.isoformat()
        
        # Ambil semua invoice unpaid & overdue
        invoices_due = await db.invoices.find({
            "status": {"$in": ["unpaid", "overdue"]}
        }).to_list(None)

        sent_count = 0

        for inv in invoices_due:
            due_iso = inv.get("due_date", "")[:10]
            if not due_iso: continue
            
            try: due_date = date.fromisoformat(due_iso)
            except ValueError: continue
                
            days_diff = (due_date - today_date).days
            
            # Tentukan kategori & rules
            category = None
            msg_title = ""
            msg_body = ""
            wa_body = ""
            update_field = None
            should_send = False

            if days_diff == 3:
                category = "H-3"
                update_field = "last_rem_h3_at"
                if inv.get(update_field, "")[:10] != today_str: should_send = True
                msg_body = settings.get("fcm_template_h3", "Tagihan {total} jatuh tempo 3 hari lagi ({due_date}).")
                wa_body = settings.get("wa_template_unpaid", "Tagihan {total} jatuh tempo {due_date}.")
                msg_title = "Peringatan Jatuh Tempo (H-3)"
                
            elif days_diff == 2:
                category = "H-2"
                update_field = "last_rem_h2_at"
                if inv.get(update_field, "")[:10] != today_str: should_send = True
                msg_body = settings.get("fcm_template_h2", "Tagihan {total} jatuh tempo 2 hari lagi ({due_date}).")
                wa_body = settings.get("wa_template_unpaid", "Tagihan {total} jatuh tempo {due_date}.")
                msg_title = "Peringatan Jatuh Tempo (H-2)"
                
            elif days_diff == 1:
                category = "H-1"
                update_field = "last_rem_h1_at"
                if not _is_throttled(inv.get(update_field), 6): should_send = True
                msg_body = settings.get("fcm_template_h1", "Besok batas pembayaran tagihan {total}. Mohon selesaikan kewajiban pembayaran.")
                wa_body = settings.get("wa_template_h1", "Besok jatuh tempo {total}.")
                msg_title = "Peringatan Jatuh Tempo (H-1)"
                
            elif days_diff == 0:
                category = "Due Date"
                update_field = "last_rem_h0_at"
                if not _is_throttled(inv.get(update_field), 4): should_send = True
                msg_body = settings.get("fcm_template_due", "HARI INI jatuh tempo pembayaran {total}.")
                wa_body = settings.get("wa_template_h1", "HARI INI jatuh tempo {total}.")
                msg_title = "Jatuh Tempo Hari Ini"
                
            elif days_diff < 0:
                category = "Overdue"
                update_field = "last_rem_overdue_at"
                if now.hour in [1, 9]:
                    last_sent = inv.get(update_field, "")[:13]
                    if last_sent != _now_iso()[:13]: should_send = True
                msg_body = settings.get("fcm_template_overdue", "Layanan Anda TERISOLIR karena melewati batas waktu pembayaran. Segera lunasi {total}.")
                wa_body = settings.get("wa_template_isolir", "Layanan diisolir. Tagihan {total}.")
                msg_title = "Pemberitahuan Isolir Layanan"
            else:
                continue

            if should_send:
                customer = await db.customers.find_one({"id": inv["customer_id"]})
                if not customer: continue
                if not customer.get("phone") and not customer.get("fcm_token"): continue

                pkg = await db.billing_packages.find_one({"id": inv["package_id"]}) or {}
                
                f_fcm = (msg_body
                       .replace("{customer_name}", customer.get("name", ""))
                       .replace("{invoice_number}", inv.get("invoice_number", ""))
                       .replace("{package_name}", pkg.get("name", ""))
                       .replace("{total}", _rupiah(inv.get("total", 0)))
                       .replace("{due_date}", _dtfmt(inv.get("due_date", ""))))
                
                f_wa = (wa_body
                       .replace("{customer_name}", customer.get("name", ""))
                       .replace("{invoice_number}", inv.get("invoice_number", ""))
                       .replace("{package_name}", pkg.get("name", ""))
                       .replace("{total}", _rupiah(inv.get("total", 0)))
                       .replace("{period}", f"{_dtfmt(inv.get('period_start',''))} s/d {_dtfmt(inv.get('period_end',''))}")
                       .replace("{due_date}", _dtfmt(inv.get("due_date", ""))))

                try:
                    is_pppoe = (customer.get("service_type") == "pppoe")
                    send_wa = True
                    
                    if is_pppoe:
                        if category == "Overdue":
                            wa_isolir_count = inv.get("wa_isolir_count", 0)
                            if wa_isolir_count < 2:
                                send_wa = True
                                await db.invoices.update_one({"id": inv["id"]}, {"$inc": {"wa_isolir_count": 1}})
                            else:
                                send_wa = False
                        else:
                            send_wa = False  # Matikan WA untuk H-3, H-2, H-1, Due pada PPPoE

                    await _send_notification(customer, f_wa, wa_url, wa_token, wa_type, title=msg_title, fcm_body=f_fcm, send_wa=send_wa)
                    await db.invoices.update_one(
                        {"id": inv["id"]},
                        {"$set": {update_field: _now_iso()}}
                    )
                    sent_count += 1
                    await asyncio.sleep(2)
                except Exception as e:
                    logger.warning(f"[BillingScheduler] Gagal kirim reminder {category} ({inv['id']}): {e}")

        if sent_count > 0:
            logger.info(f"[BillingScheduler] Notifikasi {sent_count} tagihan (H-3/H-2/H-1/Due/Overdue) terkirim.")

    except Exception as e:
        logger.error(f"[BillingScheduler] process_reminders error: {e}")

# ── 6. Auto-Hapus Invoice WA Hotspot Kedaluwarsa ─────────────────────────────

async def run_hotspot_invoice_cleanup():
    """
    Hapus otomatis invoice hotspot dari WhatsApp AI yang:
    - status 'unpaid' / 'overdue'
    - due_date sudah lewat (buyer tidak bayar dalam 1 jam)
    Berjalan setiap jam bersama auto-overdue.
    """
    try:
        from datetime import datetime, timezone, timedelta
        db = _db()
        now = datetime.now(timezone.utc)
        cutoff = (now - timedelta(hours=1)).isoformat()

        expired = await db.hotspot_invoices.find({
            "status": {"$in": ["unpaid", "overdue"]},
            "due_date": {"$lt": cutoff},
        }, {"_id": 1, "invoice_number": 1}).to_list(5000)

        if not expired: return
        ids = [e["_id"] for e in expired]
        result = await db.hotspot_invoices.delete_many({"_id": {"$in": ids}})
    except Exception as e:
        logger.error(f"[BillingScheduler] run_hotspot_invoice_cleanup error: {e}")

# ── Main Loop ─────────────────────────────────────────────────────────────────

async def billing_scheduler_loop():
    """
    Loop utama billing scheduler.
    - Auto-overdue + Hotspot cleanup + Reminders (H-3/H-2/H-1/Due/Overdue): Setiap 60 menit
    - Auto-isolir + Auto-generate: Jam 08:05 WIB (01:05 UTC)
    """
    logger.info("[BillingScheduler] Billing scheduler started.")
    last_daily_run: str = ""
    
    while True:
        try:
            # Tasks Hourly (termasuk Notifikasi High-Freq Multi-Interval)
            await run_auto_overdue()
            await run_hotspot_invoice_cleanup()
            
            # Eksekusi Reminder
            await process_reminders()

            # Daily tasks: auto-gen, isolir
            now_utc = datetime.now(timezone.utc)
            is_daily_time = (now_utc.hour == 1 and now_utc.minute >= 5)
            today_str = date.today().isoformat()

            if is_daily_time and last_daily_run != today_str:
                logger.info("[BillingScheduler] Menjalankan daily tasks (auto-gen tagihan & isolir)...")
                await run_auto_generate_invoices()
                await run_auto_isolir()
                last_daily_run = today_str

        except Exception as loop_err:
            logger.error(f"[BillingScheduler] Loop error: {loop_err}")

        await asyncio.sleep(3600)

