"""
radius_server.py — NOC Billing Pro (asyncio, PAP + CHAP support)
═══════════════════════════════════════════════════════════════════════════════
Perbaikan berdasarkan audit:
  FIX #4:  Baca NAS-Port-Type untuk routing langsung PPPoE vs Hotspot
  FIX #5:  ACCT memproses PPPoE (simpan session, update bytes untuk FUP)
  FIX #7:  Simpan Acct-Session-Id ke radius_sessions collection
  FIX #8:  Handle Acct-Start, Acct-Stop, Acct-Interim-Update semua tipe
  FIX #9:  Brute-force protection per IP (block 5 menit jika 10x gagal)

Adopsi pola MixRadius/FreeRADIUS:
  - Acct-Interim-Interval = 300 detik dikirim di setiap Access-Accept
    → MikroTik akan otomatis mengirim update bytes setiap 5 menit
    → FUP monitoring bisa real-time tanpa polling API MikroTik
  - radius_sessions collection untuk tracking sesi aktif
═══════════════════════════════════════════════════════════════════════════════
"""

import asyncio
import logging
import struct
import hashlib
import uuid
from datetime import datetime, timezone, timedelta

logger = logging.getLogger(__name__)

# ── Global State ───────────────────────────────────────────────────────────────
_db_pool = None
_global_secret = b"testing123"
_allowed_hosts: dict = {}  # {ip: secret_bytes}

# ── RADIUS Packet Codes ────────────────────────────────────────────────────────
ACCESS_REQUEST  = 1
ACCESS_ACCEPT   = 2
ACCESS_REJECT   = 3
ACCT_REQUEST    = 4
ACCT_RESPONSE   = 5

# ── RADIUS Attribute IDs ───────────────────────────────────────────────────────
ATTR_USER_NAME              = 1
ATTR_USER_PASSWORD          = 2    # PAP
ATTR_CHAP_PASSWORD          = 3    # CHAP: 1-byte ID + 16-byte MD5
ATTR_NAS_IP_ADDRESS         = 4
ATTR_FRAMED_IP_ADDRESS      = 8
ATTR_REPLY_MESSAGE          = 18
ATTR_CALLED_STATION_ID      = 30
ATTR_ACCT_STATUS_TYPE       = 40
ATTR_ACCT_INPUT_OCTETS      = 42   # Bytes upload dari user
ATTR_ACCT_OUTPUT_OCTETS     = 43   # Bytes download ke user
ATTR_ACCT_SESSION_ID        = 44   # Session ID unik dari NAS
ATTR_ACCT_SESSION_TIME      = 46   # Durasi sesi dalam detik
ATTR_ACCT_INTERIM_INTERVAL  = 85   # Kirim ke MikroTik: interval update (detik)
ATTR_CHAP_CHALLENGE         = 60   # Optional CHAP challenge
ATTR_NAS_PORT_TYPE          = 61   # Virtual=5 (PPPoE), Ethernet=15, Wireless=19 (Hotspot)

# NAS-Port-Type values
NAS_PORT_VIRTUAL   = 5    # PPPoE
NAS_PORT_ETHERNET  = 15   # Hotspot wired
NAS_PORT_WIRELESS  = 19   # Hotspot wireless

# Accounting Status types
ACCT_STATUS_START   = 1
ACCT_STATUS_STOP    = 2
ACCT_STATUS_INTERIM = 3
ACCT_STATUS_ALIVE   = 3   # Alias untuk Interim-Update

# ── Brute-Force Protection (FIX #9) ───────────────────────────────────────────
_fail_cache: dict = {}   # {ip: {"fails": int, "blocked_until": datetime}}
MAX_FAILS_PER_IP    = 10
BLOCK_DURATION_SECS = 300   # 5 menit

def _is_blocked(ip: str) -> bool:
    """Cek apakah IP terblokir karena terlalu banyak kegagalan auth."""
    entry = _fail_cache.get(ip)
    if not entry:
        return False
    if entry["fails"] >= MAX_FAILS_PER_IP:
        if datetime.now() < entry["blocked_until"]:
            return True
        # Block sudah expired, reset
        _fail_cache.pop(ip, None)
    return False

def _record_fail(ip: str):
    """Catat kegagalan autentikasi dari IP ini."""
    entry = _fail_cache.setdefault(ip, {"fails": 0, "blocked_until": datetime.now()})
    entry["fails"] += 1
    if entry["fails"] >= MAX_FAILS_PER_IP:
        entry["blocked_until"] = datetime.now() + timedelta(seconds=BLOCK_DURATION_SECS)
        logger.warning(f"[RADIUS] IP {ip} diblokir selama {BLOCK_DURATION_SECS}s karena {entry['fails']}x gagal login")

