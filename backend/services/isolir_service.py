import asyncio
import logging
from datetime import datetime, timedelta
from core.db import get_db

logger = logging.getLogger(__name__)

def _now():
    from datetime import timezone
    return datetime.now(timezone.utc).isoformat()

async def auto_isolir_loop():
    logger.info("Auto Isolir background task started (checks every minute)")
    while True:
        try:
            now = datetime.now()
            db = get_db()
            settings = await db.billing_settings.find_one({}, {"_id": 0}) or {}
            
            is_enabled = settings.get("auto_isolir_enabled", False)
            target_time_str = settings.get("auto_isolir_time", "00:05")
            grace_days = settings.get("auto_isolir_grace_days", 1)
            
            current_time_str = now.strftime("%H:%M")
            if is_enabled and current_time_str == target_time_str:
                # Cek apakah sudah berjalan hari ini
                today_str = now.strftime("%Y-%m-%d")
                run_log = await db.system_logs.find_one({"type": "auto_isolir_run", "date": today_str})
                
                if not run_log:
                    logger.info(f"Executing Auto Isolir for {today_str}...")
                    
                    # Logic check: If grace_days is 0, we should isolate if due_date <= today.
                    # If grace_days is 5, we isolate if due_date + 5 days < today (which is due_date < target_date).
                    if grace_days == 0:
                        target_due_date = today_str
                        query = {
                            "status": {"$in": ["unpaid", "overdue"]},
                            "due_date": {"$lte": target_due_date},
                            "mt_disabled": {"$ne": True}
                        }
                    else:
                        target_due_date = (now.date() - timedelta(days=grace_days)).isoformat()
                        query = {
                            "status": {"$in": ["unpaid", "overdue"]},
                            "due_date": {"$lt": target_due_date},
                            "mt_disabled": {"$ne": True}
                        }
                    
                    # Cari semua invoice belum lunas dan melewati batas toleransi due_date
                    invoices = await db.invoices.find(query).to_list(None)
                    
                    from mikrotik_api import get_api_client
                    success, failed, skipped = 0, 0, 0
                    today_iso = now.date().isoformat()
                    
                    for inv in invoices:
                        # ── Janji Bayar check: skip jika masih dalam masa janji ──
                        if inv.get("promise_date") and inv["promise_date"] >= today_iso:
                            skipped += 1
                            logger.info(
                                f"[Auto Isolir] Invoice {inv.get('invoice_number','?')} dilewati "
                                f"— Janji Bayar aktif hingga {inv['promise_date']}"
                            )
                            continue

                        customer = await db.customers.find_one({"id": inv.get("customer_id")})

                        if not customer:
                            skipped += 1
                            continue
                        device = await db.devices.find_one({"id": customer.get("device_id")})
                        if not device:
                            skipped += 1
                            continue
                        
                        try:
                            auto_isolir_method = settings.get("auto_isolir_method", "whatsapp")
                            username = customer.get("username", "")
                            
                            if auto_isolir_method in ("whatsapp", "both"):
                                mt = get_api_client(device)
                                svc_type = customer.get("service_type", "pppoe")
                                if svc_type == "pppoe":
                                    await mt.disable_pppoe_user(username)
                                else:
                                    await mt.disable_hotspot_user(username)
                                    await mt.remove_hotspot_active_session(username)
                            
                            original_ssid = None
                            genieacs_device_id = None
                            
                            if auto_isolir_method in ("ssid", "both") and username:
                                from services import genieacs_service as genie_svc
                                try:
                                    g_devs = await asyncio.to_thread(genie_svc.get_devices, 1, username, "")
                                    if g_devs:
                                        g_dev = g_devs[0]
                                        genieacs_device_id = g_dev.get("_id")
                                        
                                        # Parse current SSID safely
                                        lan1 = g_dev.get("InternetGatewayDevice", {}).get("LANDevice", {}).get("1", {})
                                        wlan = lan1.get("WLANConfiguration", {}).get("1", {})
                                        ssid_obj = wlan.get("SSID", {})
                                        
                                        if isinstance(ssid_obj, dict):
                                            original_ssid = ssid_obj.get("_value")
                                        elif isinstance(ssid_obj, str) or isinstance(ssid_obj, int):
                                            original_ssid = str(ssid_obj)
                                            
                                        if original_ssid and "ISOLIR" not in str(original_ssid):
                                            new_ssid = f"ISOLIR_{str(original_ssid)[:20]}" # Safe max length
                                            await asyncio.to_thread(
                                                genie_svc.set_parameter,
                                                genieacs_device_id,
                                                "InternetGatewayDevice.LANDevice.1.WLANConfiguration.1.SSID",
                                                new_ssid
                                            )
                                except Exception as ge:
                                    logger.error(f"GenieACS Isolir error for {username}: {ge}")
                            
                            # Update status invoice and save states
                            update_fields = {"status": "overdue"}
                            if auto_isolir_method in ("whatsapp", "both"):
                                update_fields["mt_disabled"] = True
                            if original_ssid and genieacs_device_id:
                                update_fields["original_ssid"] = str(original_ssid)
                                update_fields["genieacs_device_id"] = genieacs_device_id
                                
                            await db.invoices.update_one(
                                {"id": inv["id"]}, 
                                {"$set": update_fields}
                            )
                            success += 1
                            
                            # Kirim WA notifikasi isolir
                            if auto_isolir_method in ("whatsapp", "both"):
                                phone = customer.get("phone")
                                template = settings.get("wa_template_isolir", "")
                                wa_type = settings.get("wa_gateway_type", "fonnte")
                                url = settings.get("wa_api_url", "https://api.fonnte.com/send")
                                token = settings.get("wa_token", "")
                                
                                if phone and template and url:
                                    pkg = await db.billing_packages.find_one({"id": inv.get("package_id")})
                                    
                                    def _rupiah(amount: int) -> str:
                                        return f"Rp {amount:,.0f}".replace(",", ".")
                                        
                                    def _dtfmt(dt_str: str) -> str:
                                        if not dt_str: return ""
                                        p = dt_str[:10].split("-")
                                        return f"{p[2]}/{p[1]}/{p[0]}" if len(p) == 3 else dt_str
                                    
                                    msg = template.replace("{customer_name}", customer.get("name", ""))
                                    msg = msg.replace("{invoice_number}", inv.get("invoice_number", ""))
                                    msg = msg.replace("{package_name}", pkg.get("name", "") if pkg else "")
                                    msg = msg.replace("{total}", _rupiah(inv.get("total", 0)))
                                    msg = msg.replace("{period}", f"{_dtfmt(inv.get('period_start', ''))} s/d {_dtfmt(inv.get('period_end', ''))}")
                                    msg = msg.replace("{due_date}", _dtfmt(inv.get("due_date", "")))
                                    
                                    try:
                                        import httpx
                                        async with httpx.AsyncClient(timeout=10) as client:
                                            if wa_type == "fonnte":
                                                await client.post(url, headers={"Authorization": token}, data={"target": phone, "message": msg, "countryCode": "62"})
                                            elif wa_type == "wablas":
                                                await client.post(url, headers={"Authorization": token}, json={"phone": phone, "message": msg})
                                            else:
                                                headers = {"Authorization": token} if token else {}
                                                await client.post(url, headers=headers, json={"phone": phone, "message": msg})
                                    except Exception as we:
                                        logger.error(f"Auto Isolir WA error for {customer.get('name')}: {we}")
                                        
                        except Exception as e:
                            logger.error(f"Auto Isolir failed for {customer.get('name', '?')}: {e}")
                            failed += 1
                    
                    # Catat bahwa isolir sudah dijalankan hari ini
                    await db.system_logs.insert_one({
                        "type": "auto_isolir_run",
                        "date": today_str,
                        "success": success,
                        "failed": failed,
                        "timestamp": _now()
                    })
                    logger.info(f"Auto Isolir finished: {success} disabled, {failed} failed, {skipped} skipped.")
                    
        except Exception as e:
            logger.error(f"Error in auto_isolir_loop: {e}")
            
        await asyncio.sleep(60) # istirahat 60 detik sebelum cek jam lagi
