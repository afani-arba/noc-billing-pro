"""
bandwidth_scheduler.py
─────────────────────────────────────────────────────────────────────────────
Background scheduler untuk Dynamic Bandwidth:
  1. FUP Monitoring (setiap 30 menit)
  2. Day/Night Sync (setiap 5 menit)
  3. Booster Expiry Check (setiap 5 menit)
  4. FUP Monthly Reset (setiap tanggal 1 tiap bulan)
─────────────────────────────────────────────────────────────────────────────
"""
import asyncio
import logging
from datetime import datetime, timezone, date
import calendar

logger = logging.getLogger(__name__)

def _db():
    from core.db import get_db
    return get_db()

async def bandwidth_scheduler_loop():
    logger.info("[BandwidthScheduler] Memulai scheduler bandwidth (FUP, Day/Night, Booster)...")
    
    last_fup_run = datetime.now()
    last_monthly_reset = ""
    
    while True:
        try:
            now = datetime.now()
            
            # ── 1. Day/Night & Booster (Tiap 5 menit) ──
            await run_day_night_and_booster_sync()
            
            # ── 2. FUP Monitoring (Tiap 30 menit) ──
            if (now - last_fup_run).total_seconds() >= 1800:
                await run_fup_monitoring()
                last_fup_run = now
                
            # ── 3. FUP Monthly Reset (Tiap tgl 1) ──
            today_str = date.today().isoformat()
            if date.today().day == 1 and last_monthly_reset != today_str:
                await run_fup_monthly_reset()
                last_monthly_reset = today_str
                
        except Exception as e:
            logger.error(f"[BandwidthScheduler] Loop error: {e}")
            
        await asyncio.sleep(300) # Sleep 5 Menit

async def run_fup_monthly_reset():
    """Reset FUP bytes_used ke 0 setiap tanggal 1."""
    try:
        db = _db()
        result = await db.customers.update_many(
            {"fup_active": True},
            {"$set": {"fup_active": False, "fup_bytes_used": 0, "fup_last_rx": 0}}
        )
        logger.info(f"[BandwidthScheduler] Bulanan: FUP direset untuk {result.modified_count} pelanggan.")
    except Exception as e:
        logger.error(f"[BandwidthScheduler] FUP Monthly Reset error: {e}")

async def run_fup_monitoring():
    """Monitoring FUP: bandingkan tx/rx bytes dengan allowance bytes."""
    from services.bandwidth_manager import set_rate_limit
    try:
        db = _db()
        # Ambil paket dengan FUP
        pkgs = await db.billing_packages.find({"fup_enabled": True}).to_list(1000)
        pkg_map = {p["id"]: p for p in pkgs}
        if not pkgs: return
        
        # Ambil user aktif dengan FUP belum habis
        customers = await db.customers.find({
            "package_id": {"$in": list(pkg_map.keys())},
            "fup_active": {"$ne": True},
            "active": True
        }).to_list(10000)
        
        if not customers: return
        
        # Group berdasarkan device untuk 1x polling per router
        by_device = {}
        for c in customers:
            dev_id = c.get("device_id")
            if dev_id:
                by_device.setdefault(dev_id, []).append(c)
                
        from mikrotik_api import get_api_client
        for dev_id, cust_list in by_device.items():
            device = await db.devices.find_one({"id": dev_id})
            if not device: continue
            
            try:
                mt = get_api_client(device)
                active_sessions = await mt.list_pppoe_active()
                if not active_sessions: continue
                
                # Map active sessions
                active_map = {s.get("name"): s for s in active_sessions if s.get("name")}
                
                for c in cust_list:
                    username = c.get("username")
                    session = active_map.get(username)
                    if not session: continue
                    
                    pkg = pkg_map.get(c["package_id"])
                    limit_gb = pkg.get("fup_limit_gb", 0)
                    if limit_gb <= 0: continue
                    limit_bytes = limit_gb * 1_000_000_000
                    
                    # session["bytes-in"] adalah upload pelanggan -> download NOC
                    # session["bytes-out"] adalah download pelanggan -> upload NOC
                    # Total pemakaian = download + upload
                    current_rx = int(session.get("bytes-out", 0) or 0)
                    current_tx = int(session.get("bytes-in", 0) or 0)
                    total_current = current_rx + current_tx
                    
                    last_total = c.get("fup_last_total", 0)
                    saved_used = c.get("fup_bytes_used", 0)
                    
                    # Jika Mikrotik reset counters (misal relogin/reboot)
                    if total_current < last_total:
                        delta = total_current # Anggap dari 0
                    else:
                        delta = total_current - last_total
                        
                    new_used = saved_used + delta
                    
                    # Update usage di DB
                    update_data = {"fup_last_total": total_current, "fup_bytes_used": new_used}
                    
                    if new_used >= limit_bytes:
                        # Kena FUP
                        update_data["fup_active"] = True
                        fup_rate = pkg.get("fup_rate_limit", "")
                        
                        logger.info(f"[BW] {username} FUP Limit Reached ({new_used} / {limit_bytes}). Setting rate to {fup_rate}")
                        await set_rate_limit(c, device, fup_rate, db)
                        
                    await db.customers.update_one({"id": c["id"]}, {"$set": update_data})
                    
            except Exception as e:
                logger.error(f"[BandwidthScheduler] Gagal sync device {dev_id}: {e}")
                
    except Exception as e:
        logger.error(f"[BandwidthScheduler] FUP Monitoring error: {e}")

