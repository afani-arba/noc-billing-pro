"""
voucher_expiry_scheduler.py
─────────────────────────────────────────────────────────────────────────────
Background scheduler Hotspot Voucher - dua loop terpisah:

  Loop A (10 detik) - hotspot_session_sync_loop:
    * Poll /ip/hotspot/active dari SETIAP device yang punya voucher aktif/offline
    * Voucher 'active' tapi TIDAK ada di MikroTik -> status -> 'offline',
      akumulasi used_uptime_secs, clear last_session_start
    * Voucher 'offline' tapi ADA di MikroTik -> status -> 'active',
      set last_session_start = sekarang (resume uptime countdown)

  Loop B (30 detik) - voucher_expiry_scheduler_loop:
    * Hitung rem_uptime dan rem_validity untuk semua voucher aktif/offline
    * Jika kuota habis -> status -> 'expired' + kirim PoD Disconnect ke NAS
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

# RADIUS Disconnect-Request (PoD) - RFC 3576
DISCONNECT_REQUEST = 40
DISCONNECT_ACK     = 41
DISCONNECT_NAK     = 42

COA_PORT = 3799


# =============================================================================
# PoD Helper
# =============================================================================

def _build_pod_packet(secret_b: bytes, username: str, session_id: str = None,
                      framed_ip: str = None) -> bytes:
    """Build RADIUS Disconnect-Request (PoD) sesuai RFC 3576."""
    pkt_id   = random.randint(0, 255)
    req_auth = b"\x00" * 16

    def pack_attr(t: int, v: bytes) -> bytes:
        return bytes([t, len(v) + 2]) + v

    def pack_string(t: int, s: str) -> bytes:
        return pack_attr(t, s.encode("utf-8"))

    def pack_int(t: int, val: int) -> bytes:
        return pack_attr(t, struct.pack("!I", val))

    attrs = pack_string(1, username)           # User-Name
    if session_id:
        attrs += pack_string(44, session_id)   # Acct-Session-Id
    if framed_ip:
        try:
            attrs += pack_attr(8, socket.inet_aton(framed_ip))  # Framed-IP-Address
        except Exception:
            pass
    attrs += pack_int(61, 19)                  # NAS-Port-Type = Wireless-802.11 (Hotspot)

    length  = 20 + len(attrs)
    header  = struct.pack("!BBH", DISCONNECT_REQUEST, pkt_id, length) + req_auth
    real_auth = hashlib.md5(header + attrs + secret_b).digest()
    return struct.pack("!BBH", DISCONNECT_REQUEST, pkt_id, length) + real_auth + attrs


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
        if code == DISCONNECT_NAK:
            return {"success": False, "code": "Disconnect-NAK"}
        return {"success": False, "reason": f"Unexpected code: {code}"}
    except socket.timeout:
        return {"success": False, "reason": "PoD timeout"}
    except Exception as e:
        return {"success": False, "reason": str(e)}


async def _kick_hotspot_user(db, voucher: dict):
    """Kirim PoD Disconnect ke NAS untuk voucher ini."""
    username  = voucher.get("username", "")
    device_id = voucher.get("device_id", "")
    try:
        device = await db.devices.find_one({"id": device_id})
        if not device:
            logger.warning(f"[VoucherExpiry] Device '{device_id}' tidak ditemukan untuk kick '{username}'")
            return
        nas_ip = device.get("ip_address") or device.get("host", "").split(":")[0]
        secret = (device.get("radius_secret") or device.get("hotspot_secret", "")).strip()
        sess = await db.radius_sessions.find_one(
            {"username": username, "active": True},
            sort=[("updated_at", -1)]
        )
        session_id = sess.get("acct_session_id") if sess else None
        framed_ip  = sess.get("framed_ip") if sess else None
        if nas_ip and secret:
            secret_b = secret.encode("utf-8") if isinstance(secret, str) else secret
            packet   = _build_pod_packet(secret_b, username, session_id, framed_ip)
            loop     = asyncio.get_event_loop()
            result   = await loop.run_in_executor(None, _send_pod_udp, packet, nas_ip, secret_b)
            logger.info(f"[VoucherExpiry] PoD ke {nas_ip} untuk '{username}': {result}")
        else:
            logger.warning(f"[VoucherExpiry] Tidak bisa kick '{username}': nas_ip={nas_ip!r} secret={bool(secret)}")
    except Exception as e:
        logger.error(f"[VoucherExpiry] Gagal kirim PoD untuk '{username}': {e}")


# =============================================================================
# Loop A: Sinkronisasi Status Hotspot (10 Detik)
# =============================================================================

async def _sync_hotspot_sessions(db):
    """
    Bandingkan voucher aktif/offline di DB dengan sesi live di MikroTik.

    - Voucher 'active'  -> tidak ada di MikroTik -> 'offline',
      akumulasi used_uptime_secs, clear last_session_start
    - Voucher 'offline' -> ada di MikroTik       -> 'active',
      set last_session_start = sekarang
    """
    from mikrotik_api import get_api_client

    now_utc = datetime.now(timezone.utc)
    now_iso = now_utc.isoformat()

    try:
        # Kumpulkan semua device_id yang punya voucher aktif/offline
        device_ids = await db.hotspot_vouchers.distinct(
            "device_id",
            {"status": {"$in": ["active", "offline"]}}
        )
        if not device_ids:
            return

        for device_id in device_ids:
            device = await db.devices.find_one({"id": device_id})
            if not device:
                continue

            # Poll MikroTik
            try:
                mt = get_api_client(device)
                active_sessions = await mt.list_hotspot_active()
                mt_active = {
                    (s.get("user") or s.get("name") or "").lower()
                    for s in (active_sessions or [])
                    if s.get("user") or s.get("name")
                }
            except Exception as e:
                logger.warning(f"[SessionSync] Gagal poll {device.get('name', device_id)}: {e}")
                continue

            # Ambil voucher untuk device ini
            vouchers = await db.hotspot_vouchers.find(
                {"device_id": device_id, "status": {"$in": ["active", "offline"]}}
            ).to_list(5000)

            went_offline = 0
            went_online  = 0

            for v in vouchers:
                username   = v.get("username", "")
                cur_status = v.get("status", "")
                is_in_mt   = username.lower() in mt_active

                if cur_status == "active" and not is_in_mt:
                    # Akumulasi uptime sesi yang sedang berjalan
                    extra_secs = 0
                    last_ss = v.get("last_session_start")
                    if last_ss:
                        try:
                            start_dt   = datetime.fromisoformat(last_ss.replace("Z", "+00:00"))
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
                    await db.radius_sessions.update_many(
                        {"username": username, "active": True},
                        {"$set": {"active": False, "stopped_at": now_iso, "updated_at": now_iso}}
                    )
                    went_offline += 1
                    logger.debug(f"[SessionSync] {username} -> OFFLINE (+{extra_secs}s, total={new_used}s)")

                elif cur_status == "offline" and is_in_mt:
                    await db.hotspot_vouchers.update_one(
                        {"_id": v["_id"]},
                        {"$set": {
                            "status":             "active",
                            "last_session_start": now_iso,
                            "updated_at":         now_iso,
                        }}
                    )
                    went_online += 1
                    logger.debug(f"[SessionSync] {username} -> ACTIVE (reconnect via poll)")

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
    """
    from core.db import get_db
    logger.info("[SessionSync] Scheduler sinkronisasi sesi hotspot dimulai - interval 10 detik.")
    await asyncio.sleep(15)  # Tunggu DB & MikroTik siap

    while True:
        try:
            db = get_db()
            await _sync_hotspot_sessions(db)
        except Exception as e:
            logger.error(f"[SessionSync] Loop error: {e}")
        await asyncio.sleep(10)


