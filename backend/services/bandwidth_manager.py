"""
bandwidth_manager.py — Dynamic Bandwidth Management
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Strategi perubahan rate-limit (TANPA memutuskan koneksi user):

1. UTAMA: RADIUS CoA (RFC 3576) — ubah rate-limit LIVE tanpa kick
   - Kirim CoA ke NAS MikroTik port 3799
   - User tidak merasakan putus koneksi sama sekali

2. FALLBACK: Update PPPoE profile dinamis → assign ke secret user (TANPA kick)
   - Buat profile "NOC-BW-<rate>" jika belum ada
   - Update field `profile` di /ppp/secret
   - User akan mendapatkan limit baru saat reconnect (tidak langsung)
   - TIDAK pernah kick session kecuali diminta secara eksplisit

Note: Dynamic Simple Queue TIDAK bisa diubah langsung (RouterOS melarang).
"""
import asyncio
import struct
import hashlib
import logging
import socket
import os

logger = logging.getLogger(__name__)

COA_REQUEST = 43
COA_ACK     = 44
COA_NAK     = 45

# Prefix untuk profile dinamis yang dibuat oleh NOC Billing
NOC_PROFILE_PREFIX = "NOC-BW-"


async def set_rate_limit(customer: dict, device: dict, rate_limit: str, db=None, framed_ip: str = "") -> dict:
    """
    Ubah rate-limit user PPPoE TANPA memutuskan koneksi (no kick).
    
    Prioritas:
    1. RADIUS CoA — berlaku instan tanpa putus koneksi
    2. Profile update — berlaku saat reconnect berikutnya (fallback)
    """
    username = customer.get("username", "")

    # ── Metode 1: CoA RADIUS (Live Update tanpa kick) ──
    if device.get("radius_secret") and device.get("ip_address"):
        coa_result = await _coa_change_rate(
            nas_ip     = device.get("ip_address"),
            nas_secret = device.get("radius_secret", ""),
            username   = username,
            rate_limit = rate_limit,
            framed_ip  = framed_ip,
        )
        if coa_result.get("success"):
            logger.info(f"[BW] CoA berhasil untuk '{username}' → {rate_limit} (no kick)")
            return coa_result

        logger.warning(f"[BW] CoA gagal untuk '{username}': {coa_result.get('reason')} — fallback ke profile")

    # ── Metode 2: Update Profile (tanpa kick) — sebagai fallback ──
    # Ini memastikan kalaupun router direboot/reconnect, profile sudah tersimpan
    profile_result = await _profile_rate_change(device, username, rate_limit, kick=False)
    return profile_result


async def _profile_rate_change(device: dict, username: str, rate_limit: str, kick: bool = False) -> dict:
    """
    1. Pastikan ada PPPoE profile dengan rate-limit ini, buat jika belum ada.
    2. Assign profile ke secret user.
    3. Kick active session HANYA jika kick=True (default: False = tidak disconnect).
    """
    from mikrotik_api import get_api_client
    try:
        mt = get_api_client(device)

        # Normalisasi format rate_limit (25M/25M atau 25M)
        if "/" not in rate_limit:
            rate_limit = f"{rate_limit}/{rate_limit}"

        profile_name = f"{NOC_PROFILE_PREFIX}{rate_limit}"

        # ── Cari atau buat profile dengan rate-limit ini ──
        profiles = await mt.list_pppoe_profiles()
        profile_entry = next(
            (p for p in profiles if p.get("name") == profile_name or p.get("rate-limit") == rate_limit),
            None
        )

        if not profile_entry:
            # Buat profile baru
            logger.info(f"[BW] Membuat PPPoE profile baru: {profile_name} rate-limit={rate_limit}")
            try:
                await _create_pppoe_profile(mt, profile_name, rate_limit, profiles)
                # Ambil lagi setelah create
                profiles = await mt.list_pppoe_profiles()
                profile_entry = next((p for p in profiles if p.get("name") == profile_name), None)
            except Exception as e:
                logger.error(f"[BW] Gagal buat profile {profile_name}: {e}")
                return {"success": False, "method": "profile", "reason": f"cannot create profile: {e}"}

        if not profile_entry:
            return {"success": False, "method": "profile", "reason": f"profile {profile_name} not found after create"}

        # ── Update secret user ke profile baru ──
        secrets = await mt.list_pppoe_secrets()
        secret_entry = next((s for s in secrets if s.get("name") == username), None)

        if secret_entry:
            mt_id = secret_entry.get(".id") or secret_entry.get("id", "")
            if mt_id:
                await mt.update_pppoe_secret(mt_id, {"profile": profile_name})
                logger.info(f"[BW] Secret '{username}' profile diubah ke '{profile_name}'")
        else:
            # User RADIUS-only: tidak ada secret di router
            logger.info(f"[BW] '{username}' tidak ada di /ppp/secret (RADIUS-managed)")

        # ── Kick session aktif HANYA jika diminta secara eksplisit ─────────
        removed = 0
        if kick:
            removed = await mt.remove_pppoe_active_session(username)
            if removed > 0:
                logger.info(f"[BW] Session '{username}' di-kick → reconnect dengan profile '{profile_name}'")
            else:
                logger.info(f"[BW] '{username}' tidak ada session aktif")

        return {"success": True, "method": "profile", "rate": rate_limit,
                "profile": profile_name, "sessions_dropped": removed}

    except Exception as e:
        logger.error(f"[BW] Profile rate change error untuk '{username}': {e}")
        return {"success": False, "method": "profile", "reason": str(e)}


