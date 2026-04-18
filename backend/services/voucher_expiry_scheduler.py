"""
voucher_expiry_scheduler.py
─────────────────────────────────────────────────────────────────────────────
Background scheduler Hotspot Voucher — dua loop terpisah:

  Loop A (10 detik) — hotspot_session_sync_loop:
    • Poll /ip/hotspot/active dari SETIAP device yang radius-enabled
    • Voucher 'active' tapi TIDAK ada di MikroTik → status → 'offline',
      akumulasi used_uptime_secs, clear last_session_start
    • Voucher 'offline' tapi ADA di MikroTik → status → 'active',
      set last_session_start = sekarang (resume uptime)

  Loop B (30 detik) — voucher_expiry_scheduler_loop:
    • Hitung rem_uptime dan rem_validity untuk semua voucher aktif/offline
    • Jika kuota habis → status → 'expired' + kirim PoD Disconnect ke NAS
─────────────────────────────────────────────────────────────────────────────
"""
import asyncio
import hashlib
import logging
import socket
import struct
import random
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

# RADIUS Disconnect-Request (PoD) — RFC 3576
DISCONNECT_REQUEST = 40
DISCONNECT_ACK     = 41
DISCONNECT_NAK     = 42

COA_PORT = 3799


# ══════════════════════════════════════════════════════════════════════════════
# PoD Helper
# ══════════════════════════════════════════════════════════════════════════════

def _build_pod_packet(secret_b: bytes, username: str, session_id: str = None,
                      framed_ip: str = None, nas_port_type: int = None) -> bytes:
    """Build RADIUS Disconnect-Request (PoD) sesuai RFC 3576."""
    pkt_id  = random.randint(0, 255)
    req_auth = b"\x00" * 16

    def pack_attr(attr_type: int, value: bytes) -> bytes:
        return bytes([attr_type, len(value) + 2]) + value

    def pack_string(attr_type: int, s: str) -> bytes:
        return pack_attr(attr_type, s.encode("utf-8"))

    def pack_int(attr_type: int, val: int) -> bytes:
        return pack_attr(attr_type, struct.pack("!I", val))

    attrs = b""
    attrs += pack_string(1, username)           # User-Name

    if session_id:
        attrs += pack_string(44, session_id)    # Acct-Session-Id (presisi)

    if framed_ip:
        try:
            attrs += pack_attr(8, socket.inet_aton(framed_ip))  # Framed-IP-Address
        except Exception:
            pass

    # Tandai sebagai Hotspot agar MikroTik tidak bingung routing ke PPPoE
    attrs += pack_int(61, 19)  # NAS-Port-Type = Wireless-802.11 (Hotspot)

    length = 20 + len(attrs)
    header = struct.pack("!BBH", DISCONNECT_REQUEST, pkt_id, length) + req_auth
    real_auth = hashlib.md5(header + attrs + secret_b).digest()
    packet = struct.pack("!BBH", DISCONNECT_REQUEST, pkt_id, length) + real_auth + attrs
    return packet


def _send_pod_udp(packet: bytes, nas_ip: str, secret_b: bytes, timeout: float = 5.0) -> dict:
    """Kirim PoD via UDP synchronously."""
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.settimeout(timeout)
        sock.sendto(packet, (nas_ip, COA_PORT))
        resp, _ = sock.recvfrom(4096)
        sock.close()

        if len(resp) < 4:
            return {"success": False, "reason": "PoD response terlalu pendek"}

        code = resp[0]
        if code == DISCONNECT_ACK:
            return {"success": True, "code": "Disconnect-ACK"}
        elif code == DISCONNECT_NAK:
            return {"success": False, "code": "Disconnect-NAK"}
        else:
            return {"success": False, "reason": f"Unexpected code: {code}"}
    except socket.timeout:
        return {"success": False, "reason": "PoD timeout"}
    except Exception as e:
        return {"success": False, "reason": str(e)}


