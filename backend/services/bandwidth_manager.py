"""
bandwidth_manager.py — Zero-Disconnect Bandwidth Management
Mendukung dua mode:
  - Non-RADIUS: edit /queue/simple via MikroTik REST API
  - RADIUS:     kirim CoA-Request (RFC 3576) ke port 3799
"""
import asyncio
import struct
import hashlib
import logging
import socket

logger = logging.getLogger(__name__)

# ── CoA Constants (RFC 3576) ──────────────────────────────────────────────────
COA_REQUEST = 43
COA_ACK     = 44
COA_NAK     = 45

async def set_rate_limit(customer: dict, device: dict, rate_limit: str, db=None) -> dict:
    """
    Ubah rate-limit user PPPoE secara live tanpa disconnect.
    Otomatis pilih metode: CoA (RADIUS) atau Queue Edit (Non-RADIUS).
    """
    username = customer.get("username", "")
    use_radius = device.get("use_radius", False)   # flag di koleksi devices

    if use_radius:
        return await _coa_change_rate(
            nas_ip     = device.get("ip_address"),
            nas_secret = device.get("radius_secret", ""),
            username   = username,
            rate_limit = rate_limit,
        )
    else:
        return await _queue_change_rate(device, username, rate_limit)


async def _queue_change_rate(device: dict, username: str, rate_limit: str) -> dict:
    """Non-RADIUS: Edit /queue/simple live."""
    from mikrotik_api import get_api_client
    try:
        mt = get_api_client(device)
        queues = await mt.list_simple_queues()
        possible_names = [f"<{username}>", f"<pppoe-{username}>", f"<hotspot-{username}>"]
        q = next((q for q in queues if q.get("name") in possible_names), None)
        if q:
            await mt.update_simple_queue(q['.id'], {"max-limit": rate_limit})
            logger.info(f"[BW] Queue '{username}' updated to {rate_limit}")
            return {"success": True, "method": "queue", "rate": rate_limit}
        else:
            logger.warning(f"[BW] Queue untuk '{username}' tidak ditemukan (offline?)")
            return {"success": False, "method": "queue", "reason": "queue not found (user offline)"}
    except Exception as e:
        logger.error(f"[BW] Queue update error for '{username}': {e}")
        return {"success": False, "method": "queue", "reason": str(e)}


async def _coa_change_rate(nas_ip: str, nas_secret: str, username: str, rate_limit: str) -> dict:
    """RADIUS CoA: RFC 3576 Change of Authorization — port 3799."""
    if not nas_ip or not nas_secret:
        return {"success": False, "method": "coa", "reason": "Missing NAS IP or secret"}
    try:
        secret = nas_secret.encode("utf-8")
        pkt_id = 1

        # Build attributes
        user_name_attr = bytes([1, len(username) + 2]) + username.encode()

        # Mikrotik-Rate-Limit VSA (Vendor=14988, Type=8)
        rate_bytes = rate_limit.encode("utf-8")
        vsa_inner  = struct.pack("!I", 14988) + bytes([8, len(rate_bytes) + 2]) + rate_bytes
        vsa_attr   = bytes([26, len(vsa_inner) + 2]) + vsa_inner

        attr_data  = user_name_attr + vsa_attr
        length     = 20 + len(attr_data)

        # Authenticator placeholder (16 zero bytes) untuk kalkulasi
        import os
        auth       = os.urandom(16)
        header     = struct.pack("!BBH", COA_REQUEST, pkt_id, length) + auth
        resp_auth  = hashlib.md5(header + attr_data + secret).digest()
        packet     = struct.pack("!BBH", COA_REQUEST, pkt_id, length) + resp_auth + attr_data

        # Kirim via UDP ke MikroTik port 3799
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
            logger.warning(f"[BW] CoA-NAK/timeout untuk '{username}': code={code}")
            return {"success": False, "method": "coa", "reason": f"CoA-NAK (code={code})"}

    except asyncio.TimeoutError:
        return {"success": False, "method": "coa", "reason": "timeout (port 3799 unreachable?)"}
    except Exception as e:
        logger.error(f"[BW] CoA error for '{username}' @ {nas_ip}: {e}")
        return {"success": False, "method": "coa", "reason": str(e)}


def _udp_send_recv(host: str, port: int, data: bytes) -> bytes:
    """Blocking UDP send/receive (dipanggil via executor)."""
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
        sock.settimeout(5)
        sock.sendto(data, (host, port))
        resp, _ = sock.recvfrom(1024)
        return resp
