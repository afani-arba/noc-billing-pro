import asyncio
import os
import re
import logging
from datetime import datetime, timedelta, timezone
from motor.motor_asyncio import AsyncIOMotorClient

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("hotspot_cleanup")

def parse_uptime_limit(limit_str: str) -> int:
    """Konversi format Mikrotik (misal: '1h 30m', '1d', '45m') ke detik."""
    if not limit_str:
        return 0
    # Regex findall untuk menangkap semua angka + unit (h/m/d/s)
    parts = re.findall(r"(\d+)\s*([hmds])", limit_str.lower())
    total_secs = 0
    for val, unit in parts:
        total_secs += int(val) * {"h": 3600, "m": 60, "d": 86400, "s": 1}.get(unit, 0)
    return total_secs

async def hotspot_cleanup_loop():
    """
    Background task untuk membersihkan voucher hotspot:
    1. Auto-Expiring: Cek voucher aktif, jika waktu habis -> hapus dari Mikrotik & tandai expired.
    2. Archive Cleanup: Hapus voucher yang sudah berusia > 90 hari dari database.
    Interval: 10 Menit.
    """
    logger.info("Hotspot Expiration & Cleanup Loop started (Interval: 10 Menit).")
    
    # Beri jeda saat boot agar tidak tumpang tindih dengan servis lain
    await asyncio.sleep(30)

    while True:
        client = None
        try:
            db_uri = os.getenv("MONGO_URI", "mongodb://mongodb:27017/nocsentinel")
            db_name = os.getenv("DB_NAME", "nocsentinel")
            client = AsyncIOMotorClient(db_uri)
            db = client[db_name]
            
            now_utc = datetime.now(timezone.utc)

            # ── Bagian A: Deteksi Voucher Expired & Auto-Delete dari Mikrotik ──────
            # Cari semua voucher yang sedang 'active' dan punya session_start_time
            active_vouchers = await db.hotspot_vouchers.find({
                "status": "active",
                "session_start_time": {"$exists": True, "$ne": None}
            }).to_list(None)

            expired_count = 0
            # Kelompokkan voucher expired berdasarkan device_id
            expired_by_device = {}

            for v in active_vouchers:
                sst_str = v.get("session_start_time")
                limit_str = v.get("uptime_limit")
                validity_str = v.get("validity")
                used_uptime_secs = v.get("used_uptime_secs", 0)
                
                if not sst_str:
                    continue
                
                try:
                    start_time = datetime.fromisoformat(sst_str.replace("Z", "+00:00"))
                    if start_time.tzinfo is None:
                        start_time = start_time.replace(tzinfo=timezone.utc)
                    
                    elapsed_act = int((now_utc - start_time).total_seconds())
                    
                    limit_secs = parse_uptime_limit(limit_str) if limit_str else 0
                    validity_secs = parse_uptime_limit(validity_str) if validity_str else 0
                    
                    is_expired = False
                    reason = ""
                    
                    # 1. Check Uptime (Pause-able usage)
                    # Note: We rely on used_uptime_secs which is updated by the poller/dashboard listing
                    if limit_secs > 0 and used_uptime_secs >= limit_secs:
                        is_expired = True
                        reason = "uptime_limit_reached"
                    
                    # 2. Check Validity (Continuous countdown)
                    elif validity_secs > 0 and elapsed_act >= validity_secs:
                        is_expired = True
                        reason = "validity_expired"

                    if is_expired:
                        expired_count += 1
                        did = v.get("device_id")
                        if did and did != "all":
                            expired_by_device.setdefault(did, []).append(v)
                        
                        def fmt_time(s):
                            h, m = divmod(s // 60, 60)
                            return f"{h}h{m}m{s%60}s" if h else f"{m}m{s%60}s"

                        snapshot = {
                            "status": "expired",
                            "expired_at": now_utc.isoformat(),
                            "expiry_reason": reason,
                            "final_uptime": fmt_time(used_uptime_secs),
                            "sisa_waktu_db": "0s",
                            "sisa_validity_db": "0s" if reason == "validity_expired" else fmt_time(max(0, validity_secs - elapsed_act))
                        }
                        
                        await db.hotspot_vouchers.update_one(
                            {"_id": v["_id"]},
                            {"$set": snapshot}
                        )
                except Exception as e:
                    logger.error(f"Error processing expiry for voucher {v.get('username')}: {e}")

            if expired_count > 0:
                logger.info(f"[Hotspot Cleanup] Terdeteksi {expired_count} voucher baru saja expired. Menghapus dari MikroTik...")
                
                # Eksekusi penghapusan di MikroTik
                from mikrotik_api import get_api_client
                for did, v_list in expired_by_device.items():
                    try:
                        device = await db.devices.find_one({"id": did})
                        if not device:
                            continue
                            
                        mt = get_api_client(device)
                        mt_users = await mt.list_hotspot_users()
                        
                        # Mapping nama -> ID Mikrotik
                        names_to_del = {v["username"] for v in v_list}
                        
                        # 1. Hapus dari daftar Hotspot Users
                        for mtu in mt_users:
                            if mtu.get("name") in names_to_del:
                                try:
                                    await mt.delete_hotspot_user(mtu[".id"])
                                    logger.info(f"Deleted expired user '{mtu.get('name')}' from Mikrotik '{device.get('name')}' users list")
                                except Exception as e:
                                    logger.warning(f"Gagal hapus user {mtu.get('name')} dari Mikrotik: {e}")

                        # 2. Putus Sesi Aktif (Kick)
                        for v in v_list:
                            username = v.get("username")
                            try:
                                await mt.remove_hotspot_active_session(username)
                                logger.info(f"Force-kicked expired session for '{username}' from Mikrotik '{device.get('name')}'")
                            except Exception as e:
                                logger.warning(f"Gagal kick session {username}: {e}")
                            await asyncio.sleep(0.05)
                    except Exception as mt_err:
                        logger.error(f"Gagal koneksi ke device {did} untuk delete expired users: {mt_err}")

            # ── Bagian B: Archive Cleanup (> 90 Hari) ───────────────────────────
            ninety_days_ago = now_utc - timedelta(days=90)
            iso_threshold = ninety_days_ago.isoformat()
            
            # Cari voucher usang
            old_vouchers_cursor = db.hotspot_vouchers.find({"created_at": {"$lt": iso_threshold}})
            old_vouchers = await old_vouchers_cursor.to_list(1000)
            
            if old_vouchers:
                vids_to_del = [v["_id"] for v in old_vouchers]
                res = await db.hotspot_vouchers.delete_many({"_id": {"$in": vids_to_del}})
                logger.info(f"[Hotspot Cleanup] Berhasil menghapus archive {res.deleted_count} voucher (usia > 90 hari).")

        except Exception as e:
            logger.error(f"Critical error in hotspot_cleanup_loop: {e}")
        finally:
            if client:
                client.close()
        
        # Tunggu 10 menit
        await asyncio.sleep(600)

if __name__ == "__main__":
    asyncio.run(hotspot_cleanup_loop())
