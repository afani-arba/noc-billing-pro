"""radius_server.py — NOC Sentinel Enterprise (asyncio + PAP + CHAP support)"""

import asyncio, logging, struct, hashlib, uuid
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

_db_pool = None
_global_secret = b"testing123"
_allowed_hosts: dict = {}

ACCESS_REQUEST  = 1
ACCESS_ACCEPT   = 2
ACCESS_REJECT   = 3
ACCT_REQUEST    = 4
ACCT_RESPONSE   = 5

ATTR_USER_NAME       = 1
ATTR_USER_PASSWORD   = 2   # PAP
ATTR_CHAP_PASSWORD   = 3   # CHAP: 1-byte ID + 16-byte MD5
ATTR_REPLY_MESSAGE   = 18
ATTR_ACCT_STATUS     = 40
ATTR_CHAP_CHALLENGE  = 60  # Optional CHAP challenge (fallback: req authenticator)


def _parse_packet(data: bytes):
    if len(data) < 20:
        return None
    code, pkt_id, length = struct.unpack("!BBH", data[:4])
    auth = data[4:20]
    attrs = {}
    pos = 20
    while pos + 2 <= min(length, len(data)):
        t = data[pos]; l = data[pos+1]
        if l < 2: break
        attrs.setdefault(t, []).append(data[pos+2:pos+l])
        pos += l
    return {"code": code, "id": pkt_id, "auth": auth, "attrs": attrs}


def _decrypt_pap(cipher: bytes, authenticator: bytes, secret: bytes) -> str:
    result = bytearray()
    prev = authenticator
    for i in range(0, len(cipher), 16):
        chunk = cipher[i:i+16]
        pad = hashlib.md5(secret + prev).digest()
        result.extend(a ^ b for a, b in zip(pad, chunk))
        prev = chunk
    return result.rstrip(b"\x00").decode("utf-8", errors="replace")


def _build_reply(code, pkt_id, req_auth, secret, attrs_list):
    attr_bytes = b"".join(bytes([t, len(v)+2]) + v for t, v in attrs_list)
    length = 20 + len(attr_bytes)
    header = struct.pack("!BBH", code, pkt_id, length) + req_auth
    resp_auth = hashlib.md5(header + attr_bytes + secret).digest()
    return struct.pack("!BBH", code, pkt_id, length) + resp_auth + attr_bytes


