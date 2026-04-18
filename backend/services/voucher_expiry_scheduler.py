"""
voucher_expiry_scheduler.py
─────────────────────────────────────────────────────────────────────────────
Background scheduler yang memeriksa semua voucher Hotspot aktif setiap 30 detik.

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
