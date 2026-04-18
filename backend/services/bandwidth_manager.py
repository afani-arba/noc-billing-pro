"""
bandwidth_manager.py — Dynamic Bandwidth Management
═══════════════════════════════════════════════════════════════════════════════
Strategi perubahan rate-limit (TANPA memutus koneksi user):

1. UTAMA: RADIUS CoA (RFC 3576) — ubah rate-limit LIVE tanpa kick
   - Kirim CoA-Request ke NAS MikroTik port 3799
   - FIX #6: Gunakan Acct-Session-Id + Framed-IP (lebih presisi dari User-Name)
   - User tidak merasakan putus koneksi sama sekali

2. FALLBACK: Update PPPoE profile dinamis (TANPA kick)
   - Buat profile "NOC-BW-<rate>" jika belum ada
   - Update field `profile` di /ppp/secret
   - Berlaku saat reconnect berikutnya (tidak langsung)
   - TIDAK pernah kick session kecuali diminta eksplisit

FIX #6: CoA menyertakan Acct-Session-Id dari radius_sessions bila tersedia,
sehingga CoA hanya mengenai satu sesi aktif yang tepat.
═══════════════════════════════════════════════════════════════════════════════
"""

import asyncio
import struct
import hashlib
import logging
import socket
import os

logger = logging.getLogger(__name__)

# CoA packet codes (RFC 3576)
COA_REQUEST = 43
COA_ACK     = 44
COA_NAK     = 45

# Prefix untuk profile dinamis yang dibuat oleh NOC Billing
NOC_PROFILE_PREFIX = "NOC-BW-"


async def set_rate_limit(customer: dict, device: dict, rate_limit: str, db=None) -> dict:
    """
    Ubah rate-limit user PPPoE TANPA memutuskan koneksi (no kick).

    Prioritas:
    1. RADIUS CoA — berlaku instan tanpa putus koneksi (FIX #6: pakai Acct-Session-Id)
    2. Profile update — berlaku saat reconnect berikutnya (fallback)
    """
    username = customer.get("username", "")
    nas_ip   = device.get("ip_address", "")
    secret   = device.get("radius_secret") or device.get("hotspot_secret", "")

    if not secret:
        logger.warning(f"[BW] {username}: radius_secret kosong di device — CoA tidak bisa dikirim")

    # ── Cari Session-Id dari radius_sessions (FIX #6) ──────────────────────
    session_id = None
    framed_ip  = None
    if db is not None and username:
        try:
            sess = await db.radius_sessions.find_one(
                {"username": username, "active": True},
                sort=[("updated_at", -1)]   # Ambil sesi terbaru
            )
            if sess:
                session_id = sess.get("acct_session_id")
                framed_ip  = sess.get("framed_ip")
        except Exception as e:
            logger.debug(f"[BW] Gagal cari session_id untuk {username}: {e}")

    # ── Metode 1: CoA RADIUS (Live Update tanpa kick) ──
    if secret and nas_ip:
        coa_result = await _coa_change_rate(
            nas_ip     = nas_ip,
            nas_secret = secret,
            username   = username,
            rate_limit = rate_limit,
            session_id = session_id,   # FIX #6
            framed_ip  = framed_ip,    # FIX #6
        )
        if coa_result.get("success"):
            logger.info(f"[BW] ✅ CoA berhasil untuk '{username}' → {rate_limit} (no kick, method=CoA)")
            return coa_result

        logger.warning(f"[BW] CoA gagal untuk '{username}': {coa_result.get('reason')} — fallback ke profile")

    # ── Metode 2: Update Profile (tanpa kick) — sebagai fallback ──
    return await _update_pppoe_profile(username, rate_limit, device, db)


async def _coa_change_rate(
    nas_ip: str,
    nas_secret: str,
    username: str,
    rate_limit: str,
    session_id: str = None,
    framed_ip: str = None,
    coa_port: int = 3799,
    timeout: float = 5.0,
) -> dict:
    """
    Kirim CoA-Request ke MikroTik NAS untuk mengubah rate-limit secara live.

    FIX #6: Menyertakan Acct-Session-Id dan Framed-IP-Address bila tersedia
    agar CoA mengenai sesi yang tepat (bukan semua sesi dengan username itu).

    Implementasi manual (tanpa pyrad) untuk menghindari dependency tambahan.
    """
    try:
        import random
        secret_b = nas_secret.encode("utf-8") if isinstance(nas_secret, str) else nas_secret

        pkt_id  = random.randint(0, 255)
        # RFC 3576: Untuk Authenticator CoA-Request, hitung MD5 dengan authenticator bernilai 0
        req_auth = b"\x00" * 16

        # Build attributes
        def pack_attr(attr_type: int, value: bytes) -> bytes:
            return bytes([attr_type, len(value) + 2]) + value

        def pack_string(attr_type: int, s: str) -> bytes:
            return pack_attr(attr_type, s.encode("utf-8"))

        def pack_int(attr_type: int, val: int) -> bytes:
            return pack_attr(attr_type, struct.pack("!I", val))

        def pack_vsa(vendor_id: int, vendor_type: int, value: bytes) -> bytes:
            vsa_payload = struct.pack("!I", vendor_id) + bytes([vendor_type, len(value) + 2]) + value
            return pack_attr(26, vsa_payload)

        attrs = b""
        attrs += pack_string(1, username)           # User-Name

        # FIX #6: Sertakan Acct-Session-Id jika tersedia (identifier presisi)
        if session_id:
            attrs += pack_string(44, session_id)    # Acct-Session-Id

        # FIX #6: Sertakan Framed-IP-Address jika tersedia
        if framed_ip:
            try:
                ip_bytes = socket.inet_aton(framed_ip)
                attrs += pack_attr(8, ip_bytes)     # Framed-IP-Address
            except Exception:
                pass

        # Mikrotik-Rate-Limit VSA (Vendor 14988, Attribute 8)
        attrs += pack_vsa(14988, 8, rate_limit.encode("utf-8"))

        # Build CoA-Request packet
        length = 20 + len(attrs)
        header = struct.pack("!BBH", COA_REQUEST, pkt_id, length) + req_auth
        resp_auth = hashlib.md5(header + attrs + secret_b).digest()
        packet = struct.pack("!BBH", COA_REQUEST, pkt_id, length) + resp_auth + attrs

        # Kirim via UDP dan tunggu respons
        loop = asyncio.get_event_loop()
        result = await asyncio.wait_for(
            loop.run_in_executor(None, _send_coa_udp, packet, nas_ip, coa_port, secret_b, timeout),
            timeout=timeout + 1
        )
        return result

    except asyncio.TimeoutError:
        return {"success": False, "reason": f"CoA timeout setelah {timeout}s ke {nas_ip}:{coa_port}"}
    except Exception as e:
        return {"success": False, "reason": f"CoA exception: {e}"}