async def _create_pppoe_profile(mt, profile_name: str, rate_limit: str, existing_profiles: list):
    """Buat PPPoE profile baru berdasarkan profile default yang sudah ada."""
    # Ambil template dari profile default (ambil field yang aman)
    base = next((p for p in existing_profiles if p.get("name") != "default" and "rate-limit" in p), None)
    if not base:
        base = next((p for p in existing_profiles if p.get("name") == "default"), {})

    data = {"name": profile_name, "rate-limit": rate_limit}
    # Salin field aman dari base profile
    for f in ["local-address", "remote-address", "change-tcp-mss"]:
        if f in base and base[f]:
            data[f] = base[f]

    # Gunakan _set_resource langsung via asyncio.to_thread untuk Legacy API
    # Fallback ke _add_resource
    import asyncio
    if hasattr(mt, '_add_resource'):
        await asyncio.to_thread(mt._add_resource, "/ppp/profile", data)
    else:
        # REST API
        await mt._async_req("PUT", "ppp/profile", data)


async def _coa_change_rate(nas_ip: str, nas_secret: str, username: str, rate_limit: str, framed_ip: str = "") -> dict:
    """RADIUS CoA: RFC 3576 Change of Authorization — port 3799.
    
    Menyertakan Framed-IP-Address jika tersedia agar MikroTik dapat
    mengidentifikasi sesi dengan tepat tanpa error 'Radius with no ip provided'.
    """
    if not nas_ip or not nas_secret:
        return {"success": False, "method": "coa", "reason": "Missing NAS IP or secret"}
    try:
        from pyrad.client import Client
        from pyrad.dictionary import Dictionary
        from pyrad.packet import CoAACK
        import io
        import asyncio

        # Inline dictionary specifically for MikroTik Rate Limit VSA
        dict_str = """
ATTRIBUTE User-Name 1 string
ATTRIBUTE NAS-IP-Address 4 ipaddr
ATTRIBUTE Framed-IP-Address 8 ipaddr
ATTRIBUTE Message-Authenticator 80 octets
VENDOR MikroTik 14988
BEGIN-VENDOR MikroTik
ATTRIBUTE MikroTik-Rate-Limit 8 string
END-VENDOR MikroTik
        """
        d = Dictionary(io.StringIO(dict_str))
        client = Client(server=nas_ip, secret=nas_secret.encode('utf-8'), dict=d)
        client.coaport = 3799

        req = client.CreateCoAPacket(User_Name=username)
        req.AddAttribute("MikroTik-Rate-Limit", rate_limit)
        
        # Sertakan Framed-IP-Address jika tersedia — mencegah 'Radius with no ip provided'
        if framed_ip:
            try:
                req.AddAttribute("Framed-IP-Address", framed_ip)
                logger.debug(f"[BW] CoA {username}: Framed-IP-Address={framed_ip}")
            except Exception as ip_err:
                logger.warning(f"[BW] Gagal tambah Framed-IP-Address '{framed_ip}': {ip_err}")

        loop = asyncio.get_event_loop()

        # client.SendPacket is blocking, run in executor
        reply = await asyncio.wait_for(
            loop.run_in_executor(None, client.SendPacket, req),
            timeout=5.0
        )

        if reply.code == CoAACK:
            logger.info(f"[BW] CoA-ACK untuk '{username}' rate={rate_limit}")
            return {"success": True, "method": "coa", "rate": rate_limit}
        else:
            logger.warning(f"[BW] CoA-NAK untuk '{username}': code={reply.code}")
            return {"success": False, "method": "coa", "reason": f"CoA-NAK code={reply.code}"}

    except asyncio.TimeoutError:
        logger.warning(f"[BW] CoA timeout untuk '{username}' @ {nas_ip}:3799")
        return {"success": False, "method": "coa", "reason": "timeout (port 3799 unreachable)"}
    except Exception as e:
        logger.error(f"[BW] CoA error untuk '{username}' @ {nas_ip}: {e}")
        return {"success": False, "method": "coa", "reason": str(e)}


def _udp_send_recv(host: str, port: int, data: bytes) -> bytes:
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
        sock.settimeout(5)
        sock.sendto(data, (host, port))
        resp, _ = sock.recvfrom(1024)
        return resp