async def _kick_hotspot_user(db, voucher: dict):
    """Kirim PoD Disconnect ke NAS untuk user ini lalu tandai expired."""
    username   = voucher.get("username", "")
    device_id  = voucher.get("device_id", "")

    try:
        device = await db.devices.find_one({"id": device_id})
        if device:
            nas_ip  = device.get("ip_address") or device.get("host", "").split(":")[0]
            secret  = (device.get("radius_secret") or device.get("hotspot_secret", "")).strip()

            # Ambil session info dari radius_sessions untuk presisi
            session_id = None
            framed_ip  = None
            sess = await db.radius_sessions.find_one(
                {"username": username, "active": True},
                sort=[("updated_at", -1)]
            )
            if sess:
                session_id = sess.get("acct_session_id")
                framed_ip  = sess.get("framed_ip")

            if nas_ip and secret:
                secret_b = secret.encode("utf-8") if isinstance(secret, str) else secret
                packet   = _build_pod_packet(secret_b, username, session_id, framed_ip)

                loop = asyncio.get_event_loop()
                result = await loop.run_in_executor(
                    None, _send_pod_udp, packet, nas_ip, secret_b
                )
                logger.info(
                    f"[VoucherExpiry] PoD ke {nas_ip} untuk '{username}': {result}"
                )
            else:
                logger.warning(
                    f"[VoucherExpiry] Tidak bisa kick '{username}': "
                    f"nas_ip={nas_ip!r} / secret kosong={not secret}"
                )
        else:
            logger.warning(f"[VoucherExpiry] Device '{device_id}' tidak ditemukan untuk kick '{username}'")
    except Exception as e:
        logger.error(f"[VoucherExpiry] Gagal kirim PoD untuk '{username}': {e}")


# ══════════════════════════════════════════════════════════════════════════════
# Loop A: Sinkronisasi Status Hotspot (10 Detik)
# ══════════════════════════════════════════════════════════════════════════════

async def _sync_hotspot_sessions(db):
    """
    Bandingkan voucher aktif di DB dengan sesi live di MikroTik.

    - Voucher 'active'  → tidak ada di MikroTik → ubah ke 'offline',
      akumulasi used_uptime_secs, clear last_session_start
    - Voucher 'offline' → ada di MikroTik       → ubah ke 'active',
      set last_session_start = sekarang (resume uptime countdown)
    """
    from mikrotik_api import get_api_client

    now_utc  = datetime.now(timezone.utc)
    now_iso  = now_utc.isoformat()

    try:
        # Ambil semua device yang mungkin punya hotspot voucher
        device_ids = await db.hotspot_vouchers.distinct("device_id", {"status": {"$in": ["active", "offline"]}})
        if not device_ids:
            return

        for device_id in device_ids:
            device = await db.devices.find_one({"id": device_id})
            if not device:
                continue

            # Ambil list active hotspot dari MikroTik
            try:
                mt = get_api_client(device)
                active_sessions = await mt.list_hotspot_active()
                # Normalisasi field: beberapa ROS pakai 'user', lainnya pakai 'name'
                mt_active_usernames = {
                    (s.get("user") or s.get("name") or s.get(".id", "")).lower()
                    for s in (active_sessions or [])
                    if s.get("user") or s.get("name")
                }
            except Exception as e:
                logger.warning(f"[SessionSync] Gagal poll MikroTik {device.get('name', device_id)}: {e}")
                continue

            # Ambil semua voucher active/offline untuk device ini
            vouchers = await db.hotspot_vouchers.find(
                {"device_id": device_id, "status": {"$in": ["active", "offline"]}},
            ).to_list(5000)

            went_offline = 0
            went_online  = 0

            for v in vouchers:
                username    = v.get("username", "")
                cur_status  = v.get("status", "")
                is_in_mt    = username.lower() in mt_active_usernames

                if cur_status == "active" and not is_in_mt:
                    # ── User disconnect dari MikroTik tapi DB masih 'active' ──
                    # Akumulasikan uptime sesi yang sedang berjalan
                    extra_secs = 0
                    last_sess_start = v.get("last_session_start")
                    if last_sess_start:
                        try:
                            start_dt   = datetime.fromisoformat(last_sess_start.replace("Z", "+00:00"))
                            extra_secs = max(0, int((now_utc - start_dt).total_seconds()))
                        except Exception:
                            pass

                    new_used = int(v.get("used_uptime_secs", 0)) + extra_secs

                    await db.hotspot_vouchers.update_one(
                        {"_id": v["_id"]},
                        {"$set": {
                            "status":             "offline",
                            "used_uptime_secs":   new_used,
                            "last_session_start": None,
                            "last_logout_time":   now_iso,
                            "updated_at":         now_iso,
                        }}
                    )
                    # Tandai radius_sessions tidak aktif
                    await db.radius_sessions.update_many(
                        {"username": username, "active": True},
                        {"$set": {"active": False, "stopped_at": now_iso, "updated_at": now_iso}}
                    )
                    went_offline += 1
                    logger.debug(f"[SessionSync] {username} → OFFLINE (akumulasi +{extra_secs}s, total={new_used}s)")

                elif cur_status == "offline" and is_in_mt:
                    # ── User reconnect ke MikroTik tapi DB masih 'offline' ──
                    # (Mungkin Acct-Start terlewat/terlambat)
                    await db.hotspot_vouchers.update_one(
                        {"_id": v["_id"]},
                        {"$set": {
                            "status":             "active",
                            "last_session_start": now_iso,
                            "updated_at":         now_iso,
                        }}
                    )
                    went_online += 1
                    logger.debug(f"[SessionSync] {username} → ACTIVE (reconnect terdeteksi via poll)")

            if went_offline or went_online:
                logger.info(
                    f"[SessionSync] {device.get('name', device_id)}: "
                    f"{went_offline} offline, {went_online} online"
                )

    except Exception as e:
        logger.error(f"[SessionSync] Error: {e}")