def _send_coa_udp(packet: bytes, nas_ip: str, coa_port: int, secret: bytes, timeout: float) -> dict:
    """
    Kirim paket CoA via UDP synchronously dan parse respons.
    Dijalankan di thread pool untuk menghindari blocking event loop.
    """
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.settimeout(timeout)
        sock.sendto(packet, (nas_ip, coa_port))

        resp_data, _ = sock.recvfrom(4096)
        sock.close()

        if len(resp_data) < 4:
            return {"success": False, "reason": "CoA response terlalu pendek"}

        resp_code = resp_data[0]
        if resp_code == COA_ACK:
            return {"success": True, "method": "CoA-RFC3576", "code": "CoA-ACK"}
        elif resp_code == COA_NAK:
            # Coba parse Reply-Message dari NAK
            msg = ""
            try:
                pos = 20
                while pos + 2 <= len(resp_data):
                    t = resp_data[pos]
                    l = resp_data[pos + 1]
                    if t == 18:   # Reply-Message
                        msg = resp_data[pos + 2:pos + l].decode("utf-8", errors="replace")
                    pos += l
            except Exception:
                pass
            return {"success": False, "reason": f"CoA-NAK: {msg or 'NAS menolak'}"}
        else:
            return {"success": False, "reason": f"CoA response code tidak dikenal: {resp_code}"}

    except socket.timeout:
        return {"success": False, "reason": f"CoA socket timeout ke {nas_ip}:{coa_port}"}
    except Exception as e:
        return {"success": False, "reason": f"CoA socket error: {e}"}


async def _update_pppoe_profile(username: str, rate_limit: str, device: dict, db) -> dict:
    """
    Fallback: Update PPPoE profile dinamis TANPA kick session.
    Membuat profile 'NOC-BW-<rate>' dan assign ke /ppp/secret user.
    """
    try:
        from mikrotik_api import get_api_client
        mt = get_api_client(device)

        profile_name = f"{NOC_PROFILE_PREFIX}{rate_limit.replace('/', '-')}"

        # Pastikan profile ada (buat jika belum)
        await _ensure_ppp_profile(mt, profile_name, rate_limit)

        # Update profile di /ppp/secret (TIDAK kick session aktif)
        secrets = await mt.list_pppoe_secrets()
        target = next((s for s in secrets if s.get("name") == username), None)

        if target:
            mt_id = target.get(".id") or target.get("id", "")
            if mt_id:
                await mt.update_pppoe_secret(mt_id, {"profile": profile_name})
                logger.info(f"[BW] Profile '{profile_name}' di-assign ke PPPoE secret {username!r} (berlaku saat reconnect)")
                return {"success": True, "method": "profile-update", "profile": profile_name,
                        "note": "Berlaku saat user reconnect (tidak langsung)"}
        else:
            logger.warning(f"[BW] PPPoE secret untuk {username!r} tidak ditemukan di MikroTik")
            return {"success": False, "reason": f"PPPoE secret {username!r} tidak ditemukan"}

    except Exception as e:
        logger.error(f"[BW] Profile update gagal untuk {username!r}: {e}")
        return {"success": False, "reason": str(e)}


async def _ensure_ppp_profile(mt, profile_name: str, rate_limit: str):
    """Buat PPPoE profile dinamis jika belum ada."""
    try:
        profiles = await mt.list_pppoe_profiles() if hasattr(mt, "list_pppoe_profiles") else []
        exists = any(p.get("name") == profile_name for p in profiles)
        if not exists:
            # Rate limit format MikroTik: "Xk/Xk" atau "XM/XM"
            await mt.create_pppoe_profile({
                "name":           profile_name,
                "rate-limit":     rate_limit,
                "comment":        f"NOC-Billing-Pro auto: {rate_limit}",
            })
            logger.info(f"[BW] Profile '{profile_name}' dibuat dengan rate-limit={rate_limit}")
    except Exception as e:
        logger.debug(f"[BW] Gagal buat/cek profile {profile_name}: {e}")
