"""
bandwidth_scheduler.py
─────────────────────────────────────────────────────────────────────────────
Background scheduler untuk Dynamic Bandwidth:
  1. FUP Monitoring (setiap 30 menit) — FIX #5: dari radius_sessions real-time
  2. Day/Night Sync + Booster Expiry Check (setiap 5 menit)
  3. FUP Monthly Reset (setiap tanggal 1 tiap bulan)
  4. Hotspot Package CoA — kirim CoA instan saat admin ubah bandwidth paket

PERBAIKAN:
- FIX #5: FUP monitoring membaca dari radius_sessions (push dari MikroTik
  via RADIUS Accounting Interim-Update) — real-time tanpa polling API
- CoA tanpa kick user (no disconnect)
- Night Mode dan Booster saling eksklusif
- Booster expire resets current_rate_limit agar scheduler evaluasi ulang
- Hotspot CoA: mendukung RFC 3576 CoA-Request ke semua sesi aktif
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

        await asyncio.sleep(300)  # Sleep 5 Menit

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
    """
    FUP Monitoring: bandingkan total bytes dengan FUP allowance.

    FIX #5: Prioritas dari radius_sessions (real-time via Accounting Interim-Update).
    Fallback ke polling API MikroTik jika radius_sessions kosong.
    """
    from services.bandwidth_manager import set_rate_limit
    try:
        db = _db()
        pkgs = await db.billing_packages.find({"fup_enabled": True}).to_list(1000)
        pkg_map = {p["id"]: p for p in pkgs}
        if not pkgs:
            return

        customers = await db.customers.find({
            "package_id": {"$in": list(pkg_map.keys())},
            "active": True
        }).to_list(10000)

        if not customers:
            return

        # ── Prioritas 1: radius_sessions (real-time dari Accounting) ──
        active_sessions = await db.radius_sessions.find({"active": True}).to_list(10000)
        session_map = {s["username"]: s for s in active_sessions if s.get("username")}
        using_sessions = bool(session_map)

        if using_sessions:
            logger.info(f"[BW] FUP: {len(session_map)} radius_sessions (real-time)")
        else:
            logger.info("[BW] FUP: fallback ke polling API MikroTik")

        by_device: dict = {}
        for c in customers:
            dev_id = c.get("device_id")
            if dev_id:
                by_device.setdefault(dev_id, []).append(c)

        from mikrotik_api import get_api_client

        for dev_id, cust_list in by_device.items():
            device = await db.devices.find_one({"id": dev_id})
            if not device:
                continue

            api_session_map: dict = {}
            if not using_sessions:
                try:
                    mt = get_api_client(device)
                    active = await mt.list_pppoe_active()
                    api_session_map = {s.get("name"): s for s in active if s.get("name")}
                except Exception as e:
                    logger.error(f"[BW] Gagal polling {device.get('name')}: {e}")

            for c in cust_list:
                username = c.get("username")
                pkg = pkg_map.get(c["package_id"])
                limit_gb = pkg.get("fup_limit_gb", 0)
                if limit_gb <= 0:
                    # FIX: Release FUP lock jika admin pindah ke paket tanpa FUP / Speed on Demand
                    if c.get("fup_active"):
                        await db.customers.update_one({"id": c["id"]}, {"$set": {"fup_active": False}})
                        c["fup_active"] = False
                    continue
                limit_bytes = limit_gb * 1_000_000_000
                total_current = 0

                if using_sessions:
                    sess = session_map.get(username)
                    if not sess:
                        continue
                    total_current = sess.get("total_bytes", 0)
                else:
                    api_sess = api_session_map.get(username)
                    if not api_sess:
                        continue
                    rx = int(api_sess.get("bytes-out", 0) or 0)
                    tx = int(api_sess.get("bytes-in", 0) or 0)
                    raw_total  = rx + tx
                    last_total = c.get("fup_last_total", 0)
                    saved_used = c.get("fup_bytes_used", 0)
                    delta = raw_total - last_total if raw_total >= last_total else raw_total
                    total_current = saved_used + delta

                update_data = {"fup_last_total": total_current, "fup_bytes_used": total_current}

                if total_current >= limit_bytes:
                    update_data["fup_active"] = True
                    fup_rate = pkg.get("fup_rate_limit", "")
                    logger.info(f"[BW] {username} FUP ({total_current}/{limit_bytes}B). Rate apply {fup_rate}")
                    await set_rate_limit(c, device, fup_rate, db)

                await db.customers.update_one({"id": c["id"]}, {"$set": update_data})

    except Exception as e:
        logger.error(f"[BandwidthScheduler] FUP Monitoring error: {e}")

async def run_day_night_and_booster_sync(customer_id: str = None):
    """
    Handle logic Day/Night Mode dan Speed Booster secara real-time.
    Dipanggil rutin tiap 5 menit, atau secara targeted untuk 1 pelanggan.

    - Night Mode dan Booster SALING EKSKLUSIF
    - Booster yang expire → current_rate_limit di-reset agar evaluasi ulang ke Normal
    - CoA dikirim TANPA kick (user tidak diputus koneksinya)
    - Hanya user yang SEDANG ONLINE yang di-CoA
    - Jika customer_id diisi → hanya proses 1 pelanggan tersebut
    """
    from services.bandwidth_manager import _coa_change_rate
    try:
        db = _db()

        pkgs = await db.billing_packages.find({}).to_list(1000)
        pkg_map = {p["id"]: p for p in pkgs}
        if not pkgs:
            return

        q = {"package_id": {"$in": list(pkg_map.keys())}, "active": True}
        if customer_id:
            q["id"] = customer_id

        customers = await db.customers.find(q).to_list(10000)

        now_utc = datetime.now(timezone.utc)
        now_time_str = datetime.now().strftime("%H:%M")

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
                    exp_at = datetime.fromisoformat(exp_str)
                    if exp_at.tzinfo is None:
                        exp_at = exp_at.replace(tzinfo=timezone.utc)

                    if now_utc < exp_at:
                        booster_active = True
                    else:
                        # Booster expired — matikan dan reset current_rate_limit
                        logger.info(f"[BW] Booster '{c.get('username')}' expired — reset ke normal")
                        await db.customers.update_one(
                            {"id": c["id"]},
                            {"$set": {"booster_active": False, "current_rate_limit": None}}
                        )
                        c["booster_active"] = False
                        c["current_rate_limit"] = None
                except Exception as parse_err:
                    logger.warning(f"[BW] Gagal parse booster_expires_at untuk {c.get('username')}: {parse_err}")
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
                    is_night = now_time_str >= n_start or now_time_str < n_end
                else:
                    is_night = n_start <= now_time_str < n_end

            # ── MUTUAL EXCLUSIVITY: Booster priority > Night Mode ──
            if booster_active and is_night:
                is_night = False

            # ── Tentukan target rate berdasarkan prioritas ──
            if booster_active and c.get("boost_rate_limit"):
                target_rate = c["boost_rate_limit"]
            elif c.get("fup_active") and pkg.get("fup_rate_limit") and pkg.get("fup_limit_gb", 0) > 0:
                target_rate = pkg["fup_rate_limit"]
            elif is_night and pkg.get("night_rate_limit"):
                target_rate = pkg["night_rate_limit"]
            else:
                sp_up   = pkg.get("speed_up",   "")
                sp_down = pkg.get("speed_down", "")
                if not sp_up or not sp_down:
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

            # ── FIX #6: Perbaikan secret mismatch (fallback global_secret) ──
            radius_secret = device.get("radius_secret") or device.get("hotspot_secret", "")
            if not radius_secret:
                try:
                    hs = await db.hotspot_settings.find_one({}, {"_id": 0}) or {}
                    radius_secret = hs.get("radius_secret") or hs.get("secret", "")
                except Exception:
                    pass

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
                    logger.warning(f"[BW] {username} ONLINE tapi radius_secret kosong → skip CoA")
                    continue

                # CoA TANPA KICK — user tidak diputus koneksinya
                from services.bandwidth_manager import set_rate_limit
                ret = await set_rate_limit(c, device, target_rate, db)
                if ret.get("success"):
                    logger.info(f"[BW] ✅ {username} → {target_rate} via {ret.get('method')} (no disconnect)")
                else:
                    logger.error(f"[BW] ❌ {username} GAGAL → {target_rate}: {ret.get('reason')}")

    except Exception as e:
        logger.error(f"[BandwidthScheduler] Day/Night Sync error: {e}")


async def run_hotspot_package_coa(pkg: dict):
    """
    Kirim RADIUS CoA (RFC 3576) ke semua sesi hotspot aktif yang menggunakan profil/paket ini.

    Dipanggil saat admin mengubah bandwidth (speed_up/speed_down) di halaman
    Paket Layanan Hotspot — agar perubahan berlaku INSTAN tanpa putus koneksi user.

    Flow:
      1. Cari semua hotspot_vouchers aktif dengan profile == pkg.name
      2. Temukan radius_sessions aktif mereka
      3. Kirim CoA-Request ke NAS (MikroTik port 3799) dengan Mikrotik-Rate-Limit VSA
      4. Jika user offline → catat di log, berlaku saat login berikutnya via Access-Accept
    """
    from services.bandwidth_manager import _coa_change_rate
    try:
        db = _db()

        profile_name = pkg.get("name", "")
        speed_up     = str(pkg.get("speed_up",   "") or "").strip()
        speed_down   = str(pkg.get("speed_down", "") or "").strip()

        if not profile_name:
            logger.warning("[HotspotCoA] pkg.name kosong — skip")
            return

        if not speed_up or not speed_down:
            logger.warning(f"[HotspotCoA] Paket {profile_name!r} tidak punya speed_up/speed_down — CoA skip")
            return

        # Format rate MikroTik: "upload/download"  (misal "10M/20M")
        rate_limit = f"{speed_up}/{speed_down}"

        # ── 1. Cari semua voucher aktif dengan profil ini ──────────────────
        vouchers = await db.hotspot_vouchers.find(
            {"profile": profile_name, "status": "active"},
            {"_id": 0, "username": 1, "device_id": 1}
        ).to_list(10000)

        if not vouchers:
            logger.info(f"[HotspotCoA] Tidak ada voucher aktif untuk profil {profile_name!r} — skip")
            return

        logger.info(f"[HotspotCoA] Paket {profile_name!r} diupdate → {rate_limit} | {len(vouchers)} voucher aktif")

        # ── 2. Group by device ─────────────────────────────────────────────
        by_device: dict = {}
        for v in vouchers:
            dev_id = v.get("device_id", "")
            if dev_id:
                by_device.setdefault(dev_id, []).append(v.get("username", ""))

        # ── 3. Pre-load semua sesi aktif sekali per device dari radius_sessions ──
        # Lebih efisien daripada query per-user
        all_active_sessions = await db.radius_sessions.find(
            {"active": True, "service_type": "hotspot"},
            {"_id": 0, "username": 1, "acct_session_id": 1, "framed_ip": 1}
        ).to_list(50000)
        session_map = {s["username"]: s for s in all_active_sessions if s.get("username")}

        # ── 4. Kirim CoA per device ────────────────────────────────────────
        for dev_id, usernames in by_device.items():
            device = await db.devices.find_one({"id": dev_id})
            if not device:
                logger.warning(f"[HotspotCoA] Device {dev_id} tidak ditemukan di DB — skip")
                continue

            nas_ip = device.get("ip_address", "")
            secret = (
                device.get("radius_secret")
                or device.get("hotspot_secret")
                or ""
            )

            if not nas_ip or not secret:
                logger.warning(f"[HotspotCoA] Device {device.get('name', dev_id)}: ip/secret kosong — skip CoA, berlaku saat reconnect")
                continue

            ok_count   = 0
            fail_count = 0
            skip_count = 0

            for username in usernames:
                if not username:
                    continue

                sess = session_map.get(username)
                if not sess:
                    # User terdaftar aktif di DB tapi belum/tidak ada sesi di RADIUS → skip CoA
                    skip_count += 1
                    logger.debug(f"[HotspotCoA] {username}: tidak ada sesi RADIUS aktif — berlaku saat login berikutnya")
                    continue

                session_id = sess.get("acct_session_id")
                framed_ip  = sess.get("framed_ip")

                result = await _coa_change_rate(
                    nas_ip       = nas_ip,
                    nas_secret   = secret,
                    username     = username,
                    rate_limit   = rate_limit,
                    session_id   = session_id,
                    framed_ip    = framed_ip,
                    service_type = "hotspot",
                )

                if result.get("success"):
                    ok_count += 1
                    logger.info(f"[HotspotCoA] ✅ {username} → {rate_limit}")
                else:
                    fail_count += 1
                    logger.warning(f"[HotspotCoA] ❌ {username}: {result.get('reason')}")

            logger.info(
                f"[HotspotCoA] Device {device.get('name', dev_id)}: "
                f"{ok_count} ok, {fail_count} gagal, {skip_count} offline"
            )

    except Exception as e:
        logger.error(f"[HotspotCoA] run_hotspot_package_coa error: {e}")