async def hotspot_session_sync_loop():
    """
    Loop A: Poll MikroTik setiap 10 detik untuk sinkronisasi status voucher.
    Dijalankan sebagai asyncio background task.
    """
    from core.db import get_db
    logger.info("[SessionSync] Scheduler sinkronisasi sesi hotspot dimulai — interval 10 detik.")

    # Tunggu agar DB dan koneksi MikroTik siap
    await asyncio.sleep(15)

    while True:
        try:
            db = get_db()
            await _sync_hotspot_sessions(db)
        except Exception as e:
            logger.error(f"[SessionSync] Loop error: {e}")

        await asyncio.sleep(10)


# ══════════════════════════════════════════════════════════════════════════════
# Loop B: Expiry Check (30 Detik)
# ══════════════════════════════════════════════════════════════════════════════

async def _check_and_expire_vouchers(db):
    """
    Periksa semua voucher aktif/offline dan expired-kan + kick jika kuota habis.
    Setelah Loop A berjalan, status DB sudah akurat → kalkulasi ini tepat.
    """
    now_utc = datetime.now(timezone.utc)
    now_ts  = now_utc.timestamp()

    try:
        # Periksa voucher 'active' DAN 'offline' — keduanya bisa expired
        active_vouchers = await db.hotspot_vouchers.find(
            {"status": {"$in": ["active", "offline"]}}
        ).to_list(5000)

        if not active_vouchers:
            return

        expired_count = 0
        for v in active_vouchers:
            limit_uptime  = int(v.get("limit_uptime_secs", 0))
            used_uptime   = int(v.get("used_uptime_secs", 0))
            should_expire = False
            expire_reason = ""

            # ── A. Sisa Uptime (berhenti saat offline — sudah diakumulasi Loop A) ──
            if limit_uptime > 0:
                # Tambahkan sesi yang sedang berjalan (jika masih 'active')
                current_sess_elapsed = 0
                last_sess_start = v.get("last_session_start")
                if last_sess_start and v.get("status") == "active":
                    try:
                        start_dt = datetime.fromisoformat(last_sess_start.replace("Z", "+00:00"))
                        current_sess_elapsed = max(0, int((now_utc - start_dt).total_seconds()))
                    except Exception:
                        pass

                total_used_uptime = used_uptime + current_sess_elapsed
                rem_uptime = limit_uptime - total_used_uptime

                if rem_uptime <= 0:
                    should_expire = True
                    expire_reason = f"uptime habis ({total_used_uptime}s >= {limit_uptime}s)"

            # ── B. Sisa Validitas (berjalan terus sejak first_login) ──────────
            validity_secs = int(v.get("validity_secs", 0))

            # Fallback: parse dari string jika validity_secs belum ada
            if validity_secs <= 0 and v.get("validity"):
                from services.bandwidth_scheduler import _parse_uptime_secs_inline
                try:
                    s = str(v["validity"]).lower()
                    import re
                    total = 0
                    for val, unit in re.findall(r"(\d+)\s*([wdhms])", s):
                        total += int(val) * {"w":604800,"d":86400,"h":3600,"m":60,"s":1}.get(unit,0)
                    validity_secs = total
                except Exception:
                    pass

            if not should_expire and validity_secs > 0:
                first_login = v.get("first_login_time")
                if first_login:
                    try:
                        first_dt = datetime.fromisoformat(first_login.replace("Z", "+00:00"))
                        elapsed_since_first = int((now_utc - first_dt).total_seconds())
                        rem_validity = validity_secs - elapsed_since_first
                        if rem_validity <= 0:
                            should_expire = True
                            expire_reason = (
                                f"validitas habis ({elapsed_since_first}s >= {validity_secs}s)"
                            )
                    except Exception:
                        pass

            # ── C. Jika expired: tandai DB + kick ─────────────────────────────
            if should_expire:
                logger.info(
                    f"[VoucherExpiry] Voucher '{v.get('username')}' EXPIRED: {expire_reason}"
                )
                await db.hotspot_vouchers.update_one(
                    {"_id": v["_id"]},
                    {"$set": {
                        "status":             "expired",
                        "expired_at":         now_utc.isoformat(),
                        "expire_reason":      expire_reason,
                        "last_session_start": None,
                    }}
                )
                # Tandai session radius tidak aktif
                await db.radius_sessions.update_many(
                    {"username": v.get("username"), "active": True},
                    {"$set": {"active": False, "stopped_at": now_utc.isoformat()}}
                )
                # Kirim PoD Disconnect
                await _kick_hotspot_user(db, v)
                expired_count += 1

        if expired_count > 0:
            logger.info(f"[VoucherExpiry] {expired_count} voucher di-expired dan di-kick.")

    except Exception as e:
        logger.error(f"[VoucherExpiry] Error saat pengecekan: {e}")


