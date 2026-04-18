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

    Logika pintar:
    - Hitung target_rate untuk setiap pelanggan (Booster > FUP > Night > Normal).
    - Simpan ke DB terlebih dulu (agar RADIUS pakai rate ini saat reconnect).
    - Query active sessions dari MikroTik per device.
    - CoA HANYA dikirim ke user yang sedang ONLINE.
    - User OFFLINE di-skip — mereka dapat rate benar saat reconnect via RADIUS.
    """
    from services.bandwidth_manager import _coa_change_rate
    try:
        db = _db()
        # Evaluasi SEMUA paket. Jika fitur FUP/Night dinonaktifkan, target_rate otomatis
        # turun ke normal, sehingga jika current_rate masih nyangkut, akan otomatis ter-sync.
        pkgs = await db.billing_packages.find({}).to_list(1000)
        pkg_map = {p["id"]: p for p in pkgs}
        if not pkgs:
            return

        customers = await db.customers.find({
            "package_id": {"$in": list(pkg_map.keys())},
            "active": True
        }).to_list(10000)

        now_time_str = datetime.now().strftime("%H:%M")

        # ── Kumpulkan semua yang perlu diupdate ──
        pending = []  # [{"customer": c, "target_rate": str}]

        for c in customers:
            pkg = pkg_map.get(c.get("package_id", ""))
            if not pkg:
                continue

            # Booster check
            booster_active = False
            if c.get("booster_active") and c.get("booster_expires_at"):
                exp_at = datetime.fromisoformat(c["booster_expires_at"])
                if datetime.now(timezone.utc) < exp_at:
                    booster_active = True
                else:
                    await db.customers.update_one({"id": c["id"]}, {"$set": {"booster_active": False}})

            # Night Mode check
            is_night = False
            if pkg.get("day_night_enabled"):
                n_start = pkg.get("night_start", "22:00")
                n_end   = pkg.get("night_end",   "06:00")
                if n_start > n_end:
                    is_night = now_time_str >= n_start or now_time_str < n_end
                else:
                    is_night = n_start <= now_time_str < n_end

            # Tentukan target rate
            if booster_active and pkg.get("boost_rate_limit"):
                target_rate = pkg["boost_rate_limit"]
            elif c.get("fup_active") and pkg.get("fup_rate_limit"):
                target_rate = pkg["fup_rate_limit"]
            elif is_night and pkg.get("night_rate_limit"):
                target_rate = pkg["night_rate_limit"]
            else:
                sp_up   = pkg.get("speed_up",   "—")
                sp_down = pkg.get("speed_down", "—")
                if sp_up == "—" or sp_down == "—":
                    continue
                target_rate = f"{sp_up}/{sp_down}"

            current_rate = c.get("current_rate_limit")
            if target_rate and target_rate != current_rate:
                pending.append({"customer": c, "target_rate": target_rate})

        if not pending:
            return

        # ── Group by device ──
        by_device: dict = {}
        for item in pending:
            dev_id = item["customer"].get("device_id", "")
            by_device.setdefault(dev_id, []).append(item)

        for dev_id, items in by_device.items():
            device = await db.devices.find_one({"id": dev_id})
            if not device:
                continue

            # ── Fetch active sessions dari MikroTik ──
            active_usernames: set = set()
            try:
                from mikrotik_api import get_api_client
                import asyncio as _asyncio
                mt = get_api_client(device)
                sessions = await _asyncio.to_thread(mt._list_resource, "/ppp/active")
                active_usernames = {s.get("name", "") for s in sessions if s.get("name")}
                logger.info(f"[BW] {device.get('name')}: {len(active_usernames)} user aktif")
            except Exception as e:
                logger.warning(f"[BW] Gagal baca active sessions {device.get('name')}: {e}")

            radius_secret = device.get("radius_secret", "")
            nas_ip = device.get("ip_address", "")

            for item in items:
                c            = item["customer"]
                target_rate  = item["target_rate"]
                username     = c.get("username", "")
                current_rate = c.get("current_rate_limit")

                logger.info(f"[BW] {username}: {current_rate} → {target_rate}")

                # ── Simpan ke DB dulu (RADIUS pakai ini saat reconnect) ──
                await db.customers.update_one(
                    {"id": c["id"]},
                    {"$set": {"current_rate_limit": target_rate}}
                )

                # ── CoA hanya jika user SEDANG ONLINE ──
                if username not in active_usernames:
                    logger.info(f"[BW] {username} OFFLINE — rate disimpan, berlaku saat reconnect")
                    continue

                if not radius_secret:
                    logger.warning(f"[BW] {username} ONLINE tapi no radius_secret di device → skip CoA")
                    continue

                coa_result = await _coa_change_rate(
                    nas_ip=nas_ip,
                    nas_secret=radius_secret,
                    username=username,
                    rate_limit=target_rate,
                )
                if coa_result.get("success"):
                    logger.info(f"[BW] ✅ {username} CoA OK → {target_rate} (LIVE, tanpa kick)")
                else:
                    logger.warning(f"[BW] ⚠️  {username} CoA gagal: {coa_result.get('reason')} (rate tersimpan di DB)")

    except Exception as e:
        logger.error(f"[BandwidthScheduler] Day/Night Sync error: {e}")