def _record_success(ip: str):
    """Reset counter kegagalan setelah login sukses."""
    _fail_cache.pop(ip, None)


# ── Packet Parser & Builder ────────────────────────────────────────────────────
def _parse_packet(data: bytes) -> dict | None:
    if len(data) < 20:
        return None
    code, pkt_id, length = struct.unpack("!BBH", data[:4])
    auth = data[4:20]
    attrs = {}
    pos = 20
    while pos + 2 <= min(length, len(data)):
        t = data[pos]
        l = data[pos + 1]
        if l < 2:
            break
        attrs.setdefault(t, []).append(data[pos + 2: pos + l])
        pos += l
    return {"code": code, "id": pkt_id, "auth": auth, "attrs": attrs}


def _build_reply(code: int, pkt_id: int, req_auth: bytes, secret: bytes, attrs_list: list) -> bytes:
    attr_bytes = b"".join(bytes([t, len(v) + 2]) + v for t, v in attrs_list)
    length = 20 + len(attr_bytes)
    header = struct.pack("!BBH", code, pkt_id, length) + req_auth
    resp_auth = hashlib.md5(header + attr_bytes + secret).digest()
    return struct.pack("!BBH", code, pkt_id, length) + resp_auth + attr_bytes


def _get_secret(nas_ip: str) -> bytes:
    return _allowed_hosts.get(nas_ip, _global_secret)


def _get_attr_str(attrs: dict, attr_id: int, default: str = "") -> str:
    raw = attrs.get(attr_id, [None])[0]
    if raw is None:
        return default
    return raw.decode("utf-8", errors="replace")


def _get_attr_int(attrs: dict, attr_id: int, default: int = 0) -> int:
    raw = attrs.get(attr_id, [b"\x00\x00\x00\x00"])[0]
    if not raw:
        return default
    try:
        return struct.unpack("!I", raw.ljust(4, b"\x00")[:4])[0]
    except Exception:
        return default


def _decrypt_pap(cipher: bytes, authenticator: bytes, secret: bytes) -> str:
    result = bytearray()
    prev = authenticator
    for i in range(0, len(cipher), 16):
        chunk = cipher[i: i + 16]
        pad = hashlib.md5(secret + prev).digest()
        result.extend(a ^ b for a, b in zip(pad, chunk))
        prev = chunk
    return result.rstrip(b"\x00").decode("utf-8", errors="replace")


def _build_rate_limit_string(pkg: dict) -> str:
    up = str(pkg.get("speed_up", "")).strip()
    down = str(pkg.get("speed_down", "")).strip()
    bl_u = str(pkg.get("burst_limit_up", "")).strip()
    bl_d = str(pkg.get("burst_limit_down", "")).strip()
    bt_u = str(pkg.get("burst_threshold_up", "")).strip()
    bt_d = str(pkg.get("burst_threshold_down", "")).strip()
    time_u = str(pkg.get("burst_time_up", "")).strip()
    time_d = str(pkg.get("burst_time_down", "")).strip()
    
    rate = f"{up}/{down}" if up and down else (up or down)
    burst = f"{bl_u}/{bl_d}" if bl_u and bl_d else (bl_u or bl_d)
    thresh = f"{bt_u}/{bt_d}" if bt_u and bt_d else (bt_u or bt_d)
    time = f"{time_u}/{time_d}" if time_u and time_d else (time_u or time_d)
    
    parts = []
    if rate: parts.append(rate)
    if burst:
        parts.append(burst)
        if thresh:
            parts.append(thresh)
            if time: parts.append(time)
    return " ".join(parts)

def _build_vsa_rate_limit(rate_str: str) -> bytes:
    """Build Vendor-Specific Attribute (VSA) untuk Mikrotik-Rate-Limit."""
    rate_val = rate_str.encode("utf-8")
    # VSA format: vendor-id (4 bytes) + vendor-type (1) + vendor-length (1) + value
    return struct.pack("!I", 14988) + bytes([8, len(rate_val) + 2]) + rate_val


def _build_acct_interim_interval(seconds: int = 300) -> tuple:
    """Build atribut Acct-Interim-Interval untuk dikirim di Access-Accept."""
    return (ATTR_ACCT_INTERIM_INTERVAL, struct.pack("!I", seconds))


