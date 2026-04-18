"""
bandwidth_scheduler.py
─────────────────────────────────────────────────────────────────────────────
Background scheduler untuk Dynamic Bandwidth:
  1. FUP Monitoring (setiap 30 menit)
  2. Day/Night Sync + Booster Expiry Check (setiap 5 menit)
  4. FUP Monthly Reset (setiap tanggal 1 tiap bulan)

PERBAIKAN UTAMA:
- Tidak pernah kick user saat limit diubah (CoA tanpa disconnect)
- Night Mode dan Booster saling eksklusif (hanya satu yang bisa aktif)
- Setelah Night Mode berakhir atau Booster expired, rate dikembalikan ke normal
- Perubahan limit hanya berlaku untuk user yang SEDANG AKTIF (online)
- Booster expire resets current_rate_limit agar scheduler evaluasi ulang
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
            
            # ── 2. FUP Monitoring (Tiap 5 menit untuk meminimalisasi lost bytes) ──
            if (now - last_fup_run).total_seconds() >= 300:
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
                
                # Fetch interface data directly to get rx/tx bytes (ppp/active does NOT contain bytes!)
                ifaces = []
                try:
                    ifaces = await mt.list_interfaces()
                except Exception as e:
                    logger.warning(f"[FUP] Gagal fetch interfaces untuk {dev_id}: {e}")
                    
                iface_map = {}
                for i in ifaces:
                    if str(i.get("type", "")).lower() == "pppoe-in":
                        name = i.get("name", "")
                        if name:
                            iface_map[name] = {
                                "rx": int(i.get("rx-byte", 0) or 0),
                                "tx": int(i.get("tx-byte", 0) or 0)
                            }

                for c in cust_list:
                    username = c.get("username", "")
                    session = active_map.get(username)
                    if not session: continue
                    
                    pkg = pkg_map.get(c["package_id"])
                    limit_gb = pkg.get("fup_limit_gb", 0)
                    if limit_gb <= 0: continue
                    limit_bytes = limit_gb * 1_000_000_000
                    
                    # PPPoE interface name format
                    iface_name_1 = f"<pppoe-{username}>"
                    iface_name_2 = username
                    iface_data = iface_map.get(iface_name_1) or iface_map.get(iface_name_2)
                    
                    if iface_data:
                        # tx di MikroTik PPPoE Interface = download pelanggan ke NOC (dari sudut pandang NOC)
                        # rx di MikroTik PPPoE Interface = upload pelanggan ke NOC
                        total_current = iface_data["tx"] + iface_data["rx"]
                    else:
                        # Fallback ke session hotspot jika tersedia
                        current_rx = int(session.get("bytes-out", 0) or 0)
                        current_tx = int(session.get("bytes-in", 0) or 0)
                        total_current = current_rx + current_tx
                        
                    if total_current == 0:
                        continue # Data 0 berarti stat interface gagal dbaca atau tidak tercatat, lewati.
                    
                    last_total = c.get("fup_last_total", 0)
                    saved_used = c.get("fup_bytes_used", 0)
                    
                    # Jika Mikrotik reset counters (misal relogin/reboot)
                    if total_current < last_total:
                        delta = total_current # Anggap ngitung dari 0 lagi
                    else:
                        delta = total_current - last_total
                        
                    new_used = saved_used + delta
                    
                    # Update usage di DB
                    update_data = {"fup_last_total": total_current, "fup_bytes_used": new_used}
                    
                    if new_used >= limit_bytes:
                        # Kena FUP
                        update_data["fup_active"] = True
                        update_data["current_rate_limit"] = None # Force scheduler re-evaluasi
                        fup_rate = pkg.get("fup_rate_limit", "")
                        
                        logger.info(f"[BW] {username} FUP Limit Reached ({(new_used / 1_000_000_000):.2f} GB / {limit_gb} GB). Akan diset ke {fup_rate}")
                        # TIDAK PERLU PANGGIL set_rate_limit DI SINI! 
                        # Scheduler (run_day_night_and_booster_sync) akan menanganinya otomatis dan menggunakan CoA (no-kick).
                        
                    await db.customers.update_one({"id": c["id"]}, {"$set": update_data})
                    
            except Exception as e:
                logger.error(f"[BandwidthScheduler] Gagal sync device {dev_id}: {e}")
                
    except Exception as e:
        logger.error(f"[BandwidthScheduler] FUP Monitoring error: {e}")

async def run_day_night_and_booster_sync(customer_id: str = None):
    """
    Handle logic Day/Night Mode dan Speed Booster secara real-time.
    Dipanggil rutin tiap 5 menit, atau secara targeted untuk 1 pelanggan.

    Perbaikan penting:
    - Night Mode dan Booster SALING EKSKLUSIF — hanya satu yang bisa aktif
    - Booster yang expire → current_rate_limit di-reset agar evaluasi ulang ke Normal
    - CoA dikirim TANPA kick (user tidak diputus koneksinya)
    - Hanya user yang SEDANG ONLINE yang di-CoA; offline → rate tersimpan di DB untuk reconnect
    - Jika customer_id diisi → hanya proses 1 pelanggan tersebut
    """
    from services.bandwidth_manager import _coa_change_rate
    try:
        db = _db()

        # Evaluasi SEMUA paket (atau hanya 1 pelanggan jika customer_id diisi)
        pkgs = await db.billing_packages.find({}).to_list(1000)
        pkg_map = {p["id"]: p for p in pkgs}
        if not pkgs:
            return

        # Filter query: jika targeted, hanya 1 pelanggan; jika global, semua aktif
        q = {"package_id": {"$in": list(pkg_map.keys())}, "active": True}
        if customer_id:
            q["id"] = customer_id

        customers = await db.customers.find(q).to_list(10000)

        now_utc = datetime.now(timezone.utc)
        now_time_str = datetime.now().strftime("%H:%M")

        # ── Kumpulkan semua yang perlu diupdate ──
        pending = []  # [{"customer": c, "target_rate": str}]

        for c in customers:
            pkg = pkg_map.get(c.get("package_id", ""))
            if not pkg:
                continue

            # ── Cek Booster expiry ──
            booster_active = False
            if c.get("booster_active") and c.get("booster_expires_at"):
                try:
                    exp_str = c["booster_expires_at"]
                    # Handle both timezone-aware and naive datetimes
                    exp_at = datetime.fromisoformat(exp_str)
                    if exp_at.tzinfo is None:
                        exp_at = exp_at.replace(tzinfo=timezone.utc)

                    if now_utc < exp_at:
                        booster_active = True
                    else:
                        # Booster expired — matikan dan reset current_rate_limit
                        # agar scheduler mengevaluasi ulang ke kondisi normal
                        logger.info(f"[BW] Booster '{c.get('username')}' expired — reset ke normal")
                        await db.customers.update_one(
                            {"id": c["id"]},
                            {"$set": {
                                "booster_active": False,
                                "current_rate_limit": None  # Force re-evaluate
                            }}
                        )
                        # Update local copy agar evaluasi target_rate benar
                        c["booster_active"] = False
                        c["current_rate_limit"] = None
                except Exception as parse_err:
                    logger.warning(f"[BW] Gagal parse booster_expires_at untuk {c.get('username')}: {parse_err}")
                    # Matikan booster jika tanggal tidak bisa dibaca
                    await db.customers.update_one(
                        {"id": c["id"]},
                        {"$set": {"booster_active": False, "current_rate_limit": None}}
                    )
                    c["booster_active"] = False
                    c["current_rate_limit"] = None

            # ── Night Mode check ──
            is_night = False
            if pkg.get("day_night_enabled"):
                n_start = pkg.get("night_start", "22:00")
                n_end   = pkg.get("night_end",   "06:00")
                if n_start > n_end:
                    # Overnight (misal 22:00 - 06:00)
                    is_night = now_time_str >= n_start or now_time_str < n_end
                else:
                    is_night = n_start <= now_time_str < n_end

            # ── MUTUAL EXCLUSIVITY: Booster vs Night Mode ──
            # Jika Booster sedang aktif, Night Mode DIABAIKAN 
            # Jika Night Mode sedang berlaku, Booster TIDAK bisa diaktifkan
            # (validasi aktivasi Booster di endpoint, bukan di sini)
            # Di scheduler: Booster priority > Night Mode
            if booster_active and is_night:
                # Booster menang → Night Mode diabaikan
                is_night = False

            # ── Tentukan target rate berdasarkan prioritas ──
            # Prioritas: Booster > FUP > Night > Normal
            if booster_active and c.get("boost_rate_limit"):
                target_rate = c["boost_rate_limit"]
            elif c.get("fup_active") and pkg.get("fup_rate_limit"):
                target_rate = pkg["fup_rate_limit"]
            elif is_night and pkg.get("night_rate_limit"):
                target_rate = pkg["night_rate_limit"]
            else:
                # Normal rate dari paket
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

                # CoA TANPA KICK — user tidak diputus koneksinya
                from services.bandwidth_manager import set_rate_limit
                ret = await set_rate_limit(c, device, target_rate, db)
                if ret.get("success"):
                    logger.info(f"[BW] ✅ {username} berhasil diubah ke {target_rate} via {ret.get('method')} (no disconnect)")
                else:
                    logger.error(f"[BW] ❌ {username} GAGAL ubah ke {target_rate}: {ret.get('reason')}")

    except Exception as e:
        logger.error(f"[BandwidthScheduler] Day/Night Sync error: {e}")