def _get_secret(nas_ip: str) -> bytes:
    return _allowed_hosts.get(nas_ip, _global_secret)


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
        secret = _get_secret(addr[0])
        pkt = _parse_packet(data)
        if not pkt:
            return
        logger.info(f"RADIUS pkt from {addr[0]}: code={pkt['code']} id={pkt['id']}")
        if pkt["code"] == ACCESS_REQUEST:
            await self._auth(pkt, addr, secret)
        elif pkt["code"] == ACCT_REQUEST:
            await self._acct(pkt, addr, secret)

    async def _auth(self, pkt, addr, secret):
        pid, req_auth, attrs = pkt["id"], pkt["auth"], pkt["attrs"]
        uname = (attrs.get(ATTR_USER_NAME, [b""])[0]).decode("utf-8", errors="replace")

        pap_raw   = (attrs.get(ATTR_USER_PASSWORD,  [None])[0])
        chap_raw  = (attrs.get(ATTR_CHAP_PASSWORD,  [None])[0])
        chap_chal = (attrs.get(ATTR_CHAP_CHALLENGE, [None])[0])

        method = "PAP" if pap_raw else ("CHAP" if chap_raw else "NONE")
        logger.info(f"RADIUS AUTH [{method}] user={uname!r}")

        def reject(msg: bytes):
            r = _build_reply(ACCESS_REJECT, pid, req_auth, secret, [(ATTR_REPLY_MESSAGE, msg)])
            self._transport.sendto(r, addr)

        def accept(attrs_list=None):
            if attrs_list is None: attrs_list = []
            r = _build_reply(ACCESS_ACCEPT, pid, req_auth, secret, attrs_list)
            self._transport.sendto(r, addr)
            logger.info(f"RADIUS ACCEPT: {uname!r} attrs={len(attrs_list)}")

        if method == "NONE":
            return reject(b"No auth method")

        # DB lookup
        voucher = None
        if self._db is not None:
            try:
                voucher = await self._db.hotspot_vouchers.find_one({"username": uname})
            except Exception as e:
                logger.error(f"DB error (Hotspot voucher lookup): {e}")

        # ── Fallback: cek customers (PPPoE Billing) jika bukan hotspot voucher ─────────
        pppoe_customer = None
        if not voucher and self._db is not None:
            try:
                pppoe_customer = await self._db.customers.find_one({
                    "username": uname,
                    "active": True,
                })
            except Exception as e:
                logger.error(f"DB error (PPPoE customer lookup): {e}")

        if not voucher and not pppoe_customer:
            logger.info(f"RADIUS REJECT: {uname!r} not found in Hotspot DB nor PPPoE Billing")
            return reject(b"User not found")

        # Route ke handler PPPoE jika ditemukan sebagai customer billing
        if pppoe_customer and not voucher:
            return await self._auth_pppoe(pppoe_customer, uname, pid, req_auth, secret,
                                          method, pap_raw, chap_raw, chap_chal, addr)

        db_pwd = voucher.get("password", "")

        # --- PAP verify ---
        if method == "PAP":
            try:
                plain = _decrypt_pap(pap_raw, req_auth, secret)
            except Exception as e:
                logger.warning(f"PAP decrypt fail: {e}")
                return reject(b"Auth error")
            auth_ok = (plain == db_pwd)

        # --- CHAP verify ---
        # Alur MikroTik HTTP CHAP (dari login.html line 358):
        #   Browser: hexMD5(chapId + password + chapChallenge) → dikirim sebagai field "password"
        #   MikroTik menerima hex string ini dan melakukan CHAP standard:
        #   CHAP-Response = MD5(chap_id_byte + hex_string_from_browser + chap_challenge_bytes)
        else:
            if len(chap_raw) < 17:
                return reject(b"Bad CHAP packet")
            chap_id   = chap_raw[0:1]
            chap_resp = chap_raw[1:17]
            challenge = chap_chal if chap_chal else req_auth
            chap_id_str = chap_id.hex()  # 2-char hex string dari 1-byte ID

            logger.info(
                f"CHAP DEBUG: id={chap_id.hex()} "
                f"challenge_src={'attr60' if chap_chal else 'req_auth'} "
                f"challenge={challenge.hex()} db_pwd={db_pwd!r} "
                f"chap_resp={chap_resp.hex()}"
            )

            auth_ok = False

            # Variasi 1: Standard CHAP RFC2865 — MD5(chap_id + plaintext_pwd + challenge)
            e1 = hashlib.md5(chap_id + db_pwd.encode("utf-8") + challenge).digest()
            if e1 == chap_resp:
                auth_ok = True
                logger.info("CHAP ok: v1 standard")

            # Variasi 2: MikroTik HTTP CHAP dari browser login page
            # Browser: hex_browser = hexMD5(chapId_hex + password + challenge_hex)
            # MikroTik RADIUS: MD5(chap_id_byte + hex_browser.encode('latin1') + challenge)
            if not auth_ok:
                challenge_hex = challenge.hex()
                hex_browser = hashlib.md5(
                    (chap_id_str + db_pwd + challenge_hex).encode("latin-1")
                ).hexdigest()
                e2 = hashlib.md5(chap_id + hex_browser.encode("latin-1") + challenge).digest()
                if e2 == chap_resp:
                    auth_ok = True
                    logger.info("CHAP ok: v2 hexMD5(chapId_hex+pwd+challenge_hex)")

            # Variasi 3: chapId sebagai raw byte (bukan hex string)
            if not auth_ok:
                hex_browser3 = hashlib.md5(
                    chap_id + db_pwd.encode("utf-8") + challenge
                ).hexdigest()
                e3 = hashlib.md5(chap_id + hex_browser3.encode("latin-1") + challenge).digest()
                if e3 == chap_resp:
                    auth_ok = True
                    logger.info("CHAP ok: v3 hexMD5(chapId_byte+pwd+challenge)")

            # Variasi 4: username sebagai password
            if not auth_ok and db_pwd != uname:
                e4 = hashlib.md5(chap_id + uname.encode("utf-8") + challenge).digest()
                if e4 == chap_resp:
                    auth_ok = True
                    logger.info("CHAP ok: v4 username=password plaintext")

            logger.info(f"CHAP result: ok={auth_ok} resp={chap_resp.hex()}")

        if not auth_ok:
            logger.info(f"RADIUS REJECT: wrong password for {uname!r}")
            return reject(b"Wrong password")

        if voucher.get("status") == "expired":
            logger.info(f"RADIUS REJECT: {uname!r} expired")
            return reject(b"Voucher expired")

        # Build RADIUS VSA: Only Mikrotik-Rate-Limit (no Mikrotik-Group)
        # Semua voucher akan menggunakan profile "default" di MikroTik
        reply_attrs = []
        try:
            profile_name = voucher.get("profile", "")
            if profile_name and self._db is not None:
                pkg = await self._db.billing_packages.find_one({
                    "$or": [{"name": profile_name}, {"id": profile_name}]
                })
                if pkg:
                    down = pkg.get("speed_down", "").strip()
                    up = pkg.get("speed_up", "").strip()
                    if down and up:
                        # Format: "upload/download" (Mikrotik rx-rate/tx-rate)
                        rate_str = f"{up}/{down}"
                        rate_val = rate_str.encode("utf-8")
                        vsa_rate = struct.pack("!I", 14988) + bytes([8, len(rate_val) + 2]) + rate_val
                        reply_attrs.append((26, vsa_rate))
                        logger.info(f"RADIUS: sending rate-limit {rate_str!r} for {uname!r}")
        except Exception as e:
            logger.error(f"Error packing RADIUS VSA: {e}")

        accept(reply_attrs)


    async def _auth_pppoe(self, customer: dict, uname: str, pid: int, req_auth: bytes,
                          secret: bytes, method: str, pap_raw, chap_raw, chap_chal,
                          addr: tuple):
        """
        Handler autentikasi RADIUS untuk PPPoE Billing customers.
        - Verifikasi password
        - Cek status billing (isolir jika ada invoice overdue)
        - Return VSA Mikrotik-Rate-Limit dari billing package
        """
        def reject(msg: bytes):
            r = _build_reply(ACCESS_REJECT, pid, req_auth, secret, [(ATTR_REPLY_MESSAGE, msg)])
            self._transport.sendto(r, addr)

        def accept(attrs_list=None):
            if attrs_list is None: attrs_list = []
            r = _build_reply(ACCESS_ACCEPT, pid, req_auth, secret, attrs_list)
            self._transport.sendto(r, addr)
            logger.info(f"RADIUS PPPoE ACCEPT: {uname!r} attrs={len(attrs_list)}")

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
            # Standard CHAP
            e1 = hashlib.md5(chap_id + db_pwd.encode("utf-8") + challenge).digest()
            auth_ok = (e1 == chap_resp)
        else:
            return reject(b"Unsupported auth method")

        if not auth_ok:
            logger.info(f"RADIUS PPPoE REJECT: wrong password for {uname!r}")
            return reject(b"Wrong password")

        # ── Cek status billing: tolak jika ada invoice overdue ───────────────────
        try:
            if self._db is not None:
                overdue = await self._db.invoices.find_one({
                    "customer_id": customer["id"],
                    "status": "overdue",
                })
                if overdue:
                    logger.info(
                        f"RADIUS PPPoE REJECT: {uname!r} memiliki tagihan overdue "
                        f"(Invoice: {overdue.get('invoice_number')})"
                    )
                    return reject(b"Tagihan belum dibayar")
        except Exception as e:
            logger.error(f"PPPoE billing check error: {e}")

        # ── Build VSA Mikrotik-Rate-Limit & Framed-Pool ─────────────────────────
        reply_attrs = []
        try:
            if self._db is not None:
                pkg = await self._db.billing_packages.find_one({"id": customer.get("package_id", "")})
                if pkg:
                    down = str(pkg.get("speed_down", "")).strip()
                    up   = str(pkg.get("speed_up",   "")).strip()
                    if down and up:
                        rate_str = f"{up}/{down}"
                        rate_val = rate_str.encode("utf-8")
                        # Mikrotik-Rate-Limit Vendor-Specific Attribute (VSA)
                        vsa_rate = struct.pack("!I", 14988) + bytes([8, len(rate_val) + 2]) + rate_val
                        reply_attrs.append((26, vsa_rate))
                        logger.info(f"RADIUS PPPoE: rate-limit '{rate_str}' untuk {uname!r}")
                
                # Fetch PPPoE Pool Config to send Framed-Pool
                pool_cfg = await self._db.system_settings.find_one({"_id": "pppoe_pool_config"})
                if pool_cfg and pool_cfg.get("pool_name"):
                    pool_name = pool_cfg["pool_name"]
                    reply_attrs.append((88, pool_name.encode("utf-8"))) # Framed-Pool
                    logger.info(f"RADIUS PPPoE: assigned Framed-Pool '{pool_name}' untuk {uname!r}")
                else:
                    # Provide default pool name as fallback to ensure IP assignment
                    reply_attrs.append((88, b"pppoe-pool"))
        except Exception as e:
            logger.error(f"PPPoE VSA rate-limit error: {e}")

        accept(reply_attrs)

    async def _acct(self, pkt, addr, secret):
        pid, req_auth, attrs = pkt["id"], pkt["auth"], pkt["attrs"]
        # Always ACK immediately
        self._transport.sendto(_build_reply(ACCT_RESPONSE, pid, req_auth, secret, []), addr)

        uname = (attrs.get(ATTR_USER_NAME, [b""])[0]).decode("utf-8", errors="replace")
        stype_raw = attrs.get(ATTR_ACCT_STATUS, [b"\x00\x00\x00\x00"])[0]
        stype = struct.unpack("!I", stype_raw.ljust(4, b"\x00"))[0] if stype_raw else 0
        logger.info(f"RADIUS ACCT: user={uname!r} type={stype}")

        if self._db is None or not uname:
            return
        try:
            v = await self._db.hotspot_vouchers.find_one({"username": uname})
            if v and stype == 1 and v.get("status") == "new":
                now = datetime.now(timezone.utc).isoformat()
                await self._db.hotspot_vouchers.update_one(
                    {"_id": v["_id"]},
                    {"$set": {"status": "active", "activated_at": now}}
                )
                await self._db.hotspot_sales.insert_one({
                    "id": str(uuid.uuid4()),
                    "voucher_id": str(v["_id"]),
                    "username": uname,
                    "price": float(v.get("price", 0)),
                    "created_at": now,
                    "device_ip": addr[0]
                })
                logger.info(f"ACCT: voucher {uname!r} activated, sale recorded")
        except Exception as e:
            logger.error(f"ACCT DB error: {e}")