# ── RADIUS Protocol Handler ────────────────────────────────────────────────────
class RADIUSProtocol(asyncio.DatagramProtocol):
    def __init__(self, db):
        self._db = db
        self._transport = None

    def connection_made(self, transport):
        self._transport = transport
        logger.info("RADIUS UDP transport ready")

    def error_received(self, exc):
        logger.error(f"RADIUS UDP error: {exc}")

    def datagram_received(self, data: bytes, addr: tuple):
        asyncio.ensure_future(self._handle(data, addr))

    async def _handle(self, data: bytes, addr: tuple):
        pkt = _parse_packet(data)
        if not pkt:
            return

        # Tentukan nas_ip berdasarkan isi atribut NAS-IP-Address (Type 4) untuk menembus NAT Server VPN
        ATTR_NAS_IP_ADDRESS = 4
        logical_ip = None
        if ATTR_NAS_IP_ADDRESS in pkt["attrs"]:
            ip_raw = pkt["attrs"][ATTR_NAS_IP_ADDRESS][0]
            if ip_raw and len(ip_raw) == 4:
                logical_ip = ".".join(str(b) for b in ip_raw)
        
        nas_ip = logical_ip if logical_ip else addr[0]

        # FIX #9: Cek brute-force block sebelum proses apapun
        if _is_blocked(nas_ip):
            logger.warning(f"[RADIUS] Request dari {nas_ip} (addr={addr[0]}) DIABAIKAN (brute-force block)")
            return

        secret = _get_secret(nas_ip)
        
        logger.info(f"RADIUS pkt from {nas_ip} (via {addr[0]}): code={pkt['code']} id={pkt['id']}")

        if pkt["code"] == ACCESS_REQUEST:
            await self._auth(pkt, addr, secret)
        elif pkt["code"] == ACCT_REQUEST:
            await self._acct(pkt, addr, secret)

    # ── Authentication Handler ────────────────────────────────────────────────
    async def _auth(self, pkt: dict, addr: tuple, secret: bytes):
        nas_ip = addr[0]
        pid, req_auth, attrs = pkt["id"], pkt["auth"], pkt["attrs"]

        uname     = _get_attr_str(attrs, ATTR_USER_NAME)
        pap_raw   = attrs.get(ATTR_USER_PASSWORD, [None])[0]
        chap_raw  = attrs.get(ATTR_CHAP_PASSWORD, [None])[0]
        chap_chal = attrs.get(ATTR_CHAP_CHALLENGE, [None])[0]

        # FIX #4: Baca NAS-Port-Type untuk routing langsung tanpa tebak-tebakan
        nas_port_type = _get_attr_int(attrs, ATTR_NAS_PORT_TYPE, default=NAS_PORT_VIRTUAL)
        is_pppoe_req   = (nas_port_type == NAS_PORT_VIRTUAL)
        is_hotspot_req = (nas_port_type in (NAS_PORT_ETHERNET, NAS_PORT_WIRELESS))

        method = "PAP" if pap_raw else ("CHAP" if chap_raw else "NONE")
        logger.info(f"RADIUS AUTH [{method}] user={uname!r} NAS-Port-Type={nas_port_type} "
                    f"({'PPPoE' if is_pppoe_req else 'Hotspot' if is_hotspot_req else 'Unknown'})")

        def reject(msg: bytes):
            _record_fail(nas_ip)
            r = _build_reply(ACCESS_REJECT, pid, req_auth, secret, [(ATTR_REPLY_MESSAGE, msg)])
            self._transport.sendto(r, addr)

        def accept(attrs_list=None):
            """Kirim Access-Accept dengan Acct-Interim-Interval 5 menit (pola MixRadius)."""
            if attrs_list is None:
                attrs_list = []
            # Tambahkan Acct-Interim-Interval = 300 detik agar MikroTik otomatis
            # mengirim update bytes setiap 5 menit (FUP real-time tanpa polling API)
            attrs_list.append(_build_acct_interim_interval(300))
            r = _build_reply(ACCESS_ACCEPT, pid, req_auth, secret, attrs_list)
            self._transport.sendto(r, addr)
            _record_success(nas_ip)
            logger.info(f"RADIUS ACCEPT: {uname!r} ({len(attrs_list)} attrs, interim=300s)")

        # Jangan reject NONE di awal, MAC-Auth mungkin tidak mengirim password ATR

        # ── FIX #4: Routing Dinamis (Bypass cacat NAS-Port-Type MikroTik) ────────────
        # MikroTik sering mengirim NAS-Port-Type=15 (Hotspot/Ethernet) untuk PPPoE!
        # Deteksi paling akurat PPPoE adalah dari Framed-Protocol = 1 (PPP)
        ATTR_FRAMED_PROTOCOL = 7
        framed_protocol = _get_attr_int(attrs, ATTR_FRAMED_PROTOCOL, default=0)
        is_ppp_framed = (framed_protocol == 1)

        if self._db is None:
            return reject(b"DB unavailable")

        try:
            # 1. Coba cari di customers (PPPoE/Broadband) lebih prioritas jika is_ppp_framed
            customer = await self._db.customers.find_one({"username": uname, "active": True})
            voucher = await self._db.hotspot_vouchers.find_one({"username": uname})

            if is_ppp_framed and customer:
                # 100% PPPoE
                return await self._auth_pppoe(customer, uname, pid, req_auth, secret,
                                              method, pap_raw, chap_raw, chap_chal, addr, reject, accept)
            
            if voucher:
                # 100% Hotspot Voucher
                return await self._auth_hotspot(voucher, uname, pid, req_auth, secret,
                                                method, pap_raw, chap_raw, chap_chal, addr, reject, accept)

            # Jika tidak ada marker khusus, route berdasarkan temuan DB
            if customer:
                return await self._auth_pppoe(customer, uname, pid, req_auth, secret,
                                              method, pap_raw, chap_raw, chap_chal, addr, reject, accept)

            # Tidak ditemukan di mana-mana
            logger.info(f"RADIUS REJECT: {uname!r} tidak ditemukan di customers maupun vouchers")
            return reject(b"Voucher or User not found")
        except Exception as e:
            logger.error(f"DB error (Auth lookup): {e}")
            return reject(b"Auth lookup error")


    # ── PPPoE Authentication ──────────────────────────────────────────────────
    async def _auth_pppoe(self, customer: dict, uname: str, pid: int, req_auth: bytes,
                          secret: bytes, method: str, pap_raw, chap_raw, chap_chal,
                          addr: tuple, reject, accept):
        db_pwd = customer.get("password", "")
        auth_ok = False

        if method == "PAP" and pap_raw:
            try:
                plain = _decrypt_pap(pap_raw, req_auth, secret)
                auth_ok = (plain == db_pwd)
            except Exception as e:
                logger.warning(f"PPPoE PAP decrypt fail: {e}")
                return reject(b"Auth error")
        elif method == "CHAP" and chap_raw:
            if len(chap_raw) < 17:
                return reject(b"Bad CHAP packet")
            chap_id   = chap_raw[0:1]
            chap_resp = chap_raw[1:17]
            challenge = chap_chal if chap_chal else req_auth
            e1 = hashlib.md5(chap_id + db_pwd.encode("utf-8") + challenge).digest()
            auth_ok = (e1 == chap_resp)
        elif method == "NONE":
            # Jika klien tidak kirim password, cocokkan jika password di DB kosong atau sama dengan username (MAC-Auth)
            auth_ok = (db_pwd == "" or db_pwd == uname)
            logger.debug(f"PPPoE NONE method (No Password) auth_ok={auth_ok} for {uname!r}")
        else:
            return reject(b"Unsupported auth method")

        if not auth_ok:
            logger.info(f"RADIUS PPPoE REJECT: password salah untuk {uname!r}")
            return reject(b"Wrong password")

        # Cek billing: tolak jika ada overdue invoice
        try:
            if self._db is not None:
                overdue = await self._db.invoices.find_one({
                    "customer_id": customer.get("id", ""),
                    "status": "overdue",
                })
                if overdue:
                    logger.info(f"RADIUS PPPoE REJECT: {uname!r} ada tagihan overdue ({overdue.get('invoice_number')})")
                    return reject(b"Tagihan belum dibayar")
        except Exception as e:
            logger.error(f"PPPoE billing check error: {e}")

        # Build reply attributes
        reply_attrs = []
        try:
            if self._db is not None:
                pkg = await self._db.billing_packages.find_one({"id": customer.get("package_id", "")})

                # Override rate: Night Mode / Booster / FUP sudah di-set oleh scheduler
                override_rate = customer.get("current_rate_limit", "")
                rate_str = None

                if override_rate:
                    rate_str = override_rate
                    logger.info(f"RADIUS PPPoE: rate OVERRIDE '{rate_str}' untuk {uname!r}")
                elif pkg:
                    rate_str = _build_rate_limit_string(pkg)
                    if rate_str:
                        logger.info(f"RADIUS: rate `{rate_str}`")

                if rate_str:
                    reply_attrs.append((26, _build_vsa_rate_limit(rate_str)))

                # Framed-Pool
                pool_cfg = await self._db.system_settings.find_one({"_id": "pppoe_pool_config"})
                pool_name = (pool_cfg.get("pool_name") if pool_cfg else None) or "pppoe-pool"
                reply_attrs.append((88, pool_name.encode("utf-8")))
                logger.info(f"RADIUS PPPoE: Framed-Pool '{pool_name}' untuk {uname!r}")

        except Exception as e:
            logger.error(f"PPPoE VSA build error: {e}")

        accept(reply_attrs)

    # ── Hotspot Authentication ────────────────────────────────────────────────
    async def _auth_hotspot(self, voucher: dict, uname: str, pid: int, req_auth: bytes,
                            secret: bytes, method: str, pap_raw, chap_raw, chap_chal,
                            addr: tuple, reject, accept):
        db_pwd = voucher.get("password", "")
        auth_ok = False

        if method == "PAP":
            try:
                plain = _decrypt_pap(pap_raw, req_auth, secret)
                auth_ok = (plain == db_pwd)
            except Exception as e:
                logger.warning(f"Hotspot PAP decrypt fail: {e}")
                return reject(b"Auth error")
        elif method == "NONE":
            # MAC-Auth sering tidak mengirim atribut password sama sekali
            auth_ok = (db_pwd == "" or db_pwd == uname)
            logger.debug(f"Hotspot NONE method (MAC-Auth) auth_ok={auth_ok} for {uname!r}")
        else:
            # CHAP — implementasi multi-variasi untuk kompatibilitas MikroTik HTTP login
            if not chap_raw or len(chap_raw) < 17:
                return reject(b"Bad CHAP packet")
            chap_id   = chap_raw[0:1]
            chap_resp = chap_raw[1:17]
            challenge = chap_chal if chap_chal else req_auth
            chap_id_str = chap_id.hex()

            logger.debug(f"CHAP DEBUG: id={chap_id.hex()} challenge={challenge.hex()[:16]}... db_pwd={db_pwd!r}")

            # Variasi 1: Standard CHAP RFC2865
            e1 = hashlib.md5(chap_id + db_pwd.encode("utf-8") + challenge).digest()
            if e1 == chap_resp:
                auth_ok = True
                logger.debug("CHAP ok: v1 standard RFC2865")

            # Variasi 2: MikroTik HTTP CHAP (browser: hexMD5(chapId+pwd+challenge))
            if not auth_ok:
                hex_browser = hashlib.md5(
                    (chap_id_str + db_pwd + challenge.hex()).encode("latin-1")
                ).hexdigest()
                e2 = hashlib.md5(chap_id + hex_browser.encode("latin-1") + challenge).digest()
                if e2 == chap_resp:
                    auth_ok = True
                    logger.debug("CHAP ok: v2 MikroTik HTTP hexMD5")

            # Variasi 3: chapId sebagai raw byte
            if not auth_ok:
                hex_browser3 = hashlib.md5(chap_id + db_pwd.encode("utf-8") + challenge).hexdigest()
                e3 = hashlib.md5(chap_id + hex_browser3.encode("latin-1") + challenge).digest()
                if e3 == chap_resp:
                    auth_ok = True
                    logger.debug("CHAP ok: v3 raw chapId hexMD5")

            # Variasi 4: username sebagai password (fallback)
            if not auth_ok and db_pwd != uname:
                e4 = hashlib.md5(chap_id + uname.encode("utf-8") + challenge).digest()
                if e4 == chap_resp:
                    auth_ok = True
                    logger.debug("CHAP ok: v4 username=password")

        if not auth_ok:
            logger.info(f"RADIUS Hotspot REJECT: password salah untuk {uname!r}")
            return reject(b"Wrong password")

        if voucher.get("status") == "expired":
            logger.info(f"RADIUS Hotspot REJECT: {uname!r} expired")
            return reject(b"Voucher expired")

        # Build rate-limit VSA dari package
        reply_attrs = []
        try:
            profile_name = voucher.get("profile", "")
            if profile_name and self._db is not None:
                pkg = await self._db.billing_packages.find_one({
                    "$or": [{"name": profile_name}, {"id": profile_name}]
                })
                if pkg:
                    rate_str = _build_rate_limit_string(pkg)
                    if rate_str:
                        reply_attrs.append((26, _build_vsa_rate_limit(rate_str)))
                        logger.info(f"RADIUS Hotspot: rate '{rate_str}' untuk {uname!r}")
        except Exception as e:
            logger.error(f"Hotspot VSA build error: {e}")

        accept(reply_attrs)

    # ── Accounting Handler (FIX #5 #7 #8) ────────────────────────────────────
    async def _acct(self, pkt: dict, addr: tuple, secret: bytes):
        nas_ip = addr[0]
        pid, req_auth, attrs = pkt["id"], pkt["auth"], pkt["attrs"]

        # ACK segera (jangan buat NAS menunggu)
        self._transport.sendto(
            _build_reply(ACCT_RESPONSE, pid, req_auth, secret, []), addr
        )

        uname      = _get_attr_str(attrs, ATTR_USER_NAME)
        stype      = _get_attr_int(attrs, ATTR_ACCT_STATUS_TYPE)
        session_id = _get_attr_str(attrs, ATTR_ACCT_SESSION_ID)
        bytes_in   = _get_attr_int(attrs, ATTR_ACCT_INPUT_OCTETS)    # Upload dari user
        bytes_out  = _get_attr_int(attrs, ATTR_ACCT_OUTPUT_OCTETS)   # Download ke user
        sess_time  = _get_attr_int(attrs, ATTR_ACCT_SESSION_TIME)
        nas_port_type = _get_attr_int(attrs, ATTR_NAS_PORT_TYPE, default=NAS_PORT_VIRTUAL)

        ATTR_FRAMED_IP_ADDRESS = 8
        fi_raw = attrs.get(ATTR_FRAMED_IP_ADDRESS, [b""])[0]
        framed_ip = ".".join(str(b) for b in fi_raw) if fi_raw and len(fi_raw) == 4 else ""

        stype_name = {1: "Start", 2: "Stop", 3: "Interim-Update"}.get(stype, f"Unknown({stype})")
        svc_type   = "pppoe" if nas_port_type == NAS_PORT_VIRTUAL else "hotspot"

        logger.info(f"RADIUS ACCT [{stype_name}] user={uname!r} session={session_id!r} "
                    f"in={bytes_in}B out={bytes_out}B time={sess_time}s svc={svc_type}")

        if self._db is None or not uname:
            return

        now_iso = datetime.now(timezone.utc).isoformat()

        try:
            if stype == ACCT_STATUS_START:
                await self._acct_start(uname, session_id, nas_ip, nas_port_type, svc_type, framed_ip, now_iso)

            elif stype == ACCT_STATUS_STOP:
                await self._acct_stop(uname, session_id, bytes_in, bytes_out, sess_time, svc_type, framed_ip, now_iso)

            elif stype == ACCT_STATUS_INTERIM:
                await self._acct_interim(uname, session_id, bytes_in, bytes_out, sess_time, svc_type, framed_ip, now_iso)

        except Exception as e:
            logger.error(f"ACCT DB error: {e}")

    async def _acct_start(self, uname: str, session_id: str, nas_ip: str,
                          nas_port_type: int, svc_type: str, framed_ip: str, now_iso: str):
        """FIX #7 #8: Buat/update sesi di radius_sessions saat Acct-Start."""
        if self._db is None:
            return

        # Simpan ke radius_sessions
        update_data = {
            "username":       uname,
            "nas_ip":         nas_ip,
            "acct_session_id": session_id,
            "service_type":   svc_type,
            "bytes_in":       0,
            "bytes_out":      0,
            "total_bytes":    0,
            "session_time":   0,
            "started_at":     now_iso,
            "updated_at":     now_iso,
            "active":         True,
        }
        if framed_ip:
            update_data["framed_ip"] = framed_ip

        await self._db.radius_sessions.update_one(
            {"acct_session_id": session_id} if session_id else {"username": uname, "active": True},
            {"$set": update_data},
            upsert=True
        )
        logger.info(f"ACCT START: sesi {session_id!r} untuk {uname!r} ({svc_type}) dibuat")

        # Khusus Hotspot: aktivasi voucher + tracking waktu
        if svc_type == "hotspot":
            try:
                v = await self._db.hotspot_vouchers.find_one({"username": uname})
                if v and v.get("status") not in ("expired", "disabled"):
                    upd = {"last_session_start": now_iso}  # Catat waktu sesi ini dimulai

                    if v.get("status") == "new":
                        # Login pertama kali: aktifkan voucher
                        upd["status"]           = "active"
                        upd["activated_at"]     = now_iso
                        upd["first_login_time"] = now_iso   # Tandai kapan pertama login (sekali seumur hidup)
                        await self._db.hotspot_vouchers.update_one(
                            {"_id": v["_id"]}, {"$set": upd}
                        )
                        
                        # Cek apakah penjualan sudah dicatat (oleh Moota/Online Order)
                        existing_sale = await self._db.hotspot_sales.find_one({"voucher_id": str(v["_id"])})
                        if not existing_sale:
                            await self._db.hotspot_sales.insert_one({
                                "id":           str(uuid.uuid4()),
                                "voucher_id":   str(v["_id"]),
                                "username":     uname,
                                "price":        float(v.get("price", 0)),
                                "created_at":   now_iso,
                                "device_ip":    nas_ip,
                                "device_id":    v.get("device_id", ""),
                                "source":       "First Login / Auto"
                            })
                        logger.info(f"ACCT START: voucher {uname!r} login pertama — diaktifkan")
                    else:
                        # Login ulang (setelah logout): hanya update session start
                        if not v.get("first_login_time"):
                            upd["first_login_time"] = now_iso  # Safety: isi jika missing
                        await self._db.hotspot_vouchers.update_one(
                            {"_id": v["_id"]}, {"$set": upd}
                        )
                        logger.info(f"ACCT START: voucher {uname!r} login ulang — sesi baru dimulai")
            except Exception as e:
                logger.error(f"ACCT START hotspot voucher error: {e}")

    async def _acct_interim(self, uname: str, session_id: str,
                            bytes_in: int, bytes_out: int, sess_time: int,
                            svc_type: str, framed_ip: str, now_iso: str):
        """FIX #5 #7 #8: Update bytes di radius_sessions saat Interim-Update.
        Data ini digunakan oleh scheduler FUP secara real-time."""
        if self._db is None:
            return

        total_bytes = bytes_in + bytes_out

        update_data = {
            "bytes_in":    bytes_in,
            "bytes_out":   bytes_out,
            "total_bytes": total_bytes,
            "session_time": sess_time,
            "updated_at":  now_iso,
            "active":      True,
        }
        if framed_ip:
            update_data["framed_ip"] = framed_ip

        q = {"acct_session_id": session_id} if session_id else {"username": uname, "active": True}
        await self._db.radius_sessions.update_one(
            q,
            {"$set": update_data},
            upsert=True
        )
        logger.debug(f"ACCT INTERIM: {uname!r} in={bytes_in}B out={bytes_out}B total={total_bytes}B")

        # Trigger FUP check real-time untuk PPPoE (FIX #5)
        if svc_type == "pppoe":
            asyncio.ensure_future(self._check_fup_realtime(uname, total_bytes))

    async def _acct_stop(self, uname: str, session_id: str,
                         bytes_in: int, bytes_out: int, sess_time: int,
                         svc_type: str, framed_ip: str, now_iso: str):
        """FIX #8: Tandai sesi sebagai tidak aktif saat Acct-Stop."""
        if self._db is None:
            return

        total_bytes = bytes_in + bytes_out
        q = {"acct_session_id": session_id} if session_id else {"username": uname, "active": True}

        update_data = {
            "bytes_in":    bytes_in,
            "bytes_out":   bytes_out,
            "total_bytes": total_bytes,
            "session_time": sess_time,
            "stopped_at":  now_iso,
            "updated_at":  now_iso,
            "active":      False,
        }
        if framed_ip:
            update_data["framed_ip"] = framed_ip

        await self._db.radius_sessions.update_one(
            q,
            {"$set": update_data}
        )
        logger.info(f"ACCT STOP: sesi {session_id!r} untuk {uname!r} ditutup. "
                    f"Total: {total_bytes}B dalam {sess_time}s")

        # Khusus Hotspot: akumulasi used_uptime_secs saat user logout
        if svc_type == "hotspot" and sess_time > 0:
            try:
                v = await self._db.hotspot_vouchers.find_one({"username": uname})
                if v and v.get("status") not in ("expired", "disabled"):
                    # Tambahkan durasi sesi ini ke total uptime yang sudah terpakai
                    prev_used = int(v.get("used_uptime_secs", 0))
                    new_used  = prev_used + sess_time
                    await self._db.hotspot_vouchers.update_one(
                        {"_id": v["_id"]},
                        {"$set": {
                            "used_uptime_secs":   new_used,
                            "last_logout_time":   now_iso,
                            "last_session_start": None,   # Hapus penanda sesi aktif
                        }}
                    )
                    logger.info(
                        f"ACCT STOP: voucher {uname!r} uptime akumulasi "
                        f"{prev_used}s + {sess_time}s = {new_used}s"
                    )
            except Exception as e:
                logger.error(f"ACCT STOP hotspot voucher uptime error: {e}")

    async def _check_fup_realtime(self, uname: str, total_bytes: int):
        """FIX #5: Cek FUP limit secara real-time dari data Accounting.
        Dipanggil setiap Interim-Update masuk — tanpa perlu polling API MikroTik."""
        if self._db is None:
            return
        try:
            customer = await self._db.customers.find_one({"username": uname, "active": True})
            if not customer or customer.get("fup_active"):
                return   # Sudah kena FUP atau tidak ditemukan

            pkg = await self._db.billing_packages.find_one({"id": customer.get("package_id", "")})
            if not pkg or not pkg.get("fup_enabled"):
                return

            limit_gb = pkg.get("fup_limit_gb", 0)
            if limit_gb <= 0:
                return

            limit_bytes = limit_gb * 1_000_000_000
            if total_bytes >= limit_bytes:
                fup_rate = pkg.get("fup_rate_limit", "")
                logger.info(f"[FUP-REALTIME] {uname}: {total_bytes}B >= {limit_bytes}B limit. "
                            f"Apply FUP rate: {fup_rate!r}")

                # Update DB
                await self._db.customers.update_one(
                    {"username": uname},
                    {"$set": {"fup_active": True, "current_rate_limit": fup_rate}}
                )

                # Kirim CoA via bandwidth_manager
                if fup_rate:
                    try:
                        device = await self._db.devices.find_one({"id": customer.get("device_id", "")})
                        if device:
                            from services.bandwidth_manager import set_rate_limit
                            await set_rate_limit(customer, device, fup_rate, self._db)
                    except Exception as e:
                        logger.error(f"[FUP-REALTIME] CoA gagal untuk {uname}: {e}")

        except Exception as e:
            logger.error(f"[FUP-REALTIME] Check error untuk {uname}: {e}")