# =============================================================================
# Loop B: Expiry Check (30 Detik)
# =============================================================================

async def _check_and_expire_vouchers(db):
    """
    Periksa semua voucher aktif/offline dan expired-kan + kick jika kuota habis.
    """
    now_utc = datetime.now(timezone.utc)

    try:
        vouchers = await db.hotspot_vouchers.find(
            {"status": {"$in": ["active", "offline"]}}
        ).to_list(5000)

        if not vouchers:
            return

        expired_count = 0
        for v in vouchers:
            limit_uptime  = int(v.get("limit_uptime_secs", 0))
            used_uptime   = int(v.get("used_uptime_secs", 0))
            should_expire = False
            expire_reason = ""

            # A. Sisa Uptime
            if limit_uptime > 0:
                current_sess_elapsed = 0
                last_ss = v.get("last_session_start")
                if last_ss and v.get("status") == "active":
                    try:
                        start_dt = datetime.fromisoformat(last_ss.replace("Z", "+00:00"))
                        current_sess_elapsed = max(0, int((now_utc - start_dt).total_seconds()))
                    except Exception:
                        pass
                total_used = used_uptime + current_sess_elapsed
                if total_used >= limit_uptime:
                    should_expire = True
                    expire_reason = f"uptime habis ({total_used}s >= {limit_uptime}s)"

            # B. Sisa Validitas
            validity_secs = int(v.get("validity_secs", 0))
            if validity_secs <= 0 and v.get("validity"):
                import re
                total = 0
                for val, unit in re.findall(r"(\d+)\s*([wdhms])", str(v["validity"]).lower()):
                    total += int(val) * {"w": 604800, "d": 86400, "h": 3600, "m": 60, "s": 1}.get(unit, 0)
                validity_secs = total

            if not should_expire and validity_secs > 0:
                first_login = v.get("first_login_time")
                if first_login:
                    try:
                        first_dt = datetime.fromisoformat(first_login.replace("Z", "+00:00"))
                        elapsed  = int((now_utc - first_dt).total_seconds())
                        if elapsed >= validity_secs:
                            should_expire = True
                            expire_reason = f"validitas habis ({elapsed}s >= {validity_secs}s)"
                    except Exception:
                        pass

            if should_expire:
                logger.info(f"[VoucherExpiry] Voucher '{v.get('username')}' EXPIRED: {expire_reason}")
                await db.hotspot_vouchers.update_one(
                    {"_id": v["_id"]},
                    {"$set": {
                        "status":             "expired",
                        "expired_at":         now_utc.isoformat(),
                        "expire_reason":      expire_reason,
                        "last_session_start": None,
                    }}
                )
                await db.radius_sessions.update_many(
                    {"username": v.get("username"), "active": True},
                    {"$set": {"active": False, "stopped_at": now_utc.isoformat()}}
                )
                await _kick_hotspot_user(db, v)
                expired_count += 1

        if expired_count > 0:
            logger.info(f"[VoucherExpiry] {expired_count} voucher di-expired dan di-kick.")

    except Exception as e:
        logger.error(f"[VoucherExpiry] Error saat pengecekan: {e}")


async def voucher_expiry_scheduler_loop():
    """
    Loop B: periksa expired voucher setiap 30 detik.
    """
    from core.db import get_db
    logger.info("[VoucherExpiry] Scheduler dimulai - interval 30 detik.")
    await asyncio.sleep(10)  # Tunggu DB siap

    while True:
        try:
            db = get_db()
            await _check_and_expire_vouchers(db)
        except Exception as e:
            logger.error(f"[VoucherExpiry] Loop error: {e}")
        await asyncio.sleep(30)