_auth_transport = None
_acct_transport = None


async def _sync_hosts_loop(db):
    global _global_secret, _allowed_hosts
    while True:
        try:
            if db is not None:
                hs = await db.hotspot_settings.find_one({}, {"_id": 0}) or {}
                raw = hs.get("radius_secret") or hs.get("secret", "")
                if raw:
                    _global_secret = raw.encode("utf-8")

                devices = await db.devices.find({}).to_list(1000)
                new_hosts = {}
                for d in devices:
                    raw_h = d.get("host") or d.get("ip_address") or d.get("ip", "")
                    ip = raw_h.split(":")[0].strip() if raw_h else ""
                    if not ip or ip == "undefined":
                        continue
                    s = d.get("radius_secret") or d.get("hotspot_secret", "")
                    new_hosts[ip] = s.encode() if s else _global_secret
                    logger.info(f"RADIUS host: {d.get('name', ip)} @ {ip}")
                _allowed_hosts = new_hosts
                logger.info(f"RADIUS hosts synced: {list(_allowed_hosts.keys())} global={'*'*len(_global_secret)}")
        except Exception as e:
            logger.error(f"RADIUS sync error: {e}")
        await asyncio.sleep(30)


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
            logger.info("RADIUS Server started — PAP + CHAP support enabled")
        except Exception as e:
            import traceback
            logger.error(f"RADIUS start failed: {e}\n{traceback.format_exc()}")

    asyncio.run_coroutine_threadsafe(_start(), loop)