# ── Background: Sync Allowed NAS Hosts dari MongoDB ───────────────────────────
async def _sync_hosts_loop(db):
    """Sinkronisasi daftar NAS (router MikroTik) dan secret dari DB setiap 30 detik."""
    global _global_secret, _allowed_hosts
    while True:
        try:
            if db is not None:
                # Update global secret dari hotspot_settings
                hs = await db.hotspot_settings.find_one({}, {"_id": 0}) or {}
                raw = hs.get("radius_secret") or hs.get("secret", "")
                if raw:
                    _global_secret = raw.encode("utf-8")

                # Sync per-device secret
                devices = await db.devices.find({}).to_list(1000)
                new_hosts = {}
                for d in devices:
                    raw_h = d.get("host") or d.get("ip_address") or d.get("ip", "")
                    ip = raw_h.split(":")[0].strip() if raw_h else ""
                    if not ip or ip == "undefined":
                        continue
                    # Prioritas: radius_secret > hotspot_secret > global_secret
                    s = (d.get("radius_secret") or d.get("hotspot_secret") or "")
                    new_hosts[ip] = s.encode("utf-8") if s else _global_secret
                    logger.debug(f"RADIUS host synced: {d.get('name', ip)} @ {ip}")
                _allowed_hosts = new_hosts
                logger.info(f"RADIUS hosts synced: {list(_allowed_hosts.keys())} "
                            f"global={'*' * len(_global_secret)}")
        except Exception as e:
            logger.error(f"RADIUS sync error: {e}")
        await asyncio.sleep(30)


# ── Server Startup ─────────────────────────────────────────────────────────────
_auth_transport = None
_acct_transport = None


def start_radius_server(loop, db):
    global _db_pool
    _db_pool = db

    async def _start():
        global _auth_transport, _acct_transport
        try:
            _auth_transport, _ = await loop.create_datagram_endpoint(
                lambda: RADIUSProtocol(db), local_addr=("0.0.0.0", 1812)
            )
            logger.info("RADIUS Auth listening 0.0.0.0:1812")

            _acct_transport, _ = await loop.create_datagram_endpoint(
                lambda: RADIUSProtocol(db), local_addr=("0.0.0.0", 1813)
            )
            logger.info("RADIUS Acct listening 0.0.0.0:1813")

            asyncio.ensure_future(_sync_hosts_loop(db))
            logger.info("RADIUS Server aktif — PAP + CHAP + NAS-Port-Type routing + FIX #1-10")

        except Exception as e:
            import traceback
            logger.error(f"RADIUS start failed: {e}\n{traceback.format_exc()}")

    asyncio.run_coroutine_threadsafe(_start(), loop)
