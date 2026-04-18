"""
bandwidth_manager.py — Dynamic Bandwidth Management
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Strategi perubahan rate-limit (dieksekusi secara berurutan, berhenti jika berhasil):

1. PPPoE Secret Update + Active Session Drop  ← METODE UTAMA (selalu dicoba)
   Update field `rate-limit` di /ppp/secret lalu kick session aktif.
   Session reconnect otomatis dalam 1-3 detik dengan limit baru.

2. RADIUS CoA (RFC 3576)                      ← FALLBACK (jika CoA port 3799 terbuka)
   Kirim CoA-Request ke MikroTik port 3799.
   Berguna agar tidak perlu disconnect session (zero-disconnect).
   Hanya efektif jika MikroTik bisa dijangkau dari IP server ini.

Note: Queue Simple "dynamic" TIDAK bisa diubah langsung via API,
sehingga metode edit_queue dihapus dari alur utama.
"""
import asyncio
import struct
import hashlib
import logging
import socket
import os

logger = logging.getLogger(__name__)

# ── CoA Constants (RFC 3576) ──────────────────────────────────────────────────
COA_REQUEST = 43
COA_ACK     = 44
COA_NAK     = 45


async def set_rate_limit(customer: dict, device: dict, rate_limit: str, db=None) -> dict:
    """
    Ubah rate-limit user PPPoE.
    Strategi:
      1. Update PPPoE secret rate-limit + kick session aktif (selalu dicoba)
      2. CoA RADIUS jika metode (1) gagal dan CoA dikonfigurasi
    """
    username = customer.get("username", "")

    # ── Metode 1: Update PPPoE Secret + Drop Session (utama) ──
    result = await _pppoe_secret_rate_change(device, username, rate_limit)
    if result.get("success"):
        return result

    logger.warning(f"[BW] PPPoE secret update gagal untuk '{username}', mencoba CoA...")

    # ── Metode 2: CoA RADIUS (fallback, butuh port 3799 terbuka dari server) ──
    has_radius = device.get("radius_secret") and device.get("ip_address")
    if has_radius:
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

    return result  # return last error dari metode 1


async def _pppoe_secret_rate_change(device: dict, username: str, rate_limit: str) -> dict:
    """
    Update rate-limit di /ppp/secret kemudian kick session aktif agar reconnect.
    Session disconnected hanya ~1-3 detik (reconnect otomatis oleh PPPoE klien).
    """
    from mikrotik_api import get_api_client
    try:
        mt = get_api_client(device)

        # Cari secret berdasarkan username
        secrets = await mt.list_pppoe_secrets()
        secret_entry = next((s for s in secrets if s.get("name") == username), None)

        if not secret_entry:
            logger.warning(f"[BW] PPPoE secret '{username}' tidak ditemukan di MikroTik (mungkin RADIUS-managed)")
            return {"success": False, "method": "pppoe_secret", "reason": f"secret '{username}' not found on router"}

        mt_id = secret_entry.get(".id") or secret_entry.get("id", "")
        if not mt_id:
            return {"success": False, "method": "pppoe_secret", "reason": "no .id in secret entry"}

        # Update rate-limit di secret
        await mt.update_pppoe_secret(mt_id, {"rate-limit": rate_limit})
        logger.info(f"[BW] PPPoE secret '{username}' rate-limit diupdate ke {rate_limit}")

        # Kick session aktif agar langsung reconnect dengan limit baru
        removed = await mt.remove_pppoe_active_session(username)
        if removed > 0:
            logger.info(f"[BW] Session '{username}' di-kick ({removed} session) → reconnect dengan limit baru")
        else:
            logger.info(f"[BW] Session '{username}' tidak aktif (limit akan berlaku saat connect berikutnya)")

        return {"success": True, "method": "pppoe_secret", "rate": rate_limit, "sessions_dropped": removed}

    except Exception as e:
        logger.error(f"[BW] PPPoE secret update error untuk '{username}': {e}")
        return {"success": False, "method": "pppoe_secret", "reason": str(e)}


async def _coa_change_rate(nas_ip: str, nas_secret: str, username: str, rate_limit: str) -> dict:
    """RADIUS CoA: RFC 3576 Change of Authorization — port 3799."""
    if not nas_ip or not nas_secret:
        return {"success": False, "method": "coa", "reason": "Missing NAS IP or secret"}
    try:
        secret = nas_secret.encode("utf-8")
        pkt_id = 1

        # Build RADIUS attributes
        user_name_attr = bytes([1, len(username) + 2]) + username.encode()

        # Mikrotik-Rate-Limit VSA (Vendor=14988, Type=8)
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
            return {"success": False, "method": "coa", "reason": f"CoA-NAK (code={code})"}

    except asyncio.TimeoutError:
        logger.warning(f"[BW] CoA timeout untuk '{username}' @ {nas_ip}:3799 (port unreachable atau NAT memblok)")
        return {"success": False, "method": "coa", "reason": "timeout (port 3799 unreachable)"}
    except Exception as e:
        logger.error(f"[BW] CoA error untuk '{username}' @ {nas_ip}: {e}")
        return {"success": False, "method": "coa", "reason": str(e)}


def _udp_send_recv(host: str, port: int, data: bytes) -> bytes:
    """Blocking UDP send/receive (dipanggil via executor)."""
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
        sock.settimeout(5)
        sock.sendto(data, (host, port))
        resp, _ = sock.recvfrom(1024)
        return resp