async def voucher_expiry_scheduler_loop():
    """
    Loop B: periksa expired voucher setiap 30 detik.
    Dijalankan sebagai asyncio background task.
    """
    from core.db import get_db
    logger.info("[VoucherExpiry] Scheduler dimulai — interval 30 detik.")

    # Tunggu sebentar agar DB siap (server baru start)
    await asyncio.sleep(10)

    while True:
        try:
            db = get_db()
            await _check_and_expire_vouchers(db)
        except Exception as e:
            logger.error(f"[VoucherExpiry] Loop error: {e}")

        await asyncio.sleep(30)


Logika:
  1. Ambil semua voucher dengan status='active'.
  2. Untuk setiap voucher, hitung sisa waktu:
     a. rem_uptime_secs:
        = limit_uptime_secs - used_uptime_secs - <elapsed sesi aktif saat ini>
        (jika last_session_start ada, berarti user sedang online → hitung juga sesi ini)
        Hitungan mundur BERHENTI saat user offline (tidak ada last_session_start).
     b. rem_validity_secs:
        = validity_secs - <elapsed sejak first_login_time>
        (berjalan TERUS selama voucher masih aktif, terlepas user online/offline)
  3. Jika salah satu: rem_uptime_secs <= 0 ATAU rem_validity_secs <= 0:
     - Set status voucher → 'expired'
     - Kirim Disconnect-Request (PoD) ke NAS MikroTik via RADIUS port 3799
       agar user langsung di-kick dari Hotspot secara instan.
