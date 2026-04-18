"""
bandwidth_manager.py — Dynamic Bandwidth Management
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Strategi perubahan rate-limit:

1. UTAMA: Create/reuse PPPoE profile dinamis → assign ke secret user → kick session
   - Buat profile "NOC-BW-<rate>" jika belum ada (e.g. "NOC-BW-25M/25M")
   - Update field `profile` di /ppp/secret
   - Kick active session → user reconnect dalam 1-3 detik dengan limit baru

2. FALLBACK: RADIUS CoA (RFC 3576) — hanya jika port 3799 dapat dijangkau dari server

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


async def set_rate_limit(customer: dict, device: dict, rate_limit: str, db=None) -> dict:
    """
    Ubah rate-limit user PPPoE secara live.
    Metode: Update profile PPPoE + kick session aktif.
    """
    username = customer.get("username", "")

    # ── Metode 1: Profile-based update (utama) ──
    result = await _profile_rate_change(device, username, rate_limit)
    if result.get("success"):
        return result

    logger.warning(f"[BW] Profile update gagal untuk '{username}' ({result.get('reason')}), mencoba CoA...")

    # ── Metode 2: CoA RADIUS (fallback) ──
    if device.get("radius_secret") and device.get("ip_address"):
        coa_result = await _coa_change_rate(
            nas_ip     = device.get("ip_address"),
            nas_secret = device.get("radius_secret", ""),
            username   = username,
            rate_limit = rate_limit,
        )
        if coa_result.get("success"):
            return coa_result
        logger.warning(f"[BW] CoA juga gagal untuk '{username}': {coa_result.get('reason')}")
        return coa_result

    return result


async def _profile_rate_change(device: dict, username: str, rate_limit: str) -> dict:
    """
    1. Pastikan ada PPPoE profile dengan rate-limit ini, buat jika belum ada.
    2. Assign profile ke secret user.
    3. Kick active session → reconnect dengan limit baru.
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
            # User RADIUS-only: tidak ada secret di router, tapi bisa tetap kick
            logger.info(f"[BW] '{username}' tidak ada di /ppp/secret (RADIUS-managed), akan kick session saja")

        # ── Kick session aktif ────────────────────────────────────────────────
        removed = await mt.remove_pppoe_active_session(username)
        if removed > 0:
            logger.info(f"[BW] Session '{username}' di-kick → reconnect dengan profile '{profile_name}'")
        else:
            logger.info(f"[BW] '{username}' tidak ada session aktif (limit berlaku saat connect berikutnya)")

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


async def _coa_change_rate(nas_ip: str, nas_secret: str, username: str, rate_limit: str) -> dict:
    """RADIUS CoA: RFC 3576 Change of Authorization — port 3799."""
    if not nas_ip or not nas_secret:
        return {"success": False, "method": "coa", "reason": "Missing NAS IP or secret"}
    try:
        secret = nas_secret.encode("utf-8")
        pkt_id = 1

        user_name_attr = bytes([1, len(username) + 2]) + username.encode()
        rate_bytes = rate_limit.encode("utf-8")
        vsa_inner  = struct.pack("!I", 14988) + bytes([8, len(rate_bytes) + 2]) + rate_bytes
        vsa_attr   = bytes([26, len(vsa_inner) + 2]) + vsa_inner

        attr_data  = user_name_attr + vsa_attr
        length     = 20 + len(attr_data)

        auth       = os.urandom(16)
        header     = struct.pack("!BBH", COA_REQUEST, pkt_id, length) + auth
        resp_auth  = hashlib.md5(header + attr_data + secret).digest()
        packet     = struct.pack("!BBH", COA_REQUEST, pkt_id, length) + resp_auth + attr_data

        loop = asyncio.get_event_loop()
        response = await asyncio.wait_for(
            loop.run_in_executor(None, _udp_send_recv, nas_ip, 3799, packet),
            timeout=5.0
        )

        if response and response[0] == COA_ACK:
            logger.info(f"[BW] CoA-ACK untuk '{username}' rate={rate_limit}")
            return {"success": True, "method": "coa", "rate": rate_limit}
        else:
            code = response[0] if response else None
            logger.warning(f"[BW] CoA-NAK untuk '{username}': code={code}")
            return {"success": False, "method": "coa", "reason": f"CoA-NAK code={code}"}

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