async def run_day_night_and_booster_sync():
    """
    Handle logic Day/Night Mode dan Speed Booster secara real-time.
    Dipanggil rutin tiap 5 menit.
    """
    from services.bandwidth_manager import set_rate_limit
    try:
        db = _db()
        pkgs = await db.billing_packages.find({"$or": [{"day_night_enabled": True}, {"boost_rate_limit": {"$ne": ""}}]}).to_list(1000)
        pkg_map = {p["id"]: p for p in pkgs}
        if not pkgs: return
        
        customers = await db.customers.find({
            "package_id": {"$in": list(pkg_map.keys())},
            "active": True
        }).to_list(10000)

        # Untuk Day/Night kita butuh jam lokal 
        # Server asumsikan Timezone GMT+7 untuk MikroTik Indonesia, 
        # Atau idealnya ambil dari package night_start dan night_end.
        # Format "22:00" string compare ke time.strftime("%H:%M") 
        now_time_str = datetime.now().strftime("%H:%M")
        
        for c in customers:
            pkg = pkg_map.get(c["package_id"])
            if not pkg: continue
            
            # Booster Check
            booster_active = False
            # Check if booster is set on customer explicitly
            if c.get("booster_active") and c.get("booster_expires_at"):
                exp_at = datetime.fromisoformat(c["booster_expires_at"])
                if datetime.now(timezone.utc) < exp_at:
                    booster_active = True
                else:
                    # Expired
                    await db.customers.update_one({"id": c["id"]}, {"$set": {"booster_active": False}})
                    booster_active = False
            
            # Tentukan target bandwidth rate limit
            target_rate = None
            is_night = False
            
            if pkg.get("day_night_enabled"):
                n_start = pkg.get("night_start", "22:00")
                n_end = pkg.get("night_end", "06:00")
                if n_start > n_end:
                    is_night = now_time_str >= n_start or now_time_str < n_end
                else:
                    is_night = n_start <= now_time_str < n_end
            
            if booster_active and pkg.get("boost_rate_limit"):
                target_rate = pkg.get("boost_rate_limit")
            elif c.get("fup_active") and pkg.get("fup_rate_limit"):
                target_rate = pkg.get("fup_rate_limit")
            elif is_night and pkg.get("night_rate_limit"):
                target_rate = pkg.get("night_rate_limit")
            else:
                # Normal rate
                sp_up = pkg.get("speed_up", "—")
                sp_down = pkg.get("speed_down", "—")
                if sp_up == "—" or sp_down == "—": continue # Unmanaged
                target_rate = f"{sp_up}/{sp_down}"
                
            # Cek jika target rate berubah dari recorded rate
            # (Untuk optimasi agar tidak kirim CoA/REST setiap 5 menit jika tidak ada perubahan)
            current_rate = c.get("current_rate_limit")
            if target_rate and target_rate != current_rate:
                # Need to update!
                logger.info(f"[BW] {c.get('username')} rate berubah {current_rate} -> {target_rate}")
                device = await db.devices.find_one({"id": c.get("device_id")})
                if device:
                    ret = await set_rate_limit(c, device, target_rate, db)
                    if ret.get("success"):
                        await db.customers.update_one({"id": c["id"]}, {"$set": {"current_rate_limit": target_rate}})
                    
    except Exception as e:
        logger.error(f"[BandwidthScheduler] Day/Night Sync error: {e}")