─────────────────────────────────────────────────────────────────────────────
"""
import asyncio
import hashlib
import logging
import socket
import struct
import random
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

# RADIUS Disconnect-Request (PoD) — RFC 3576
DISCONNECT_REQUEST = 40
DISCONNECT_ACK     = 41
DISCONNECT_NAK     = 42

COA_PORT = 3799


def _build_pod_packet(secret_b: bytes, username: str, session_id: str = None,
                      framed_ip: str = None, nas_port_type: int = None) -> bytes:
    """Build RADIUS Disconnect-Request (PoD) sesuai RFC 3576."""
    pkt_id  = random.randint(0, 255)
    req_auth = b"\x00" * 16

    def pack_attr(attr_type: int, value: bytes) -> bytes:
        return bytes([attr_type, len(value) + 2]) + value

    def pack_string(attr_type: int, s: str) -> bytes:
        return pack_attr(attr_type, s.encode("utf-8"))

    def pack_int(attr_type: int, val: int) -> bytes:
        return pack_attr(attr_type, struct.pack("!I", val))

    attrs = b""
    attrs += pack_string(1, username)           # User-Name

    if session_id:
        attrs += pack_string(44, session_id)    # Acct-Session-Id (presisi)

    if framed_ip:
        try:
            attrs += pack_attr(8, socket.inet_aton(framed_ip))  # Framed-IP-Address
        except Exception:
            pass

    # Tandai sebagai Hotspot agar MikroTik tidak bingung routing ke PPPoE
    attrs += pack_int(61, 19)  # NAS-Port-Type = Wireless-802.11 (Hotspot)

    length = 20 + len(attrs)
    header = struct.pack("!BBH", DISCONNECT_REQUEST, pkt_id, length) + req_auth
    real_auth = hashlib.md5(header + attrs + secret_b).digest()
    packet = struct.pack("!BBH", DISCONNECT_REQUEST, pkt_id, length) + real_auth + attrs
    return packet


def _send_pod_udp(packet: bytes, nas_ip: str, secret_b: bytes, timeout: float = 5.0) -> dict:
    """Kirim PoD via UDP synchronously."""
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.settimeout(timeout)
        sock.sendto(packet, (nas_ip, COA_PORT))
        resp, _ = sock.recvfrom(4096)
        sock.close()

        if len(resp) < 4:
            return {"success": False, "reason": "PoD response terlalu pendek"}

        code = resp[0]
        if code == DISCONNECT_ACK:
            return {"success": True, "code": "Disconnect-ACK"}
        elif code == DISCONNECT_NAK:
            return {"success": False, "code": "Disconnect-NAK"}
        else:
            return {"success": False, "reason": f"Unexpected code: {code}"}
    except socket.timeout:
        return {"success": False, "reason": "PoD timeout"}
    except Exception as e:
        return {"success": False, "reason": str(e)}


async def _kick_hotspot_user(db, voucher: dict):
    """Kirim PoD Disconnect ke NAS untuk user ini lalu tandai expired."""
    username   = voucher.get("username", "")
    device_id  = voucher.get("device_id", "")

    try:
        device = await db.devices.find_one({"id": device_id})
        if device:
            nas_ip  = device.get("ip_address") or device.get("host", "").split(":")[0]
            secret  = (device.get("radius_secret") or device.get("hotspot_secret", "")).strip()

            # Ambil session info dari radius_sessions untuk presisi
            session_id = None
            framed_ip  = None
            sess = await db.radius_sessions.find_one(
                {"username": username, "active": True},
                sort=[("updated_at", -1)]
            )
            if sess:
                session_id = sess.get("acct_session_id")
                framed_ip  = sess.get("framed_ip")

            if nas_ip and secret:
                secret_b = secret.encode("utf-8") if isinstance(secret, str) else secret
                packet   = _build_pod_packet(secret_b, username, session_id, framed_ip)

                loop = asyncio.get_event_loop()
                result = await loop.run_in_executor(
                    None, _send_pod_udp, packet, nas_ip, secret_b
                )
                logger.info(
                    f"[VoucherExpiry] PoD ke {nas_ip} untuk '{username}': {result}"
                )
            else:
                logger.warning(
                    f"[VoucherExpiry] Tidak bisa kick '{username}': "
                    f"nas_ip={nas_ip!r} / secret kosong={not secret}"
                )
        else:
            logger.warning(f"[VoucherExpiry] Device '{device_id}' tidak ditemukan untuk kick '{username}'")
    except Exception as e:
        logger.error(f"[VoucherExpiry] Gagal kirim PoD untuk '{username}': {e}")


async def _check_and_expire_vouchers(db):
    """
    Periksa semua voucher aktif dan expired-kan + kick jika kuota habis.
    """
    now_utc = datetime.now(timezone.utc)
    now_ts  = now_utc.timestamp()

    try:
        active_vouchers = await db.hotspot_vouchers.find(
            {"status": "active"}
        ).to_list(5000)

        if not active_vouchers:
            return

        expired_count = 0
        for v in active_vouchers:
            # ── A. Hitung sisa Uptime (berhenti saat offline) ──────────────
            limit_uptime  = int(v.get("limit_uptime_secs", 0))
            used_uptime   = int(v.get("used_uptime_secs", 0))
            should_expire = False
            expire_reason = ""

            if limit_uptime > 0:
                # Jika user sedang online, tambahkan durasi sesi yang sedang berjalan
                current_sess_elapsed = 0
                last_sess_start = v.get("last_session_start")
                if last_sess_start:
                    try:
                        start_dt = datetime.fromisoformat(
                            last_sess_start.replace("Z", "+00:00")
                        )
                        current_sess_elapsed = int((now_utc - start_dt).total_seconds())
                        current_sess_elapsed = max(0, current_sess_elapsed)
                    except Exception:
                        pass

                total_used_uptime = used_uptime + current_sess_elapsed
                rem_uptime = limit_uptime - total_used_uptime

                if rem_uptime <= 0:
                    should_expire = True
                    expire_reason = f"uptime habis ({total_used_uptime}s >= {limit_uptime}s)"

            # ── B. Hitung sisa Validitas (berjalan terus sejak first_login) ──
            validity_secs = int(v.get("validity_secs", 0))
            if not should_expire and validity_secs > 0:
                first_login = v.get("first_login_time")
                if first_login:
                    try:
                        first_dt = datetime.fromisoformat(
                            first_login.replace("Z", "+00:00")
                        )
                        elapsed_since_first = int((now_utc - first_dt).total_seconds())
                        rem_validity = validity_secs - elapsed_since_first
                        if rem_validity <= 0:
                            should_expire = True
                            expire_reason = (
                                f"validitas habis ({elapsed_since_first}s >= {validity_secs}s)"
                            )
                    except Exception:
                        pass

            # ── C. Jika expired: tandai DB + kick ─────────────────────────
            if should_expire:
                logger.info(
                    f"[VoucherExpiry] Voucher '{v.get('username')}' EXPIRED: {expire_reason}"
                )
                await db.hotspot_vouchers.update_one(
                    {"_id": v["_id"]},
                    {"$set": {
                        "status":           "expired",
                        "expired_at":       now_utc.isoformat(),
                        "expire_reason":    expire_reason,
                        "last_session_start": None,
                    }}
                )
                # Tandai session radius tidak aktif
                await db.radius_sessions.update_many(
                    {"username": v.get("username"), "active": True},
                    {"$set": {"active": False, "stopped_at": now_utc.isoformat()}}
                )
                # Kirim PoD Disconnect
                await _kick_hotspot_user(db, v)
                expired_count += 1

        if expired_count > 0:
            logger.info(f"[VoucherExpiry] {expired_count} voucher di-expired dan di-kick.")

    except Exception as e:
        logger.error(f"[VoucherExpiry] Error saat pengecekan: {e}")


async def voucher_expiry_scheduler_loop():
    """
    Loop utama: periksa expired voucher setiap 30 detik.
    Dijalankan sebagai asyncio background task.
    """
    from core.db import get_db
    logger.info("[VoucherExpiry] Scheduler dimulai — interval 30 detik.")

    # Tunggu sebentar agar DB siap (server baru start)
    await asyncio.sleep(10)

    while True:
        try:
            db = get_db()
            await _check_and_expire_vouchers(db)
        except Exception as e:
            logger.error(f"[VoucherExpiry] Loop error: {e}")

        await asyncio.sleep(30)
