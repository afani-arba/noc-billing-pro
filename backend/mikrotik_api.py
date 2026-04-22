"""
Unified MikroTik API client — Hybrid Monitoring.
=================================================
Dua implementasi dengan interface yang identik:
  - MikroTikRestAPI     : RouterOS 7.x — REST API (port 443/80)
  - MikroTikLegacyAPI   : RouterOS 6.x — API Protocol (port 8728/8729)

Factory:
  get_api_client(device) → pilih class berdasarkan device['api_mode']
  discover_device(device) → auto-detect mode dan simpan ke DB
"""
import ssl
import httpx
import asyncio
import logging
import urllib3
import routeros_api

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
logger = logging.getLogger(__name__)


def parse_host_port(ip_address: str, default_port: int = None):
    """
    Parse 'host' or 'host:port' format dari field ip_address.
    Support format:
      - '192.168.1.1'          → ('192.168.1.1', default_port)
      - '192.168.1.1:7701'     → ('192.168.1.1', 7701)
      - '103.157.116.29:7701'  → ('103.157.116.29', 7701)

    Returns: (host: str, port: int|None)
    """
    if not ip_address:
        return ip_address, default_port

    ip_address = str(ip_address).strip()

    # Cek apakah mengandung port (host:port)
    if ':' in ip_address:
        parts = ip_address.rsplit(':', 1)
        try:
            port = int(parts[1])
            return parts[0], port
        except ValueError:
            pass  # bukan port valid, kembali sebagai host saja

    return ip_address, default_port


# ── Global HTTPX Client Pool ───────────────────────────────────────────────
# Untuk persistent connections (keep-alive) dan mencegah overhead koneksi ulang.
_httpx_clients = {}

def _get_httpx_client(base_url: str, use_ssl: bool) -> httpx.AsyncClient:
    key = (base_url, use_ssl)
    if key not in _httpx_clients:
        ctx = ssl.create_default_context(ssl.Purpose.SERVER_AUTH)
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        try:
            ctx.set_ciphers("ALL:@SECLEVEL=0")
        except ssl.SSLError:
            pass
        try:
            ctx.minimum_version = ssl.TLSVersion.MINIMUM_SUPPORTED
        except (AttributeError, ValueError):
            pass
        try:
            ctx.options |= ssl.OP_LEGACY_SERVER_CONNECT
        except AttributeError:
            pass
            
        _httpx_clients[key] = httpx.AsyncClient(
            verify=ctx if use_ssl else False,
            timeout=httpx.Timeout(30.0),
            limits=httpx.Limits(
                # ── Dibatasi kecil agar tidak membanjiri MikroTik dengan koneksi TCP berlebih──
                # MikroTik RouterOS memiliki batas session yang rendah, koneksi terlalu banyak
                # akan memperlambat Winbox dan mempengaruhi performa router.
                max_keepalive_connections=2,   # Hanya 2 keep-alive per MikroTik host
                max_connections=5,             # Maksimal 5 koneksi parallel (bukan 100!)
                keepalive_expiry=30.0          # Tutup idle connection setelah 30 detik
            )
        )
    return _httpx_clients[key]



# ── Base interface ──
class MikroTikBase:
    # ── Connection ──
    async def test_connection(self): raise NotImplementedError

    # ── Polling/Monitoring — default aman (return kosong) ──
    # Subclass yang tidak implement tidak akan menyebabkan AttributeError
    async def get_system_identity(self): return ""
    async def get_system_resource(self): return {}
    async def get_system_health(self):   return {}  # Override di subclass
    async def list_interfaces(self):     return []
    async def get_isp_interfaces(self):  return []
    async def get_out_interfaces(self):  return []

    async def get_interface_traffic(self, interface_name="ether1", duration=1): return {}
    async def ping_host(self, address="8.8.8.8", count=4): return []
    async def list_dhcp_leases(self): return []

    # ── PPPoE ──
    async def list_pppoe_secrets(self): raise NotImplementedError
    async def create_pppoe_secret(self, data): raise NotImplementedError
    async def update_pppoe_secret(self, mt_id, data): raise NotImplementedError
    async def delete_pppoe_secret(self, mt_id): raise NotImplementedError
    async def list_pppoe_active(self): raise NotImplementedError
    async def disable_pppoe_user(self, username): raise NotImplementedError
    async def enable_pppoe_user(self, username): raise NotImplementedError
    async def remove_pppoe_active_session(self, username): return 0  # default: safe no-op
    async def update_pppoe_secret_password(self, username, new_password): pass  # default: no-op (RADIUS not needed)

    # ── Hotspot ──
    async def list_hotspot_users(self): raise NotImplementedError
    async def create_hotspot_user(self, data): raise NotImplementedError
    async def update_hotspot_user(self, mt_id, data): raise NotImplementedError
    async def delete_hotspot_user(self, mt_id): raise NotImplementedError
    async def list_hotspot_active(self): raise NotImplementedError
    async def disable_hotspot_user(self, username): raise NotImplementedError
    async def enable_hotspot_user(self, username): raise NotImplementedError
    async def remove_hotspot_active_session(self, username): raise NotImplementedError
    async def list_pppoe_profiles(self): raise NotImplementedError
    async def list_hotspot_profiles(self): raise NotImplementedError
    async def list_hotspot_server_profiles(self): raise NotImplementedError
    async def list_hotspot_servers(self): raise NotImplementedError
    
    # ── Queues ──
    async def list_simple_queues(self): raise NotImplementedError
    async def update_simple_queue(self, mt_id: str, data: dict): raise NotImplementedError

    # ── SD-WAN / Route Management (default: not supported) ──
    async def add_ip_route(self, dst_address, gateway, distance=1, routing_table="main", check_gateway="", comment=""): return {}
    async def remove_ip_route(self, mt_id): return {}
    async def add_mangle_rule(self, chain, src_address="", dst_address="", action="mark-routing", routing_mark="", comment="", passthrough=True): return {}
    async def remove_mangle_rule(self, mt_id): return {}
    async def list_routing_tables(self): return []
    async def list_sstp_peers(self): return []

    # ── BGP Automation (default: not supported) ──
    async def add_bgp_network(self, prefix, comment=""): return {}
    async def remove_bgp_network(self, mt_id): return {}
    async def list_bgp_networks(self): return []
    async def list_bgp_advertisements(self, connection_name=""): return []
    async def list_routing_filters(self): return []
    async def bgp_soft_reset(self, session_name=""): return {}

    # ── Netwatch / Probing (default: not supported) ──
    async def get_netwatch_entries(self): return []
    async def add_netwatch_entry(self, data): return {}
    async def update_netwatch_entry(self, mt_id, data): return {}
    async def remove_netwatch_entry(self, mt_id): return {}

    # ── Firewall Address-List (DDoS RTBH) ──
    async def get_firewall_address_list(self, list_name: str = "") -> list: return []
    async def add_firewall_address_list(self, list_name: str, address: str, comment: str = "") -> dict: return {}
    async def remove_firewall_address_list(self, mt_id: str) -> dict: return {}

    # ── IP Accounting (untuk bandwidth per platform Peering-Eye) ──
    async def get_ip_accounting_snapshot(self) -> list: raise NotImplementedError

    # ── Mangle / Firewall Listing ──
    async def list_ip_routes(self, limit: int = 500) -> list: return []
    async def get_all_interface_stats(self) -> dict: return {"isp_interfaces": [], "isp_comments": {}, "stats": {}}

    # ── RADIUS Management ──
    async def list_radius_clients(self) -> list: return []
    async def add_radius_client(self, address: str, secret: str, service: str = "hotspot", comment: str = "") -> dict: return {}
    async def setup_hotspot_radius(self, radius_ip: str, secret: str, server_profile: str = "hsprof1", pppoe_profile: str = "") -> dict: return {}
    async def check_radius_enabled(self, server_profile: str = "hsprof1") -> dict: return {"radius_enabled": False, "radius_clients": []}

    # ── Walled Garden ──
    async def list_walled_garden(self) -> list: return []
    async def add_walled_garden_entry(self, server: str, dst_host: str, comment: str = "") -> dict: return {}
    async def setup_walled_garden(self, entries: list, server: str = "all") -> dict: return {"success": True, "steps": [], "skipped": 0, "added": 0}


# ═══════════════════════════════════════════════════════════
# RouterOS 7+ REST API
# ═══════════════════════════════════════════════════════════
class MikroTikRestAPI(MikroTikBase):
    def __init__(self, host, username, password, port=443, use_ssl=True):
        # Support format host:port — parse terlebih dahulu agar tidak double-port
        parsed_host, parsed_port = parse_host_port(host, default_port=port)
        self.host = parsed_host
        self.port = parsed_port if parsed_port is not None else port
        self.use_ssl = use_ssl

        scheme = "https" if use_ssl else "http"
        self.base_url = f"{scheme}://{self.host}:{self.port}/rest"
        self.auth = (username, password)
        self.verify = False
        self.timeout = 30

    async def _async_req(self, method, path, data=None, timeout=None):
        url = f"{self.base_url}/{path}"
        req_timeout = timeout if timeout is not None else self.timeout
        client = _get_httpx_client(self.base_url, self.use_ssl)
        
        logger.debug(f"REST API request: {method} {url} (timeout={req_timeout}s)")
        try:
            resp = await client.request(
                method, url, auth=self.auth, json=data, timeout=req_timeout
            )
            logger.debug(f"REST API response: {resp.status_code}")
            
            if resp.status_code == 401:
                raise Exception(
                    "Authentication failed - check username/password. "
                    "(PENTING ROS 7: Jika password Anda KOSONG, REST API RouterOS 7 menolaknya. Beri password pada mikrotik Anda! "
                    "Atau cek policy 'rest-api' di System->Users->Groups)"
                )
            if resp.status_code == 400:
                detail = resp.json() if resp.content else {}
                raise Exception(f"Bad request: {detail.get('detail', detail.get('message', resp.text))}")
            if resp.status_code == 404:
                raise Exception(f"Endpoint tidak ditemukan (404): {path} - pastikan RouterOS mendukung endpoint ini")
                
            resp.raise_for_status()
            return resp.json() if resp.content else {}
            
        except httpx.ConnectError as e:
            logger.error(f"Connection Error to {url}: {e}")
            error_msg = str(e)
            if "refused" in error_msg.lower():
                raise Exception(f"Connection refused - pastikan www service aktif di port {self.port} dan tidak ada firewall yang memblokir")
            elif "route to host" in error_msg.lower():
                raise Exception(f"No route to host - periksa IP address dan jaringan")
            elif "ssl" in error_msg.lower() or "handshake" in error_msg.lower():
                raise Exception(f"SSL Handshake gagal ke {self.host}:{self.port}. Coba ganti ke HTTP (port 80) di konfigurasi device.")
            else:
                raise Exception(f"Tidak dapat terhubung ke {self.host}:{self.port} - pastikan: 1) www service aktif, 2) port {self.port} tidak diblokir firewall, 3) IP server monitoring diizinkan di MikroTik")
        except httpx.TimeoutException:
            raise Exception(f"Connection timeout ke {self.host}:{self.port} - periksa: 1) Firewall MikroTik, 2) www service address restriction, 3) Koneksi jaringan")
        except Exception as e:
            if any(k in str(e) for k in ["Authentication", "Bad request", "Cannot connect", "timeout", "SSL Error", "Connection refused", "No route"]):
                raise
            raise Exception(f"REST API error: {e}")

    async def test_connection(self):
        """
        Test koneksi REST API MikroTik ROS 7+.
        Coba 3 endpoint bertingkat: system/identity → system/resource → ip/address
        Jika semua 404: REST API tidak aktif di device (www service belum diaktifkan).
        """
        endpoints = [
            ("system/identity",  lambda r: r.get("name", "MikroTik")),
            ("system/resource",  lambda r: r.get("board-name", r.get("platform", "MikroTik"))),
            ("ip/address",       lambda r: "MikroTik" if isinstance(r, list) else r.get("name", "MikroTik")),
        ]
        last_error = ""
        all_404    = True

        for path, extract_name in endpoints:
            try:
                r = await self._async_req("GET", path)
                identity = extract_name(r) if isinstance(r, (dict, list)) else "MikroTik"
                return {
                    "success":  True,
                    "identity": identity,
                    "mode":     "REST API (RouterOS 7+)",
                    "endpoint": path,
                }
            except Exception as e:
                err_str = str(e)
                last_error = err_str
                # Jika bukan 404, hentikan loop — ini error koneksi bukan REST API disabled
                if "404" not in err_str:
                    all_404 = False
                    break

        if all_404:
            # Semua endpoint 404 = REST API (www service) tidak aktif di device
            return {
                "success": False,
                "error":   (
                    f"REST API tidak aktif di {self.host}:{self.port}. "
                    "Aktifkan www service di MikroTik: "
                    "IP → Services → www → Enable, "
                    "atau jalankan: /ip service enable www"
                ),
                "mode": "REST API (RouterOS 7+)",
            }

        # Error koneksi lain (timeout, auth fail, SSL, refused)
        return {"success": False, "error": last_error, "mode": "REST API (RouterOS 7+)"}


    # ── Suppress Login/Logout Log Spam ────────────────────────────────────────
    async def suppress_account_logging(self) -> bool:
        """
        Tambahkan rule logging 'discard' untuk topic 'account' di MikroTik.
        Ini menghentikan log spam 'user admin logged in/out via api' yang muncul
        setiap kali backend NOC melakukan polling via REST API.

        Hanya memodifikasi rule jika perlu (mencari topic 'info' dan menjadikannya 'info,!account').
        Return True jika berhasil (sudah diset), False jika gagal.
        """
        try:
            # Cek daftar rule logging
            existing = await self._async_req("GET", "system/logging")
            if isinstance(existing, list):
                # Deteksi jika sudah tersuppress
                for rule in existing:
                    topics = str(rule.get("topics", "")).lower()
                    if "!account" in topics:
                        logger.debug(f"[suppress_logging] Rule info,!account sudah ada di {self.host}")
                        return True

                # Cari rule default "info" dan ubah menjadi "info,!account"
                for rule in existing:
                    topics = str(rule.get("topics", ""))
                    if topics == "info":
                        rule_id = rule.get(".id")
                        if rule_id:
                            # Gunakan PATCH untuk merubah data resource di ROS7
                            await self._async_req("PATCH", f"system/logging/{rule_id}", {
                                "topics": "info,!account"
                            })
                            logger.info(f"[suppress_logging] ✅ Log account berhasil disembunyikan di {self.host}")
                            return True
            return False
        except Exception as e:
            logger.debug(f"[suppress_logging] Gagal set logging rule di {self.host}: {e}")
            return False

    # ── System Resource (ROS 7.x REST API) ──
    async def get_system_identity(self):

        """Ambil nama router dari /rest/system/identity."""
        try:
            r = await self._async_req("GET", "system/identity")
            return r.get("name", "") if isinstance(r, dict) else ""
        except Exception:
            return ""

    async def get_system_resource(self):
        """Ambil CPU, memory, uptime dari /rest/system/resource."""
        try:
            return await self._async_req("GET", "system/resource")
        except Exception:
            return {}

    # ── System Health (ROS 7.x: temperature, voltage, power) ──
    async def get_system_health(self):
        """
        Ambil data sensor hardware dari /rest/system/health.
        Field nyata dari MikroTik ROS 7.x:
          {name: cpu-temperature, value: 47, type: C}
          {name: sfp-temperature, value: 38, type: C}
          {name: switch-temperature, value: 39, type: C}
          {name: board-temperature1, value: 39, type: C}
          {name: fan1-speed, value: 4080, type: RPM}
          {name: fan-state, value: ok}
          {name: psu1-state, value: fail}
          {name: psu2-state, value: ok}
          {name: voltage, value: 240, type: dV}   (some devices)
        """
        try:
            items = await self._async_req("GET", "system/health")
            if not isinstance(items, list):
                return {}

            result = {
                "cpu_temp": 0,
                "board_temp": 0,
                "sfp_temp": 0,
                "switch_temp": 0,
                "voltage": 0,
                "power": 0,
                "fans": {},        # {fan1: 4080, fan2: 4020, ...}
                "fan_state": "",   # "ok" / "fail"
                "psu": {},         # {psu1: "ok", psu2: "fail", ...}
                "extra_temps": {}, # {sfp: 38, switch: 39, ...}
            }

            for item in items:
                name = (item.get("name") or "").lower()
                raw_val = item.get("value", "")
                unit = (item.get("type") or "").upper()

                # Try numeric conversion
                try:
                    num_val = float(str(raw_val))
                except (ValueError, TypeError):
                    num_val = None

                # ── Temperatures ──────────────────────────────────
                if name == "cpu-temperature":
                    result["cpu_temp"] = num_val or 0

                elif name.startswith("board-temperature"):
                    # board-temperature, board-temperature1, board-temperature2
                    if result["board_temp"] == 0:
                        result["board_temp"] = num_val or 0

                elif name == "sfp-temperature":
                    result["sfp_temp"] = num_val or 0
                    result["extra_temps"]["sfp"] = num_val or 0

                elif name == "switch-temperature":
                    result["switch_temp"] = num_val or 0
                    result["extra_temps"]["switch"] = num_val or 0

                elif "temperature" in name:
                    # catch-all for other temperature sensors
                    key = name.replace("-temperature", "").replace("-temp", "")
                    result["extra_temps"][key] = num_val or 0
                    if result["board_temp"] == 0:
                        result["board_temp"] = num_val or 0

                # ── Voltage ───────────────────────────────────────
                elif "voltage" in name:
                    if num_val is not None:
                        # MikroTik may return dV (deci-volt): 240 dV = 24.0 V
                        voltage = num_val / 10.0 if unit == "DV" or num_val > 100 else num_val
                        result.setdefault("voltage", round(voltage, 1))

                # ── Power ─────────────────────────────────────────
                elif "power" in name and "psu" not in name:
                    result.setdefault("power", num_val or 0)

                # ── Current ───────────────────────────────────────
                elif name == "current":
                    result["current"] = num_val or 0

                # ── Fan speed (fan1-speed, fan2-speed ...) ────────
                elif name.endswith("-speed") and "fan" in name:
                    fan_key = name.replace("-speed", "")  # fan1, fan2, ...
                    result["fans"][fan_key] = int(num_val) if num_val else 0

                # ── Fan state (ok / fail) ─────────────────────────
                elif name == "fan-state":
                    result["fan_state"] = str(raw_val).lower()

                # ── PSU state (psu1-state, psu2-state) ───────────
                elif name.endswith("-state") and "psu" in name:
                    psu_key = name.replace("-state", "")  # psu1, psu2, ...
                    result["psu"][psu_key] = str(raw_val).lower()

            return result
        except Exception:
            return {}

    # ── Interface List ──
    async def list_interfaces(self):
        """List semua interface beserta status running/disabled."""
        try:
            ifaces = await self._async_req("GET", "interface")
            return ifaces if isinstance(ifaces, list) else []
        except Exception:
            return []

    async def list_pppoe_active(self):
        """Ambil list PPPoE active di RouterOS 7."""
        try:
            items = await self._async_req("GET", "ppp/active")
            return items if isinstance(items, list) else []
        except Exception:
            return []

    async def list_hotspot_active(self):
        """Ambil list Hotspot active di RouterOS 7."""
        try:
            items = await self._async_req("GET", "ip/hotspot/active")
            return items if isinstance(items, list) else []
        except Exception:
            return []

    async def remove_hotspot_active_session(self, username):
        """Putus koneksi (kick) user hotspot yang sedang aktif di RouterOS 7."""
        try:
            active_sessions = await self.list_hotspot_active()
            if isinstance(active_sessions, list):
                for s in active_sessions:
                    if s.get("user") == username:
                        mt_id = s.get(".id")
                        if mt_id:
                            await self._async_req("DELETE", f"ip/hotspot/active/{mt_id}")
            return {"success": True}
        except Exception as e:
            logger.warning(f"Gagal remove hotspot active session '{username}' via REST: {e}")
            return {"success": False, "error": str(e)}

    async def get_isp_interfaces(self):
        """
        Return list of interface names that are marked as ISP/WAN/INPUT uplinks
        via their 'comment' field in MikroTik.

        Keywords checked (case-insensitive) — LOCKED IN CODE (ISP1..ISP20, WAN, INPUT):
          isp, isp1..isp20, wan, wan1..wan20, input, input1..input20,
          uplink, upstream, internet, gateway

        Multi-ISP: semua interface yang match akan dikembalikan (support sampai 20 ISP).
        Falls back to empty list if none found (caller should fallback to 'all physical').
        """
        # ── Keyword ISP detection — dikunci di kode ──────────────────────────────
        ISP_KEYWORDS = (
            "isp",
            *[f"isp{i}" for i in range(1, 21)],   # isp1 .. isp20
            "wan",
            *[f"wan{i}" for i in range(1, 21)],   # wan1 .. wan20
            "input",
            *[f"input{i}" for i in range(1, 21)], # input1 .. input20
            "uplink", "upstream", "internet", "gateway",
        )
        try:
            ifaces = await self._async_req("GET", "interface")
            if not isinstance(ifaces, list):
                return []
            matched = []
            for iface in ifaces:
                comment = str(iface.get("comment", "") or "").lower()
                name = iface.get("name", "")
                if name and any(kw in comment for kw in ISP_KEYWORDS):
                    matched.append(name)
            return matched
        except Exception:
            return []

    async def get_out_interfaces(self):
        """
        Return list of interface names marked as OUT/LOCAL uplinks.
        """
        OUT_KEYWORDS = (
            "out", "local",
            *[f"out{i}" for i in range(1, 21)],
        )
        try:
            ifaces = await self._async_req("GET", "interface")
            if not isinstance(ifaces, list):
                return []
            matched = []
            for iface in ifaces:
                comment = str(iface.get("comment", "") or "").lower()
                name = iface.get("name", "")
                if name and any(kw in comment for kw in OUT_KEYWORDS):
                    matched.append(name)
            return matched
        except Exception:
            return []


    # ── Interface Traffic (monitor-traffic via POST, ROS 7.x) ──
    async def get_interface_traffic(self, interface_name: str = "ether1", duration: int = 1):
        """
        Ambil traffic realtime via /rest/interface/monitor-traffic.
        ROS 7.x: POST dengan body {"interface": "ether1", "once": true}
        CATATAN: ROS 7.16+ wajib pakai boolean True (bukan empty string "")
        Return: {"rx-bits-per-second": ..., "tx-bits-per-second": ...}
        """
        try:
            result = await asyncio.wait_for(
                self._async_req(
                    "POST", "interface/monitor-traffic",
                    {"interface": interface_name, "once": True}  # True bukan ""
                ),
                timeout=8.0
            )
            if isinstance(result, list):
                return result[0] if result else {}
            return result
        except Exception:
            return {}

    async def get_all_interface_stats(self):
        """
        ROS 7: Ambil stats interface fisik (rx-byte, tx-byte) + deteksi ISP interface.
        Return: {
            'stats':          {iface_name: {rx-bytes: int, tx-bytes: int, virtual: bool}},
            'isp_interfaces': [nama-nama interface ISP/WAN yang terdeteksi]
        }
        """
        _SKIP_TYPES = {
            "bridge", "vlan", "pppoe-out", "pppoe-in", "l2tp", "pptp",
            "ovpn-client", "ovpn-server", "sstp-client", "sstp-server",
            "gre", "eoip", "eoipv6", "veth", "sstp", "loopback",
            "6to4", "ipip", "ipip6", "dummy"
        }
        _SKIP_PREFIXES = ("lo", "docker", "veth", "tun", "tap", "<")
        _ISP_KEYWORDS = (
            "isp", *[f"isp{i}" for i in range(1, 21)],
            "wan", *[f"wan{i}" for i in range(1, 21)],
            "input", *[f"input{i}" for i in range(1, 21)],
            "uplink", "upstream", "internet", "gateway",
        )
        try:
            items = await self._async_req("GET", "interface")
            if not isinstance(items, list):
                return {"stats": {}, "isp_interfaces": [], "isp_comments": {}}

            stats = {}
            isp_ifaces = []
            isp_comments = {}

            for item in items:
                name = item.get("name", "")
                itype = str(item.get("type", "")).lower()
                if not name:
                    continue

                raw_comment = str(item.get("comment", "") or "")
                comment = raw_comment.lower()
                if any(kw in comment for kw in _ISP_KEYWORDS):
                    isp_ifaces.append(name)
                    isp_comments[name] = raw_comment

                is_virtual = itype in _SKIP_TYPES or name.lower().startswith(_SKIP_PREFIXES)
                if is_virtual:
                    continue

                stats[name] = {
                    "rx-bytes": int(item.get("rx-byte", 0) or 0),
                    "tx-bytes": int(item.get("tx-byte", 0) or 0),
                }

            return {"stats": stats, "isp_interfaces": isp_ifaces, "isp_comments": isp_comments}
        except Exception as e:
            logger.debug(f"get_all_interface_stats REST gagal: {e}")
            return {"stats": {}, "isp_interfaces": [], "isp_comments": {}}

    # ── IP Address List ──
    async def list_ip_addresses(self):
        """List semua IP address yang dikonfigurasi."""
        try:
            return await self._async_req("GET", "ip/address")
        except Exception:
            return []

    # ── OSPF ──
    async def list_ospf_neighbors(self):
        try:
            return await self._async_req("GET", "routing/ospf/neighbor")
        except Exception:
            return []

    async def list_ospf_instances(self):
        try:
            return await self._async_req("GET", "routing/ospf/instance")
        except Exception:
            return []

    # ── BGP ──
    async def list_bgp_peers(self):
        try:
            return await self._async_req("GET", "routing/bgp/connection")
        except Exception:
            return []

    async def list_bgp_sessions(self):
        try:
            return await self._async_req("GET", "routing/bgp/session")
        except Exception:
            return []

    async def list_bgp_networks(self) -> list:
        """List BGP network announcements (prefixes yang diannounce ke BGP)."""
        try:
            items = await self._async_req("GET", "routing/bgp/network")
            return items if isinstance(items, list) else []
        except Exception:
            return []

    async def add_bgp_network(self, prefix: str, comment: str = "") -> dict:
        """
        Announce prefix ke BGP via /routing/bgp/network (ROS 7.x).
        Digunakan untuk RTBH: announce /32 dengan community 'ASN:666'.
        """
        try:
            payload = {"network": prefix}
            if comment:
                payload["comment"] = comment
            return await self._async_req("PUT", "routing/bgp/network", payload)
        except Exception as e:
            raise Exception(f"Gagal announce BGP network {prefix}: {e}")

    async def remove_bgp_network(self, mt_id: str) -> dict:
        """Cabut pengumuman prefix BGP."""
        try:
            return await self._async_req("DELETE", f"routing/bgp/network/{mt_id}")
        except Exception as e:
            raise Exception(f"Gagal hapus BGP network {mt_id}: {e}")

    async def list_bgp_advertisements(self, connection_name: str = "") -> list:
        """
        List prefixes yang sedang diadvertise ke peer (ROS 7.x).
        Jika connection_name kosong, ambil semua advertisements.
        """
        try:
            path = "routing/bgp/advertisements"
            items = await self._async_req("GET", path)
            if not isinstance(items, list):
                return []
            if connection_name:
                items = [i for i in items if i.get("connection") == connection_name]
            return items
        except Exception:
            return []

    async def list_routing_filters(self) -> list:
        """List routing filter rules (ROS 7.x /routing/filter/rule)."""
        try:
            items = await self._async_req("GET", "routing/filter/rule")
            return items if isinstance(items, list) else []
        except Exception:
            return []

    async def add_bgp_community_filter(
        self,
        chain: str,
        community_value: str,
        action: str = "accept",
        comment: str = ""
    ) -> dict:
        """
        Tambah routing filter rule di MikroTik ROS v7 untuk filter BGP community.

        ROS v7 routing filter language syntax yang benar:
          if (bgp-communities.any(65000:252)) { accept } else { reject }

        Args:
            chain: nama chain filter (contoh: "sentinel-bgp-in-252")
            community_value: community BGP (contoh: "65000:252")
            action: "accept" atau "reject"
            comment: komentar untuk rule ini
        """
        try:
            # ROS v7 routing filter syntax yang valid
            rule_expr = f'if (bgp-communities.any({community_value})) {{ accept }} else {{ reject }}'
            payload = {
                "chain": chain,
                "rule": rule_expr,
            }
            if comment:
                payload["comment"] = comment
            return await self._async_req("PUT", "routing/filter/rule", payload)
        except Exception as e:
            raise Exception(f"Gagal tambah BGP community filter rule: {e}")

    async def remove_routing_filter_rule(self, mt_id: str) -> dict:
        """Hapus routing filter rule berdasarkan .id MikroTik."""
        try:
            return await self._async_req("DELETE", f"routing/filter/rule/{mt_id}")
        except Exception as e:
            raise Exception(f"Gagal hapus routing filter rule {mt_id}: {e}")

    async def set_bgp_connection_input_filter(
        self,
        connection_name: str,
        filter_chain: str
    ) -> dict:
        """
        Set input filter (chain) pada BGP connection di ROS v7.
        Ini mengaktifkan filter community pada BGP session tertentu.

        Args:
            connection_name: nama BGP connection di ROS v7 (contoh: "to-noc-sentinel")
            filter_chain: nama chain filter yang akan dipakai (contoh: "sentinel-bgp-in-252")
        """
        try:
            connections = await self._async_req("GET", "routing/bgp/connection")
            if not isinstance(connections, list):
                raise Exception("Gagal ambil daftar BGP connections")
            for conn in connections:
                name = conn.get("name", "")
                mt_id = conn.get(".id", "")
                if connection_name.lower() in name.lower() or name.lower() in connection_name.lower():
                    if mt_id:
                        return await self._async_req(
                            "PATCH",
                            f"routing/bgp/connection/{mt_id}",
                            {"input.filter": filter_chain}
                        )
            # Tidak ketemu by name — coba ambil semua dan patch yang punya remote address cocok
            raise Exception(f"BGP connection '{connection_name}' tidak ditemukan di MikroTik")
        except Exception as e:
            raise Exception(f"Gagal set BGP connection filter: {e}")

    async def ensure_bgp_community_filter(
        self,
        community_value: str,
        local_as: int = 65000
    ) -> dict:
        """
        Setup lengkap BGP community filter untuk peer ini di MikroTik ROS v7:
        1. Buat chain filter "sentinel-bgp-in" jika belum ada
        2. Tambah rule: accept jika community cocok, reject sisanya
        3. Assign chain ke semua BGP connection yang mengarah ke NOC Sentinel

        Args:
            community_value: community value untuk peer ini (contoh: "65000:252")
            local_as: LOCAL AS GoBGP (default 65000)

        Returns: dict dengan status tiap langkah
        """
        result = {"steps": [], "success": False}
        chain_name = f"sentinel-bgp-in"
        comment = f"Auto-filter by NOC Sentinel — accept only community {community_value}"

        try:
            # ── Langkah 1: Cek existing rules di chain ────────────────────────────
            existing_rules = await self.list_routing_filters()
            sentinel_rules = [r for r in existing_rules if r.get("chain", "") == chain_name]

            # Hapus semua rule lama di chain sentinel-bgp-in untuk rebuild bersih
            for old_rule in sentinel_rules:
                old_id = old_rule.get(".id", "")
                if old_id:
                    try:
                        await self.remove_routing_filter_rule(old_id)
                        result["steps"].append(f"Hapus rule lama {old_id}")
                    except Exception:
                        pass

            # ── Langkah 2: Tambah rule baru ───────────────────────────────────────
            # Rule: accept jika community cocok
            accept_rule = await self.add_bgp_community_filter(
                chain=chain_name,
                community_value=community_value,
                action="accept",
                comment=comment
            )
            result["steps"].append(f"Rule accept community {community_value} ditambahkan")
            result["filter_rule_id"] = accept_rule.get(".id", "")

            # ── Langkah 3: Assign filter ke BGP connection ────────────────────────
            connections = await self._async_req("GET", "routing/bgp/connection")
            if isinstance(connections, list):
                for conn in connections:
                    mt_id = conn.get(".id", "")
                    name = conn.get("name", "")
                    remote_addr = conn.get("remote.address", "")
                    # Cari connection yang mengarah ke NOC Sentinel (10.254.254.254)
                    if "10.254.254.254" in str(remote_addr) or "sentinel" in name.lower() or "noc" in name.lower():
                        try:
                            await self._async_req(
                                "PATCH",
                                f"routing/bgp/connection/{mt_id}",
                                {"input.filter": chain_name}
                            )
                            result["steps"].append(f"Filter '{chain_name}' di-assign ke BGP connection '{name}'")
                        except Exception as patch_err:
                            result["steps"].append(f"Gagal assign filter ke '{name}': {patch_err}")

            result["success"] = True
            result["chain"] = chain_name
            result["community"] = community_value

        except Exception as e:
            result["error"] = str(e)
            result["steps"].append(f"Error: {e}")

        return result

    async def bgp_soft_reset(self, session_name: str = "") -> dict:
        """
        Trigger BGP soft-reset untuk satu atau semua session (ROS 7.x).
        Menggunakan console command via /console endpoint.
        """
        try:
            # ROS 7.x: /routing/bgp/session/{id} — trigger refresh
            if session_name:
                sessions = await self.list_bgp_sessions()
                for s in sessions:
                    name = s.get("name", "")
                    if name == session_name or name.startswith(session_name + "-"):
                        mt_id = s.get(".id", "")
                        if mt_id:
                            try:
                                await self._async_req("POST", f"routing/bgp/session/{mt_id}/refresh", {})
                            except Exception:
                                pass
            return {"success": True, "message": f"BGP soft-reset sent for '{session_name or 'all'}'"}
        except Exception as e:
            raise Exception(f"BGP soft-reset gagal: {e}")

    # ── IP Routes & SD-WAN Route Management ──
    async def list_ip_routes(self, limit: int = 200):
        try:
            routes = await self._async_req("GET", "ip/route")
            return routes[:limit] if isinstance(routes, list) else []
        except Exception:
            return []

    async def add_ip_route(self, dst_address: str, gateway: str, distance: int = 1,
                           routing_table: str = "main", check_gateway: str = "",
                           comment: str = "") -> dict:
        """
        Inject static/SD-WAN route via REST API (ROS 7.x).
        Mendukung multi-gateway ECMP: gateway='gw1,gw2'
        check_gateway: '' | 'ping' | 'arp'
        """
        try:
            payload = {
                "dst-address": dst_address,
                "gateway": gateway,
                "distance": str(distance),
            }
            if routing_table and routing_table != "main":
                payload["routing-table"] = routing_table
            if check_gateway:
                payload["check-gateway"] = check_gateway
            if comment:
                payload["comment"] = comment
            return await self._async_req("PUT", "ip/route", payload)
        except Exception as e:
            raise Exception(f"Gagal tambah route {dst_address}: {e}")

    async def remove_ip_route(self, mt_id: str) -> dict:
        """Hapus route berdasarkan .id MikroTik."""
        try:
            return await self._async_req("DELETE", f"ip/route/{mt_id}")
        except Exception as e:
            raise Exception(f"Gagal hapus route {mt_id}: {e}")

    async def add_mangle_rule(self, chain: str, src_address: str = "",
                              dst_address: str = "", action: str = "mark-routing",
                              routing_mark: str = "", comment: str = "",
                              passthrough: bool = True) -> dict:
        """
        Tambah mangle rule untuk SD-WAN traffic marking (ROS 7.x).
        chain: 'prerouting' | 'output' | 'forward'
        action: 'mark-routing' | 'mark-packet' | 'accept'
        """
        try:
            payload = {"chain": chain, "action": action, "passthrough": str(passthrough).lower()}
            if src_address:
                payload["src-address"] = src_address
            if dst_address:
                payload["dst-address"] = dst_address
            if routing_mark and action in ("mark-routing", "mark-packet"):
                payload["new-routing-mark"] = routing_mark
            if comment:
                payload["comment"] = comment
            return await self._async_req("PUT", "ip/firewall/mangle", payload)
        except Exception as e:
            raise Exception(f"Gagal tambah mangle rule: {e}")

    async def remove_mangle_rule(self, mt_id: str) -> dict:
        """Hapus mangle rule berdasarkan .id"""
        try:
            return await self._async_req("DELETE", f"ip/firewall/mangle/{mt_id}")
        except Exception as e:
            raise Exception(f"Gagal hapus mangle rule {mt_id}: {e}")

    async def list_routing_tables(self) -> list:
        """List routing tables (ROS 7.x — /rest/routing/table)."""
        try:
            items = await self._async_req("GET", "routing/table")
            return items if isinstance(items, list) else []
        except Exception:
            return []

    # ── Active Connections ──
    async def list_connections(self, limit: int = 500):
        try:
            conns = await self._async_req("GET", "ip/firewall/connection")
            return conns[:limit] if isinstance(conns, list) else []
        except Exception:
            return []

    # ── DHCP Leases ──
    async def list_dhcp_leases(self):
        try:
            items = await self._async_req("GET", "ip/dhcp-server/lease")
            return items if isinstance(items, list) else []
        except Exception:
            return []

    # ── Firewall ──
    async def list_firewall_filter(self):
        try:
            return await self._async_req("GET", "ip/firewall/filter")
        except Exception:
            return []

    async def list_firewall_nat(self):
        try:
            return await self._async_req("GET", "ip/firewall/nat")
        except Exception:
            return []

    async def list_firewall_mangle(self):
        try:
            return await self._async_req("GET", "ip/firewall/mangle")
        except Exception:
            return []

    async def get_firewall_address_list(self):
        try:
            return await self._async_req("GET", "ip/firewall/address-list")
        except Exception:
            return []

    async def add_firewall_address_list(self, list_name: str, address: str, comment: str=""):
        try:
            return await self._async_req("PUT", "ip/firewall/address-list", {"list": list_name, "address": address, "comment": comment})
        except Exception as e:
            raise Exception(f"Gagal tambah address-list: {e}")

    async def remove_firewall_address_list(self, mt_id: str):
        try:
            return await self._async_req("DELETE", f"ip/firewall/address-list/{mt_id}")
        except Exception as e:
            raise Exception(f"Gagal hapus address-list: {e}")

    # ── PPPoE (ROS 7.x REST API) ──────────────────────────────────────────────
    # Endpoint: /rest/ppp/secret  (PPPoE user secrets)
    #           /rest/ppp/active  (active PPPoE connections)
    #           /rest/ppp/profile (PPP profiles)

    async def list_pppoe_secrets(self):
        """List PPPoE secrets (users) dari /ppp/secret."""
        try:
            items = await self._async_req("GET", "ppp/secret")
            return items if isinstance(items, list) else []
        except Exception as e:
            logger.warning(f"list_pppoe_secrets REST failed: {e}")
            return []

    async def create_pppoe_secret(self, data):
        """Buat PPPoE secret baru."""
        try:
            return await self._async_req("PUT", "ppp/secret", data)
        except Exception as e:
            raise Exception(f"Gagal membuat PPPoE user: {e}")

    async def update_pppoe_secret(self, mt_id, data):
        """Update PPPoE secret berdasarkan .id MikroTik."""
        try:
            # REST API ROS7: PATCH /ppp/secret/<mt_id>
            return await self._async_req("PATCH", f"ppp/secret/{mt_id}", data)
        except Exception as e:
            raise Exception(f"Gagal mengupdate PPPoE user: {e}")

    async def delete_pppoe_secret(self, mt_id):
        """Hapus PPPoE secret berdasarkan .id MikroTik."""
        try:
            return await self._async_req("DELETE", f"ppp/secret/{mt_id}")
        except Exception as e:
            raise Exception(f"Gagal menghapus PPPoE user: {e}")

    async def update_pppoe_secret_password(self, username: str, new_password: str):
        """Ganti password PPPoE secret berdasarkan username (cari dahulu, lalu PATCH)."""
        try:
            secrets = await self.list_pppoe_secrets()
            for s in secrets:
                if s.get("name") == username:
                    mt_id = s.get(".id", "")
                    if mt_id:
                        return await self._async_req("PATCH", f"ppp/secret/{mt_id}", {"password": new_password})
            # Tidak found — user mungkin RADIUS-only, tidak fatal
            logger.warning(f"update_pppoe_secret_password: user '{username}' tidak ditemukan di MikroTik (mungkin RADIUS-only)")
        except Exception as e:
            raise Exception(f"Gagal update password PPPoE '{username}': {e}")

    async def list_pppoe_active(self):
        """List koneksi PPPoE yang aktif dari /ppp/active."""
        try:
            items = await self._async_req("GET", "ppp/active")
            return items if isinstance(items, list) else []
        except Exception as e:
            logger.warning(f"list_pppoe_active REST failed: {e}")
            return []

    async def disable_pppoe_user(self, username):
        """Disable PPPoE user berdasarkan username."""
        try:
            secrets = await self.list_pppoe_secrets()
            for s in secrets:
                if s.get("name") == username:
                    mt_id = s.get(".id", "")
                    return await self._async_req("PATCH", f"ppp/secret/{mt_id}", {"disabled": "true"})
            raise Exception(f"PPPoE user '{username}' tidak ditemukan")
        except Exception as e:
            raise Exception(f"Gagal disable PPPoE user: {e}")

    async def enable_pppoe_user(self, username):
        """Enable PPPoE user berdasarkan username."""
        try:
            secrets = await self.list_pppoe_secrets()
            for s in secrets:
                if s.get("name") == username:
                    mt_id = s.get(".id", "")
                    return await self._async_req("PATCH", f"ppp/secret/{mt_id}", {"disabled": "false"})
            raise Exception(f"PPPoE user '{username}' tidak ditemukan")
        except Exception as e:
            raise Exception(f"Gagal enable PPPoE user: {e}")

    async def remove_pppoe_active_session(self, username):
        """Hapus (kick) semua active PPPoE session milik username. Return jumlah sesi yang dihapus."""
        try:
            active_sessions = await self.list_pppoe_active()
            removed = 0
            for session in active_sessions:
                if session.get("name") == username:
                    mt_id = session.get(".id", "")
                    if mt_id:
                        try:
                            await self._async_req("DELETE", f"ppp/active/{mt_id}")
                            removed += 1
                        except Exception:
                            pass  # session mungkin sudah tidak ada
            return removed
        except Exception as e:
            logger.warning(f"remove_pppoe_active_session({username}) gagal: {e}")
            return 0

    # ── PPP Profiles ──────────────────────────────────────────────────────────
    async def list_pppoe_profiles(self):
        """List PPP profiles dari /ppp/profile."""
        try:
            items = await self._async_req("GET", "ppp/profile")
            return items if isinstance(items, list) else []
        except Exception as e:
            logger.warning(f"list_pppoe_profiles REST failed: {e}")
            return []

    # ── Hotspot (ROS 7.x REST API) ────────────────────────────────────────────
    async def list_hotspot_users(self):
        try:
            items = await self._async_req("GET", "ip/hotspot/user")
            return items if isinstance(items, list) else []
        except Exception:
            return []

    async def create_hotspot_user(self, data):
        return await self._async_req("PUT", "ip/hotspot/user", data)

    async def update_hotspot_user(self, mt_id, data):
        return await self._async_req("PATCH", f"ip/hotspot/user/{mt_id}", data)

    async def delete_hotspot_user(self, mt_id):
        return await self._async_req("DELETE", f"ip/hotspot/user/{mt_id}")

    async def list_hotspot_active(self):
        try:
            items = await self._async_req("GET", "ip/hotspot/active")
            return items if isinstance(items, list) else []
        except Exception:
            return []

    async def disable_hotspot_user(self, username):
        users = await self.list_hotspot_users()
        for u in users:
            if u.get("name") == username:
                mt_id = u.get(".id", "")
                return await self._async_req("PATCH", f"ip/hotspot/user/{mt_id}", {"disabled": "true"})
        raise Exception(f"Hotspot user '{username}' tidak ditemukan")

    async def enable_hotspot_user(self, username):
        users = await self.list_hotspot_users()
        for u in users:
            if u.get("name") == username:
                mt_id = u.get(".id", "")
                return await self._async_req("PATCH", f"ip/hotspot/user/{mt_id}", {"disabled": "false"})
        raise Exception(f"Hotspot user '{username}' tidak ditemukan")

    async def remove_hotspot_active_session(self, username):
        try:
            active_sessions = await self.list_hotspot_active()
            for s in active_sessions:
                if s.get("user") == username:
                    mt_id = s.get(".id", "")
                    await self._async_req("DELETE", f"ip/hotspot/active/{mt_id}")
            return {"success": True}
        except Exception as e:
            logger.warning(f"Gagal remove hotspot active session '{username}': {e}")
            return {"success": False, "error": str(e)}

    # ── Queues ──
    async def list_simple_queues(self):
        try:
            items = await self._async_req("GET", "queue/simple")
            return items if isinstance(items, list) else []
        except Exception as e:
            logger.warning(f"list_simple_queues REST failed: {e}")
            return []

    async def update_simple_queue(self, mt_id: str, data: dict):
        try:
            return await self._async_req("PATCH", f"queue/simple/{mt_id}", data)
        except Exception as e:
            raise Exception(f"Gagal update simple queue (REST): {e}")

    async def list_hotspot_profiles(self):
        try:
            items = await self._async_req("GET", "ip/hotspot/user/profile")
            return items if isinstance(items, list) else []
        except Exception:
            return []

    async def list_hotspot_servers(self):
        try:
            items = await self._async_req("GET", "ip/hotspot")
            return items if isinstance(items, list) else []
        except Exception:
            return []

    async def list_hotspot_server_profiles(self):
        try:
            items = await self._async_req("GET", "ip/hotspot/profile")
            return items if isinstance(items, list) else []
        except Exception:
            return []

    # ── RADIUS Management (ROS 7.x REST API) ─────────────────────────────────
    async def list_radius_clients(self) -> list:
        """List semua RADIUS client yang terdaftar di MikroTik."""
        try:
            items = await self._async_req("GET", "radius")
            return items if isinstance(items, list) else []
        except Exception as e:
            logger.warning(f"list_radius_clients failed: {e}")
            return []

    async def add_radius_client(
        self, address: str, secret: str,
        service = None, comment: str = "NOC-Billing-Pro"
    ) -> dict:
        """
        Tambah/update RADIUS client di MikroTik (ROS 7 REST).
        FIX #1: timeout=3000 (3 detik) — cegah 'radius not responding'
        FIX #3: 1 entri saja dengan service=[hotspot,ppp]
        """
        if service is None:
            service = ["hotspot", "ppp"]
        try:
            payload = {
                "address": address,
                "secret": secret,
                "service": service if isinstance(service, list) else [service],
                "comment": comment,
                "authentication-port": 1816,
                "accounting-port": 1817,
                "timeout": "3s",   # FIX #1: 3 detik (format MikroTik: '3s')
            }
            existing = await self.list_radius_clients()
            match = next((r for r in existing if r.get("address") == address or r.get("comment") == comment), None)
            if match:
                return await self._async_req("PATCH", f"radius/{match.get('.id', '')}", payload)
            return await self._async_req("PUT", "radius", payload)
        except Exception as e:
            raise Exception(f"Gagal tambah RADIUS client: {e}")

    async def purge_and_reset_radius(self, radius_ip: str, secret: str) -> dict:
        """
        FIX #3: Hapus SEMUA entri RADIUS lama lalu pasang 1 entri bersih.
        Mencegah duplikasi hotspot/ppp yang menyebabkan konflik.
        """
        steps = []
        try:
            existing = await self.list_radius_clients()
            for r in existing:
                mt_id = r.get(".id", "")
                if mt_id:
                    try:
                        await self._async_req("DELETE", f"radius/{mt_id}")
                        steps.append(f"🗑 Hapus RADIUS entry: address={r.get('address')} svc={r.get('service')}")
                    except Exception as e:
                        steps.append(f"⚠️ Gagal hapus entry {mt_id}: {e}")
            # Pasang 1 entri bersih
            await self.add_radius_client(radius_ip, secret, service=["hotspot", "ppp"])
            steps.append(f"✅ 1 RADIUS client baru: {radius_ip} (hotspot+ppp, timeout=3s)")
            return {"success": True, "steps": steps}
        except Exception as e:
            steps.append(f"❌ Error: {e}")
            return {"success": False, "steps": steps}

    async def enable_radius_incoming(self) -> dict:
        """
        FIX #2: Aktifkan /radius incoming CoA listener di MikroTik (port 3799).
        Tanpa ini CoA tidak pernah diterima — perubahan limit harus kick user.
        """
        try:
            try:
                await self._async_req("POST", "radius/incoming/set", {"accept": "true", "port": "3799"})
            except Exception:
                await self._async_req("PATCH", "radius/incoming", {"accept": "true", "port": "3799"})
            logger.info(f"[RADIUS] CoA incoming diaktifkan di {self.host}:3799")
            return {"success": True, "msg": "CoA incoming (port 3799) aktif"}
        except Exception as e:
            logger.warning(f"[RADIUS] Gagal aktifkan incoming di {self.host}: {e}")
            return {"success": False, "error": str(e)}

    async def setup_hotspot_radius(self, radius_ip: str, secret: str, server_profile: str = "hsprof1", pppoe_profile: str = "") -> dict:
        """
        Setup lengkap RADIUS di MikroTik untuk Hotspot & PPPoE (ROS 7):
        1. Purge entri lama, pasang 1 entri bersih (FIX #3)
        2. Aktifkan use-radius di hotspot server profile
        3. Aktifkan CoA incoming port 3799 (FIX #2)
        4. Aktifkan PPP AAA use-radius + interim-update
        """
        steps = []

        # Langkah 1: Purge + reset 1 entri RADIUS bersih
        purge = await self.purge_and_reset_radius(radius_ip, secret)
        steps.extend(purge.get("steps", []))
        if not purge.get("success"):
            return {"success": False, "steps": steps}

        # Langkah 2: Aktifkan use-radius di hotspot profile
        try:
            profiles = await self._async_req("GET", "ip/hotspot/profile")
            if isinstance(profiles, list) and profiles:
                match = next((p for p in profiles if str(p.get("name","")).lower() == server_profile.lower()), None)
                if not match:
                    match = next((p for p in profiles if "hsprof" in str(p.get("name","")).lower()), profiles[0])
                if match:
                    mt_id = match.get(".id", "")
                    await self._async_req("PATCH", f"ip/hotspot/profile/{mt_id}", {"use-radius": "true"})
                    steps.append(f"✅ Hotspot profile '{match.get('name')}' — use-radius=yes")
                else:
                    steps.append("⚠️ Tidak ada hotspot server profile ditemukan")
            else:
                steps.append("⚠️ Data profile hotspot kosong")
        except Exception as e:
            steps.append(f"⚠️ Gagal set use-radius hotspot: {e}")

        # Langkah 3: Aktifkan CoA incoming (FIX #2)
        coa = await self.enable_radius_incoming()
        steps.append("✅ CoA incoming port 3799 aktif" if coa.get("success") else f"⚠️ CoA: {coa.get('error')}")

        # Langkah 4: PPP AAA use-radius + interim-update (agar MikroTik kirim bytes tiap 5 menit)
        if pppoe_profile:
            try:
                try:
                    await self._async_req("POST", "ppp/aaa/set", {"use-radius": "yes", "interim-update": "00:05:00"})
                except Exception:
                    await self._async_req("PATCH", "ppp/aaa", {"use-radius": "true", "interim-update": "00:05:00"})
                steps.append("✅ PPP AAA — use-radius=yes + interim-update=5menit aktif")
            except Exception as e:
                steps.append(f"⚠️ Gagal set PPP AAA: {e}")

        return {"success": True, "steps": steps}

    async def check_radius_enabled(self, server_profile: str = "hsprof1") -> dict:
        """Cek status RADIUS: apakah aktif, berapa entri, CoA status."""
        try:
            profiles = await self._async_req("GET", "ip/hotspot/profile")
            radius_clients = await self.list_radius_clients()
            incoming = {}
            try:
                incoming = await self._async_req("GET", "radius/incoming")
            except Exception:
                pass
            radius_enabled = False
            active_profile = None
            if isinstance(profiles, list):
                for p in profiles:
                    use_rad = str(p.get("use-radius", "false")).lower()
                    if use_rad in ("true", "yes"):
                        radius_enabled = True
                        active_profile = p.get("name")
                        break
            return {
                "radius_enabled": radius_enabled,
                "active_profile": active_profile,
                "radius_clients_count": len(radius_clients),
                "coa_incoming_active": str(incoming.get("accept", "false")).lower() in ("true", "yes") if isinstance(incoming, dict) else False,
                "radius_clients": [
                    {"address": r.get("address"), "service": r.get("service"),
                     "timeout": r.get("timeout"), "comment": r.get("comment")}
                    for r in radius_clients
                ] if isinstance(radius_clients, list) else [],
            }
        except Exception as e:
            return {"radius_enabled": False, "radius_clients": [], "error": str(e)}


    # ── Walled Garden (ROS 7.x REST API) ─────────────────────────────────────
    async def list_walled_garden(self) -> list:
        """List semua Walled Garden entries dari MikroTik."""
        try:
            items = await self._async_req("GET", "ip/hotspot/walled-garden")
            return items if isinstance(items, list) else []
        except Exception as e:
            logger.warning(f"list_walled_garden failed: {e}")
            return []

    async def add_walled_garden_entry(self, server: str, dst_host: str, comment: str = "") -> dict:
        """Tambah satu entry Walled Garden. Skip jika host sudah ada."""
        try:
            existing = await self.list_walled_garden()
            for e in existing:
                if e.get("dst-host") == dst_host:
                    return {"skipped": True, "dst-host": dst_host}
            payload = {"dst-host": dst_host, "action": "allow"}
            if server and server != "all":
                payload["server"] = server
            if comment:
                payload["comment"] = comment
            return await self._async_req("PUT", "ip/hotspot/walled-garden", payload)
        except Exception as e:
            raise Exception(f"Gagal tambah walled garden '{dst_host}': {e}")

    async def setup_walled_garden(self, entries: list, server: str = "all") -> dict:
        """
        Batch tambahkan list domain ke Walled Garden.
        entries: list of str (domain/host) atau list of dict {host, comment}
        Return: {success, added, skipped, steps}
        """
        steps = []
        added = 0
        skipped = 0
        failed = 0
        for entry in entries:
            if isinstance(entry, dict):
                # Handle both 'host' (legacy) and 'dst-host' (standard)
                host    = entry.get("dst-host") or entry.get("host", "")
                comment = entry.get("comment", "NOC-Sentinel")
            else:
                host    = str(entry).strip()
                comment = "NOC-Sentinel"
            if not host:
                continue
            try:
                await self.add_walled_garden_entry(server=server, dst_host=host, comment=comment)
                added += 1
            except Exception as e:
                logger.error(f"Failed to add walled garden entry {host}: {e}")
                failed += 1
                result = await self.add_walled_garden_entry(server=server, dst_host=host, comment=comment)
                if result.get("skipped"):
                    skipped += 1
                    steps.append(f"⏭ Sudah ada: {host}")
                else:
                    added += 1
                    steps.append(f"✅ Ditambahkan: {host}")
            except Exception as e:
                failed += 1
                steps.append(f"❌ Gagal {host}: {e}")
        return {
            "success": failed == 0,
            "added": added,
            "skipped": skipped,
            "failed": failed,
            "steps": steps,
        }


    async def get_netwatch_entries(self) -> list:
        """
        Ambil semua Netwatch probe entries.
        ROS 7.4+: type: icmp | tcp-conn | http-get | https-get | dns
        Fields: host, type, interval, timeout, status, since, comment
        """
        try:
            items = await self._async_req("GET", "tool/netwatch")
            return items if isinstance(items, list) else []
        except Exception:
            return []

    async def add_netwatch_entry(self, data: dict) -> dict:
        """
        Tambah Netwatch probe baru.
        data: {host, type, interval, timeout, comment, http-codes, ...}
        type: 'icmp' | 'tcp-conn' | 'http-get' | 'https-get' | 'dns'
        """
        try:
            return await self._async_req("PUT", "tool/netwatch", data)
        except Exception as e:
            raise Exception(f"Gagal tambah netwatch: {e}")

    async def update_netwatch_entry(self, mt_id: str, data: dict) -> dict:
        """Update Netwatch entry (enable/disable, ubah threshold, dll)."""
        try:
            return await self._async_req("PATCH", f"tool/netwatch/{mt_id}", data)
        except Exception as e:
            raise Exception(f"Gagal update netwatch {mt_id}: {e}")

    async def remove_netwatch_entry(self, mt_id: str) -> dict:
        """Hapus Netwatch probe."""
        try:
            return await self._async_req("DELETE", f"tool/netwatch/{mt_id}")
        except Exception as e:
            raise Exception(f"Gagal hapus netwatch {mt_id}: {e}")

    # ── IP Accounting Snapshot (ROS 7.x REST API) ──────────────────────────────
    async def get_ip_accounting_snapshot(self) -> list:
        """
        Ambil IP Accounting snapshot dari MikroTik ROS 7.x via REST API.

        ROS 7: GET /rest/ip/accounting/snapshot
        Mengembalikan list of entries dengan field:
          src-address, dst-address, bytes, packets

        Pastikan IP Accounting diaktifkan di MikroTik:
          /ip accounting set enabled=yes
          /ip accounting set threshold=unlimited (opsional, untuk menghindari data loss)

        Return: list of {src-address: str, dst-address: str, bytes: int, packets: int}
        """
        try:
            items = await asyncio.wait_for(
                self._async_req("GET", "ip/accounting/snapshot"),
                timeout=25.0
            )
            if isinstance(items, list):
                # Normalisasi: pastikan bytes adalah integer
                result = []
                for entry in items:
                    result.append({
                        "src-address": entry.get("src-address", ""),
                        "dst-address": entry.get("dst-address", ""),
                        "bytes":   int(entry.get("bytes", 0)),
                        "packets": int(entry.get("packets", 0)),
                    })
                return result
            return []
        except asyncio.TimeoutError:
            raise asyncio.TimeoutError(f"Timeout ambil IP Accounting snapshot dari {self.host}")
        except NotImplementedError:
            raise
        except Exception as e:
            err_str = str(e)
            # Jika 404, berarti IP Accounting tidak aktif / endpoint tidak tersedia di versi ini
            if "404" in err_str:
                logger.debug(f"[IPAccounting] {self.host}: endpoint ip/accounting/snapshot tidak tersedia (404) — aktifkan /ip accounting di MikroTik")
                raise NotImplementedError("IP Accounting tidak aktif di device ini")
            raise Exception(f"Gagal ambil IP Accounting snapshot: {err_str}")

    # ── Ping (ROS 7.x REST API) ──
    async def ping_host(self, address: str = "8.8.8.8", count: int = 4, interface: str = ""):
        """
        Melakukan ping dari router ke target address via /rest/ping.
        Mengembalikan list of dict response ping.
        """
        try:
            # ROS 7: coba integer count terlebih dahulu, lalu string jika gagal
            payload = {"address": address, "count": int(count)}
            if interface:
                payload["interface"] = interface
            
            items = await self._async_req("POST", "ping", payload)
            
            # Beberapa versi ROS7 mengembalikan dict tunggal dengan "avg-rtt" (aggregated)
            # Versi lain mengembalikan list per-packet [{time, status}, ...]
            if isinstance(items, dict):
                if "ret" in items:
                    items = items["ret"]
                elif "avg-rtt" in items or "time" in items:
                    # Aggregated result → convert ke list format
                    items = [items]
                else:
                    items = []
                    
            return items if isinstance(items, list) else [items] if items else []
        except Exception as e:
            logger.warning(f"ping_host REST gagal ke {address}: {e}")
            return []



# ═══════════════════════════════════════════════════════════
# RouterOS 6.x — MikroTik API Protocol (port 8728/8729)
# Nama class: MikroTikLegacyAPI
# Alias backward-compat: MikroTikRouterAPI
# ═══════════════════════════════════════════════════════════
import threading
_legacy_api_pools = {}
_legacy_pool_lock = threading.Lock()
_legacy_host_locks = {}

def _get_host_lock(host):
    with _legacy_pool_lock:
        if host not in _legacy_host_locks:
            _legacy_host_locks[host] = threading.Lock()
        return _legacy_host_locks[host]

class MikroTikLegacyAPI(MikroTikBase):
    def __init__(self, host, username, password, port=8728, use_ssl=False, plaintext_login=True):
        self.host = host
        self.username = username
        self.password = password
        self.port = port
        self.use_ssl = use_ssl
        self.plaintext_login = plaintext_login

    def _get_connection(self):
        """Create or reuse a connection pool to the router."""
        pool_key = f"{self.host}:{self.port}:{self.username}"
        with _legacy_pool_lock:
            if pool_key in _legacy_api_pools:
                return _legacy_api_pools[pool_key]

            try:
                pool = routeros_api.RouterOsApiPool(
                    host=self.host,
                    username=self.username,
                    password=self.password,
                    port=self.port,
                    use_ssl=self.use_ssl,
                    ssl_verify=False,
                    plaintext_login=self.plaintext_login,
                )
                _legacy_api_pools[pool_key] = pool
                return pool
            except Exception as e:
                raise Exception(f"Cannot connect to MikroTik API at {self.host}:{self.port} - {e}")

    def _execute(self, callback):
        """Execute a callback sequentially to prevent multithreading corruption on the API socket."""
        pool_key = f"{self.host}:{self.port}:{self.username}"
        host_lock = _get_host_lock(self.host)
        
        max_retries = 1
        
        for attempt in range(max_retries + 1):
            with host_lock:
                pool = self._get_connection()
                try:
                    api = pool.get_api()
                    result = callback(api)
                    return result
                except Exception as e:
                    # Disconnect and clear stale pool
                    try:
                        pool.disconnect()
                    except Exception:
                        pass
                    with _legacy_pool_lock:
                        if pool_key in _legacy_api_pools:
                            del _legacy_api_pools[pool_key]
                    
                    # If it's the last attempt, raise the error
                    if attempt == max_retries:
                        logger.error(f"[MikroTikLegacyAPI] Command failed after {max_retries} retries on {self.host}: {e}")
                        raise

    def _list_resource(self, path):
        def cb(api):
            resource = api.get_resource(path)
            return resource.get()
        return self._execute(cb)

    def _add_resource(self, path, data):
        def cb(api):
            resource = api.get_resource(path)
            # routeros_api uses keyword arguments
            resource.add(**data)
            return {"success": True}
        return self._execute(cb)

    def _set_resource(self, path, mt_id, data):
        def cb(api):
            resource = api.get_resource(path)
            resource.set(id=mt_id, **data)
            return {"success": True}
        return self._execute(cb)

    def _remove_resource(self, path, mt_id):
        def cb(api):
            resource = api.get_resource(path)
            resource.remove(id=mt_id)
            return {"success": True}
        return self._execute(cb)

    # Normalize RouterOS 6 API response to match REST API format
    def _normalize_items(self, items):
        """RouterOS API returns list of dicts with 'id' key. Normalize to match REST format."""
        result = []
        for item in items:
            normalized = {}
            for k, v in item.items():
                normalized[k] = v
            if "id" in normalized and ".id" not in normalized:
                normalized[".id"] = normalized["id"]
            result.append(normalized)
        return result

    async def list_dhcp_leases(self):
        def cb(api):
            return self._normalize_items(api.get_resource('/ip/dhcp-server/lease').get())
        return await asyncio.to_thread(self._execute, cb)

    async def get_firewall_address_list(self):
        items = await asyncio.to_thread(self._list_resource, "/ip/firewall/address-list")
        return self._normalize_items(items)

    async def add_firewall_address_list(self, list_name: str, address: str, comment: str=""):
        return await asyncio.to_thread(self._add_resource, "/ip/firewall/address-list", {"list": list_name, "address": address, "comment": comment})

    async def remove_firewall_address_list(self, mt_id: str):
        return await asyncio.to_thread(self._remove_resource, "/ip/firewall/address-list", mt_id)

    async def test_connection(self):
        try:
            def cb(api):
                resource = api.get_resource("/system/identity")
                return resource.get()
            result = await asyncio.to_thread(self._execute, cb)
            name = result[0].get("name", "") if result else ""
            return {"success": True, "identity": name, "mode": "API Protocol (RouterOS 6+)"}
        except Exception as e:
            return {"success": False, "error": str(e), "mode": "API Protocol (RouterOS 6+)"}

    # ── Suppress Login/Logout Log Spam ────────────────────────────────────────
    async def suppress_account_logging(self) -> bool:
        """Tambahkan pengecualian !account ke rule logging info di ROS6."""
        try:
            def cb(api):
                resource = api.get_resource("/system/logging")
                rules = resource.get()
                
                # Check if already suppressed
                for rule in rules:
                    topics = str(rule.get("topics", "")).lower()
                    if "!account" in topics:
                        return True
                
                # Find default info rule and modify
                for rule in rules:
                    topics = rule.get("topics", "")
                    if topics == "info":
                        resource.set(id=rule.get("id"), topics="info,!account")
                        return True
                return False
                
            result = await asyncio.to_thread(self._execute, cb)
            if result:
                logger.info(f"[suppress_logging] ✅ Log account disembunyikan via Legacy API di {self.host}")
            return bool(result)
        except Exception as e:
            logger.debug(f"[suppress_logging] Gagal set logging rule di {self.host} (Legacy API): {e}")
            return False

    # ── PPPoE ──
    async def list_pppoe_secrets(self):
        items = await asyncio.to_thread(self._list_resource, "/ppp/secret")
        return self._normalize_items(items)

    async def create_pppoe_secret(self, data):
        return await asyncio.to_thread(self._add_resource, "/ppp/secret", data)

    async def update_pppoe_secret(self, mt_id, data):
        return await asyncio.to_thread(self._set_resource, "/ppp/secret", mt_id, data)

    async def delete_pppoe_secret(self, mt_id):
        return await asyncio.to_thread(self._remove_resource, "/ppp/secret", mt_id)

    async def list_pppoe_active(self):
        items = await asyncio.to_thread(self._list_resource, "/ppp/active")
        return self._normalize_items(items)

    async def disable_pppoe_user(self, username):
        secrets = await self.list_pppoe_secrets()
        for s in secrets:
            if s.get("name") == username:
                mt_id = s.get(".id") or s.get("id", "")
                return await asyncio.to_thread(self._set_resource, "/ppp/secret", mt_id, {"disabled": "true"})
        raise Exception(f"PPPoE user '{username}' tidak ditemukan")

    async def enable_pppoe_user(self, username):
        secrets = await self.list_pppoe_secrets()
        for s in secrets:
            if s.get("name") == username:
                mt_id = s.get(".id") or s.get("id", "")
                return await asyncio.to_thread(self._set_resource, "/ppp/secret", mt_id, {"disabled": "false"})
        raise Exception(f"PPPoE user '{username}' tidak ditemukan")

    async def remove_pppoe_active_session(self, username):
        """Kick (hapus) semua active PPPoE session milik username via Legacy API."""
        try:
            active_sessions = await self.list_pppoe_active()
            removed = 0
            for s in active_sessions:
                if s.get("name") == username:
                    mt_id = s.get(".id") or s.get("id", "")
                    if mt_id:
                        try:
                            await asyncio.to_thread(self._remove_resource, "/ppp/active", mt_id)
                            removed += 1
                        except Exception:
                            pass
            return removed
        except Exception as e:
            logger.warning(f"remove_pppoe_active_session Legacy ({username}): {e}")
            return 0

    async def update_pppoe_secret_password(self, username: str, new_password: str):
        """Ganti password PPPoE secret berdasarkan username via Legacy API."""
        secrets = await self.list_pppoe_secrets()
        for s in secrets:
            if s.get("name") == username:
                mt_id = s.get(".id") or s.get("id", "")
                if mt_id:
                    return await asyncio.to_thread(self._set_resource, "/ppp/secret", mt_id, {"password": new_password})
        logger.warning(f"update_pppoe_secret_password Legacy: user '{username}' tidak ditemukan di MikroTik (mungkin RADIUS-only)")

    # ── Hotspot ──
    async def list_hotspot_users(self):
        items = await asyncio.to_thread(self._list_resource, "/ip/hotspot/user")
        return self._normalize_items(items)

    async def create_hotspot_user(self, data):
        return await asyncio.to_thread(self._add_resource, "/ip/hotspot/user", data)

    async def update_hotspot_user(self, mt_id, data):
        return await asyncio.to_thread(self._set_resource, "/ip/hotspot/user", mt_id, data)

    async def delete_hotspot_user(self, mt_id):
        return await asyncio.to_thread(self._remove_resource, "/ip/hotspot/user", mt_id)

    async def list_hotspot_active(self):
        items = await asyncio.to_thread(self._list_resource, "/ip/hotspot/active")
        return self._normalize_items(items)

    async def disable_hotspot_user(self, username):
        users = await self.list_hotspot_users()
        for u in users:
            if u.get("name") == username:
                mt_id = u.get(".id") or u.get("id", "")
                return await asyncio.to_thread(self._set_resource, "/ip/hotspot/user", mt_id, {"disabled": "true"})
        raise Exception(f"Hotspot user '{username}' tidak ditemukan")

    async def enable_hotspot_user(self, username):
        users = await self.list_hotspot_users()
        for u in users:
            if u.get("name") == username:
                mt_id = u.get(".id") or u.get("id", "")
                return await asyncio.to_thread(self._set_resource, "/ip/hotspot/user", mt_id, {"disabled": "false"})
        raise Exception(f"Hotspot user '{username}' tidak ditemukan")

    async def remove_hotspot_active_session(self, username):
        try:
            active_sessions = await self.list_hotspot_active()
            for s in active_sessions:
                if s.get("user") == username:
                    mt_id = s.get(".id") or s.get("id", "")
                    await asyncio.to_thread(self._remove_resource, "/ip/hotspot/active", mt_id)
            return {"success": True}
        except Exception as e:
            logger.warning(f"Gagal remove hotspot active session '{username}': {e}")
            return {"success": False, "error": str(e)}

    async def list_pppoe_profiles(self):
        try:
            items = await asyncio.to_thread(self._list_resource, "/ppp/profile")
            return self._normalize_items(items)
        except Exception:
            return []

    # ── Queues ──
    async def list_simple_queues(self):
        try:
            items = await asyncio.to_thread(self._list_resource, "/queue/simple")
            return self._normalize_items(items)
        except Exception as e:
            logger.warning(f"list_simple_queues API failed: {e}")
            return []

    async def update_simple_queue(self, mt_id: str, data: dict):
        try:
            return await asyncio.to_thread(self._set_resource, "/queue/simple", mt_id, data)
        except Exception as e:
            raise Exception(f"Gagal update simple queue (API): {e}")

    # ── IP Accounting Snapshot (ROS 6.x API Protocol) ──────────────────────────
    async def get_ip_accounting_snapshot(self) -> list:
        """
        Ambil IP Accounting snapshot dari MikroTik ROS 6.x via API Protocol.

        ROS 6 membutuhkan dua langkah:
          1. /ip accounting snapshot take  — ambil snapshot saat ini
          2. /ip accounting snapshot print — baca hasilnya

        Pastikan IP Accounting diaktifkan di MikroTik:
          /ip accounting set enabled=yes

        Return: list of {src-address: str, dst-address: str, bytes: int, packets: int}
        """
        def _take_and_read(api):
            try:
                # Langkah 1: take snapshot (/ip accounting snapshot take)
                snapshot_resource = api.get_resource("/ip/accounting/snapshot")
                try:
                    snapshot_resource.call("take")
                except Exception:
                    pass  # Beberapa ROS6 versi lama tidak punya "take" sub-command

                # Langkah 2: baca isi snapshot
                items = snapshot_resource.get()
                if not items:
                    return []

                result = []
                for entry in items:
                    try:
                        result.append({
                            "src-address": entry.get("src-address", ""),
                            "dst-address": entry.get("dst-address", ""),
                            "bytes":   int(entry.get("bytes", 0)),
                            "packets": int(entry.get("packets", 0)),
                        })
                    except (ValueError, TypeError):
                        continue
                return result
            except Exception as e:
                err_str = str(e)
                if "no such command" in err_str.lower() or "unknown command" in err_str.lower() or "no such item" in err_str.lower():
                    raise NotImplementedError("IP Accounting tidak aktif atau tidak tersedia di device ini")
                raise

        try:
            result = await asyncio.wait_for(
                asyncio.to_thread(self._execute, _take_and_read),
                timeout=25.0
            )
            return result if result else []
        except asyncio.TimeoutError:
            raise asyncio.TimeoutError(f"Timeout ambil IP Accounting snapshot dari {self.host}")
        except NotImplementedError:
            raise
        except Exception as e:
            raise Exception(f"Gagal ambil IP Accounting snapshot (ROS6): {e}")


    async def list_hotspot_profiles(self):
        try:
            items = await asyncio.to_thread(self._list_resource, "/ip/hotspot/user-profile")
            return self._normalize_items(items)
        except Exception:
            try:
                items = await asyncio.to_thread(self._list_resource, "/ip/hotspot/user/profile")
                return self._normalize_items(items)
            except Exception:
                return []

    async def list_hotspot_servers(self):
        try:
            items = await asyncio.to_thread(self._list_resource, "/ip/hotspot")
            return self._normalize_items(items)
        except Exception:
            return []

    async def list_hotspot_server_profiles(self):
        try:
            items = await asyncio.to_thread(self._list_resource, "/ip/hotspot/profile")
            return self._normalize_items(items)
        except Exception:
            return []

    # ── System Resource ──
    async def get_system_identity(self):
        """Ambil nama router dari /system/identity."""
        try:
            items = await asyncio.to_thread(self._list_resource, "/system/identity")
            return items[0].get("name", "") if items else ""
        except Exception:
            return ""

    async def get_system_resource(self):
        """Ambil CPU, memory, uptime dari /system/resource."""
        try:
            items = await asyncio.to_thread(self._list_resource, "/system/resource")
            return items[0] if items else {}
        except Exception:
            return {}

    async def get_system_health(self):
        """
        ROS6: Ambil data health dari /system/health (temperature, voltage).
        Setiap item: {name: 'temperature'|'voltage', value: '30', type: 'C'|'V'}
        Return dict normalized: {cpu_temp, board_temp, voltage, ..., raw: [...]}
        """
        try:
            items = await asyncio.to_thread(self._list_resource, "/system/health")
            if not items:
                return {}

            result = {
                "cpu_temp": 0.0,
                "board_temp": 0.0,
                "sfp_temp": 0.0,
                "switch_temp": 0.0,
                "voltage": 0.0,
                "power": 0.0,
                "fans": {},
                "psu": {},
                "extra_temps": {},
                "raw": items,
            }

            def _f(v):
                try: return float(str(v).strip())
                except Exception: return 0.0

            for entry in items:
                name  = str(entry.get("name", "")).lower().strip()
                value = entry.get("value", "0")
                typ   = str(entry.get("type", "")).upper().strip()

                if typ == "C":  # Temperature
                    if "cpu" in name and "board" not in name:
                        result["cpu_temp"] = _f(value)
                    elif "board" in name:
                        result["board_temp"] = _f(value)
                    elif "sfp" in name or "optical" in name:
                        result["sfp_temp"] = _f(value)
                    elif "switch" in name or "chip" in name:
                        result["switch_temp"] = _f(value)
                    elif "temperature" == name:
                        # Generic 'temperature' entry — biasanya board temp
                        if result["board_temp"] == 0:
                            result["board_temp"] = _f(value)
                        else:
                            result["extra_temps"][name] = _f(value)
                    else:
                        result["extra_temps"][name] = _f(value)

                elif typ == "V":  # Voltage
                    if result["voltage"] == 0:
                        result["voltage"] = _f(value)

                elif typ == "W":  # Power
                    result["power"] = _f(value)

                elif typ == "RPM":
                    result["fans"][name] = int(_f(value))

                elif typ == "":
                    # Beberapa ROS6 tidak ada tipe, tebak dari nama
                    if "fan" in name:
                        result["fans"][name] = int(_f(value))
                    elif "volt" in name:
                        if result["voltage"] == 0:
                            result["voltage"] = _f(value)

            return result
        except Exception as e:
            logger.debug(f"get_system_health ROS6 gagal: {e}")
            return {}

    # ── Interface List ──
    async def list_interfaces(self):
        try:
            items = await asyncio.to_thread(self._list_resource, "/interface")
            return self._normalize_items(items)
        except Exception:
            return []

    async def get_isp_interfaces(self):
        """
        Return list of interface names that are marked as ISP/WAN/INPUT uplinks
        via their 'comment' field in MikroTik.

        Keywords checked (case-insensitive) — LOCKED IN CODE (ISP1..ISP20, WAN, INPUT):
          isp, isp1..isp20, wan, wan1..wan20, input, input1..input20,
          uplink, upstream, internet, gateway

        Multi-ISP: semua interface yang match dikembalikan (support sampai 20 ISP).
        """
        # ── Keyword ISP detection — dikunci di kode ──────────────────────────────
        ISP_KEYWORDS = (
            "isp",
            *[f"isp{i}" for i in range(1, 21)],   # isp1 .. isp20
            "wan",
            *[f"wan{i}" for i in range(1, 21)],   # wan1 .. wan20
            "input",
            *[f"input{i}" for i in range(1, 21)], # input1 .. input20
            "uplink", "upstream", "internet", "gateway",
        )
        try:
            items = await asyncio.to_thread(self._list_resource, "/interface")
            ifaces = self._normalize_items(items)
            matched = []
            for iface in ifaces:
                comment = str(iface.get("comment", "") or "").lower()
                name = iface.get("name", "")
                if name and any(kw in comment for kw in ISP_KEYWORDS):
                    matched.append(name)
            return matched
        except Exception:
            return []

    async def get_out_interfaces(self):
        OUT_KEYWORDS = (
            "out", "local",
            *[f"out{i}" for i in range(1, 21)],
        )
        try:
            items = await asyncio.to_thread(self._list_resource, "/interface")
            ifaces = self._normalize_items(items)
            matched = []
            for iface in ifaces:
                comment = str(iface.get("comment", "") or "").lower()
                name = iface.get("name", "")
                if name and any(kw in comment for kw in OUT_KEYWORDS):
                    matched.append(name)
            return matched
        except Exception:
            return []


    # ── Interface Traffic (RouterOS 6 API) ──
    async def get_interface_traffic(self, interface_name: str = "ether1", duration: int = 1):
        """
        ROS 6: Ambil rx-byte dan tx-byte dari interface stats.
        Digunakan untuk kalkulasi delta bps antara dua polling cycle.
        Return: {"rx-bytes": int, "tx-bytes": int, "name": str}
        (Bukan real-time bps — caller harus hitung delta sendiri)
        """
        try:
            def cb(api):
                resource = api.get_resource("/interface")
                items = resource.get(name=interface_name)
                return items
            items = await asyncio.to_thread(self._execute, cb)
            if items and isinstance(items, list):
                item = items[0]
                return {
                    "name":     interface_name,
                    "rx-bytes": int(item.get("rx-byte", 0) or 0),
                    "tx-bytes": int(item.get("tx-byte", 0) or 0),
                }
            return {}
        except Exception as e:
            logger.debug(f"get_interface_traffic ROS6 gagal untuk {interface_name}: {e}")
            return {}

    async def get_all_interface_stats(self):
        """
        ROS 6: Ambil stats interface fisik (rx-byte, tx-byte) + deteksi ISP interface.
        Semua dalam 1 koneksi ke MikroTik — efisien.

        Return: {
            'stats':          {iface_name: {rx-bytes: int, tx-bytes: int}},
            'isp_interfaces': [nama-nama interface ISP/WAN yang terdeteksi]
        }

        ISP detection menggunakan keyword di field 'comment'.
        Dilakukan dalam 1 loop — tidak perlu koneksi/call terpisah.
        """
        _SKIP_TYPES = {
            "bridge", "vlan", "pppoe-out", "pppoe-in", "l2tp", "pptp",
            "ovpn-client", "ovpn-server", "sstp-client", "sstp-server",
            "gre", "eoip", "eoipv6", "veth", "sstp", "loopback",
            "6to4", "ipip", "ipip6",
        }
        _SKIP_PREFIXES = ("lo", "docker", "veth", "tun", "tap", "<")
        _ISP_KEYWORDS = (
            "isp", *[f"isp{i}" for i in range(1, 21)],
            "wan", *[f"wan{i}" for i in range(1, 21)],
            "input", *[f"input{i}" for i in range(1, 21)],
            "uplink", "upstream", "internet", "gateway",
        )
        try:
            items = await asyncio.to_thread(self._list_resource, "/interface")
            stats              = {}
            isp_ifaces         = []
            isp_comments: dict = {}   # {iface_name: original_comment}
            for item in items:
                name  = item.get("name", "")
                itype = item.get("type", "").lower()
                if not name:
                    continue
                # Deteksi ISP/WAN dari comment (satu loop, tidak perlu call terpisah)
                raw_comment = str(item.get("comment", "") or "")
                comment     = raw_comment.lower()
                if any(kw in comment for kw in _ISP_KEYWORDS):
                    isp_ifaces.append(name)
                    isp_comments[name] = raw_comment   # simpan comment asli (case-preserved)
                # Skip virtual/internal interfaces
                if itype in _SKIP_TYPES or name.lower().startswith(_SKIP_PREFIXES):
                    continue
                stats[name] = {
                    "rx-bytes": int(item.get("rx-byte", 0) or 0),
                    "tx-bytes": int(item.get("tx-byte", 0) or 0),
                }
            return {"stats": stats, "isp_interfaces": isp_ifaces, "isp_comments": isp_comments}
        except Exception as e:
            logger.debug(f"get_all_interface_stats ROS6 gagal: {e}")
            return {"stats": {}, "isp_interfaces": [], "isp_comments": {}}


    # ── IP Address List ──
    async def list_ip_addresses(self):
        try:
            items = await asyncio.to_thread(self._list_resource, "/ip/address")
            return self._normalize_items(items)
        except Exception:
            return []

    # ── BGP ──
    async def list_bgp_peers(self):
        try:
            items = await asyncio.to_thread(self._list_resource, "/routing/bgp/peer")
            return self._normalize_items(items)
        except Exception:
            return []

    async def list_bgp_sessions(self):
        return []  # RouterOS 6 doesn't have separate sessions

    # ── OSPF ──
    async def list_ospf_neighbors(self):
        try:
            items = await asyncio.to_thread(self._list_resource, "/routing/ospf/neighbor")
            return self._normalize_items(items)
        except Exception:
            return []

    async def list_ospf_instances(self):
        try:
            items = await asyncio.to_thread(self._list_resource, "/routing/ospf/instance")
            return self._normalize_items(items)
        except Exception:
            return []

    # ── IP Routes ──
    async def list_ip_routes(self, limit: int = 200):
        try:
            items = await asyncio.to_thread(self._list_resource, "/ip/route")
            return self._normalize_items(items)[:limit]
        except Exception:
            return []

    async def add_ip_route(self, dst_address: str, gateway: str, distance: int = 1,
                           routing_table: str = "main", check_gateway: str = "",
                           comment: str = "") -> dict:
        """Inject static route via ROS 6 API Protocol."""
        try:
            data = {"dst-address": dst_address, "gateway": gateway, "distance": str(distance)}
            if check_gateway:
                data["check-gateway"] = check_gateway
            if comment:
                data["comment"] = comment
            return await asyncio.to_thread(self._add_resource, "/ip/route", data)
        except Exception as e:
            raise Exception(f"Gagal tambah route {dst_address}: {e}")

    async def remove_ip_route(self, mt_id: str) -> dict:
        """Hapus route by .id (ROS 6)."""
        try:
            return await asyncio.to_thread(self._remove_resource, "/ip/route", mt_id)
        except Exception as e:
            raise Exception(f"Gagal hapus route {mt_id}: {e}")

    async def add_mangle_rule(self, chain: str, src_address: str = "",
                              dst_address: str = "", action: str = "mark-routing",
                              routing_mark: str = "", comment: str = "",
                              passthrough: bool = True) -> dict:
        """Tambah mangle rule via ROS 6 API Protocol."""
        try:
            data = {"chain": chain, "action": action, "passthrough": "yes" if passthrough else "no"}
            if src_address:
                data["src-address"] = src_address
            if dst_address:
                data["dst-address"] = dst_address
            if routing_mark:
                data["new-routing-mark"] = routing_mark
            if comment:
                data["comment"] = comment
            return await asyncio.to_thread(self._add_resource, "/ip/firewall/mangle", data)
        except Exception as e:
            raise Exception(f"Gagal tambah mangle rule: {e}")

    async def remove_mangle_rule(self, mt_id: str) -> dict:
        """Hapus mangle rule (ROS 6)."""
        try:
            return await asyncio.to_thread(self._remove_resource, "/ip/firewall/mangle", mt_id)
        except Exception as e:
            raise Exception(f"Gagal hapus mangle rule {mt_id}: {e}")

    async def add_bgp_network(self, prefix: str, comment: str = "") -> dict:
        """Announce prefix ke BGP (ROS 6 /routing/bgp/network)."""
        try:
            data = {"network": prefix}
            if comment:
                data["comment"] = comment
            return await asyncio.to_thread(self._add_resource, "/routing/bgp/network", data)
        except Exception as e:
            raise Exception(f"Gagal announce BGP {prefix}: {e}")

    async def remove_bgp_network(self, mt_id: str) -> dict:
        """Cabut pengumuman prefix BGP (ROS 6)."""
        try:
            return await asyncio.to_thread(self._remove_resource, "/routing/bgp/network", mt_id)
        except Exception as e:
            raise Exception(f"Gagal hapus BGP network {mt_id}: {e}")

    async def list_bgp_networks(self) -> list:
        """List BGP network announcements (ROS 6)."""
        try:
            items = await asyncio.to_thread(self._list_resource, "/routing/bgp/network")
            return self._normalize_items(items)
        except Exception:
            return []

    async def get_netwatch_entries(self) -> list:
        """List Netwatch entries (ROS 6)."""
        try:
            items = await asyncio.to_thread(self._list_resource, "/tool/netwatch")
            return self._normalize_items(items)
        except Exception:
            return []

    async def add_netwatch_entry(self, data: dict) -> dict:
        """Tambah Netwatch probe (ROS 6)."""
        try:
            return await asyncio.to_thread(self._add_resource, "/tool/netwatch", data)
        except Exception as e:
            raise Exception(f"Gagal tambah netwatch: {e}")

    async def update_netwatch_entry(self, mt_id: str, data: dict) -> dict:
        """Update Netwatch entry (ROS 6)."""
        try:
            return await asyncio.to_thread(self._set_resource, "/tool/netwatch", mt_id, data)
        except Exception as e:
            raise Exception(f"Gagal update netwatch: {e}")

    async def remove_netwatch_entry(self, mt_id: str) -> dict:
        """Hapus Netwatch probe (ROS 6)."""
        try:
            return await asyncio.to_thread(self._remove_resource, "/tool/netwatch", mt_id)
        except Exception as e:
            raise Exception(f"Gagal hapus netwatch: {e}")

    # ── Active Connections ──
    async def list_connections(self, limit: int = 500):
        try:
            items = await asyncio.to_thread(self._list_resource, "/ip/firewall/connection")
            return self._normalize_items(items)[:limit]
        except Exception:
            return []

    # ── Firewall ──
    async def list_firewall_filter(self):
        try:
            items = await asyncio.to_thread(self._list_resource, "/ip/firewall/filter")
            return self._normalize_items(items)
        except Exception:
            return []

    async def list_firewall_nat(self):
        try:
            items = await asyncio.to_thread(self._list_resource, "/ip/firewall/nat")
            return self._normalize_items(items)
        except Exception:
            return []

    async def list_firewall_mangle(self):
        try:
            items = await asyncio.to_thread(self._list_resource, "/ip/firewall/mangle")
            return self._normalize_items(items)
        except Exception:
            return []

    async def get_firewall_address_list(self, list_name: str = "") -> list:
        """List firewall address-list entries (ROS 6)."""
        try:
            items = await asyncio.to_thread(self._list_resource, "/ip/firewall/address-list")
            normalized = self._normalize_items(items)
            if list_name:
                normalized = [i for i in normalized if i.get("list") == list_name]
            return normalized
        except Exception:
            return []

    async def add_firewall_address_list(self, list_name: str, address: str, comment: str = "") -> dict:
        """Tambah IP ke firewall address-list (ROS 6)."""
        try:
            payload = {"list": list_name, "address": address}
            if comment:
                payload["comment"] = comment
            return await asyncio.to_thread(self._add_resource, "/ip/firewall/address-list", payload)
        except Exception as e:
            raise Exception(f"Gagal tambah address-list: {e}")

    async def remove_firewall_address_list(self, mt_id: str) -> dict:
        """Hapus IP dari firewall address-list (ROS 6)."""
        try:
            return await asyncio.to_thread(self._remove_resource, "/ip/firewall/address-list", mt_id)
        except Exception as e:
            raise Exception(f"Gagal hapus address-list: {e}")

    async def list_ip_routes(self, limit: int = 500) -> list:
        """List IP routes (ROS 6)."""
        try:
            items = await asyncio.to_thread(self._list_resource, "/ip/route")
            return self._normalize_items(items)[:limit]
        except Exception:
            return []

    async def add_ip_route(self, dst_address: str, gateway: str, distance: int = 1,
                           routing_table: str = "main", check_gateway: str = "",
                           comment: str = "") -> dict:
        """Inject static route (ROS 6)."""
        try:
            payload = {
                "dst-address": dst_address,
                "gateway": gateway,
                "distance": str(distance),
            }
            if check_gateway:
                payload["check-gateway"] = check_gateway
            if comment:
                payload["comment"] = comment
            return await asyncio.to_thread(self._add_resource, "/ip/route", payload)
        except Exception as e:
            raise Exception(f"Gagal inject route: {e}")

    async def remove_ip_route(self, mt_id: str) -> dict:
        """Hapus IP route (ROS 6)."""
        try:
            return await asyncio.to_thread(self._remove_resource, "/ip/route", mt_id)
        except Exception as e:
            raise Exception(f"Gagal hapus route: {e}")

    async def add_mangle_rule(self, chain: str, src_address: str = "", dst_address: str = "",
                              action: str = "mark-routing", routing_mark: str = "",
                              comment: str = "", passthrough: bool = True) -> dict:
        """Tambah mangle rule (ROS 6) untuk SD-WAN failover."""
        try:
            payload = {
                "chain": chain,
                "action": action,
                "passthrough": "yes" if passthrough else "no",
            }
            if src_address:
                payload["src-address"] = src_address
            if dst_address:
                payload["dst-address"] = dst_address
            if routing_mark:
                payload["new-routing-mark"] = routing_mark
            if comment:
                payload["comment"] = comment
            return await asyncio.to_thread(self._add_resource, "/ip/firewall/mangle", payload)
        except Exception as e:
            raise Exception(f"Gagal tambah mangle rule: {e}")

    async def remove_mangle_rule(self, mt_id: str) -> dict:
        """Hapus mangle rule (ROS 6)."""
        try:
            return await asyncio.to_thread(self._remove_resource, "/ip/firewall/mangle", mt_id)
        except Exception as e:
            raise Exception(f"Gagal hapus mangle rule: {e}")

    async def list_bgp_networks(self) -> list:
        """List BGP network announcements (ROS 6)."""
        try:
            items = await asyncio.to_thread(self._list_resource, "/routing/bgp/network")
            return self._normalize_items(items)
        except Exception:
            return []

    async def add_bgp_network(self, prefix: str, comment: str = "") -> dict:
        """Announce prefix ke BGP (ROS 6) — untuk RTBH."""
        try:
            payload = {"network": prefix}
            if comment:
                payload["comment"] = comment
            return await asyncio.to_thread(self._add_resource, "/routing/bgp/network", payload)
        except Exception as e:
            raise Exception(f"Gagal tambah BGP network: {e}")

    async def remove_bgp_network(self, mt_id: str) -> dict:
        """Hapus BGP network announcement (ROS 6)."""
        try:
            return await asyncio.to_thread(self._remove_resource, "/routing/bgp/network", mt_id)
        except Exception as e:
            raise Exception(f"Gagal hapus BGP network: {e}")

    # ── Session Counters ──
    async def list_pppoe_active(self):
        try:
            items = await asyncio.to_thread(self._list_resource, "/ppp/active")
            return self._normalize_items(items)
        except Exception:
            return []

    async def list_hotspot_active(self):
        try:
            items = await asyncio.to_thread(self._list_resource, "/ip/hotspot/active")
            return self._normalize_items(items)
        except Exception:
            return []



    # ── Ping (ROS 6.x API Protocol) ──
    async def ping_host(self, address: str = "8.8.8.8", count: int = 4, interface: str = ""):
        """
        Melakukan ping dari router ke target address via command /ping.
        Mengembalikan list of dict response ping.
        """
        try:
            def cb(api):
                resource = api.get_resource("/")
                args = {"address": address, "count": str(count)}
                if interface:
                    args["interface"] = interface
                return resource.call("ping", args)
            
            items = await asyncio.to_thread(self._execute, cb)
            return self._normalize_items(items) if items else []
        except Exception as e:
            logger.debug(f"ping_host API Protocol gagal ke {address}: {e}")
            return []

    # ── RADIUS Management (ROS 6.x API Protocol) ──
    async def list_radius_clients(self) -> list:
        try:
            items = await asyncio.to_thread(self._list_resource, "/radius")
            return self._normalize_items(items)
        except Exception:
            return []

    async def add_radius_client(
        self, address: str, secret: str,
        service = None, comment: str = "NOC-Billing-Pro"
    ) -> dict:
        """
        Tambah/update RADIUS client di MikroTik (ROS 6 Legacy API).
        FIX #1: timeout=3000ms — cegah 'radius not responding'
        FIX #3: service=hotspot,ppp — 1 entri untuk keduanya
        """
        if service is None:
            service = "hotspot,ppp"
        if isinstance(service, list):
            service = ",".join(service)
        try:
            existing = await self.list_radius_clients()
            match = next((r for r in existing if r.get("address") == address or r.get("comment") == comment), None)
            data = {
                "address": address,
                "secret": secret,
                "service": service,
                "comment": comment,
                "authentication-port": "1816",
                "accounting-port": "1817",
                "timeout": "3s",   # FIX #1: 3 detik timeout
            }
            if match:
                mt_id = match.get(".id") or match.get("id", "")
                return await asyncio.to_thread(self._set_resource, "/radius", mt_id, data)
            return await asyncio.to_thread(self._add_resource, "/radius", data)
        except Exception as e:
            raise Exception(f"Gagal tambah RADIUS client (ROS6): {e}")

    async def purge_and_reset_radius(self, radius_ip: str, secret: str) -> dict:
        """
        FIX #3: Hapus SEMUA entri RADIUS lama, pasang 1 entri bersih (ROS 6).
        """
        steps = []
        try:
            existing = await self.list_radius_clients()
            for r in existing:
                mt_id = r.get(".id") or r.get("id", "")
                if mt_id:
                    try:
                        await asyncio.to_thread(self._remove_resource, "/radius", mt_id)
                        steps.append(f"🗑 Hapus RADIUS: addr={r.get('address')} svc={r.get('service')}")
                    except Exception as e:
                        steps.append(f"⚠️ Gagal hapus {mt_id}: {e}")
            await self.add_radius_client(radius_ip, secret, service="hotspot,ppp")
            steps.append(f"✅ 1 RADIUS client baru: {radius_ip} (hotspot+ppp, timeout=3s)")
            return {"success": True, "steps": steps}
        except Exception as e:
            steps.append(f"❌ Error: {e}")
            return {"success": False, "steps": steps}

    async def enable_radius_incoming(self) -> dict:
        """
        FIX #2: Aktifkan /radius incoming CoA listener (port 3799) — ROS 6 Legacy.
        """
        try:
            def cb(api):
                res = api.get_resource("/radius/incoming")
                res.set(**{"accept": "yes", "port": "3799"})
            await asyncio.to_thread(self._execute, cb)
            logger.info(f"[RADIUS] CoA incoming diaktifkan di {self.host}:3799 (ROS6)")
            return {"success": True, "msg": "CoA incoming (port 3799) aktif"}
        except Exception as e:
            logger.warning(f"[RADIUS] Gagal aktifkan incoming di {self.host}: {e}")
            return {"success": False, "error": str(e)}

    async def setup_hotspot_radius(self, radius_ip: str, secret: str, server_profile: str = "hsprof1", pppoe_profile: str = "") -> dict:
        """
        Setup lengkap RADIUS di MikroTik untuk Hotspot & PPPoE (ROS 6):
        1. Purge entri lama, pasang 1 entri bersih (FIX #3)
        2. Aktifkan use-radius di hotspot server profile
        3. Aktifkan CoA incoming port 3799 (FIX #2)
        4. Aktifkan PPP AAA use-radius + interim-update
        """
        steps = []

        # Langkah 1: Purge + reset 1 entri RADIUS bersih
        purge = await self.purge_and_reset_radius(radius_ip, secret)
        steps.extend(purge.get("steps", []))
        if not purge.get("success"):
            return {"success": False, "steps": steps}

        # Langkah 2: Aktifkan use-radius di hotspot server profile
        try:
            def get_server_profiles(api):
                return api.get_resource("/ip/hotspot/profile").get()
            raw_profiles = await asyncio.to_thread(self._execute, get_server_profiles)
            profiles = self._normalize_items(raw_profiles)

            if profiles:
                match = next((p for p in profiles if str(p.get("name", "")).lower() == server_profile.lower()), None)
                if not match:
                    match = next((p for p in profiles if "hsprof" in str(p.get("name", "")).lower()), None)
                if not match:
                    match = profiles[0]

                if match:
                    mt_id = match.get(".id") or match.get("id", "")
                    prof_name = match.get("name", "profile")
                    await asyncio.to_thread(self._set_resource, "/ip/hotspot/profile", mt_id, {"use-radius": "yes"})
                    steps.append(f"✅ Profile '{prof_name}' — use-radius=yes diaktifkan")
                else:
                    steps.append("⚠️ Tidak ada hotspot server profile ditemukan")
            else:
                steps.append("⚠️ Hotspot server profile kosong — pastikan hotspot sudah dikonfigurasi di MikroTik")
        except Exception as e:
            steps.append(f"⚠️ Gagal set use-radius di profile hotspot: {e}")

        # Langkah 3: Aktifkan CoA incoming (FIX #2)
        coa = await self.enable_radius_incoming()
        steps.append("✅ CoA incoming port 3799 aktif" if coa.get("success") else f"⚠️ CoA: {coa.get('error')}")

        # Langkah 4: PPP AAA use-radius + interim-update 5 menit
        if pppoe_profile:
            try:
                def set_ppp_aaa(api):
                    res = api.get_resource("/ppp/aaa")
                    res.set(**{"use-radius": "yes", "interim-update": "00:05:00"})
                await asyncio.to_thread(self._execute, set_ppp_aaa)
                steps.append("✅ PPP AAA — use-radius=yes + interim-update=5menit aktif")
            except Exception as e:
                steps.append(f"⚠️ Gagal set PPP AAA: {e}")

        return {"success": True, "steps": steps}


    async def check_radius_enabled(self, server_profile: str = "hsprof1") -> dict:
        try:
            def get_profiles(api):
                return api.get_resource("/ip/hotspot/profile").get()
            
            raw_profiles = await asyncio.to_thread(self._execute, get_profiles)
            profiles = self._normalize_items(raw_profiles)
            radius_clients = await self.list_radius_clients()
            
            radius_enabled = False
            active_profile = None
            for p in profiles:
                if str(p.get("use-radius", "no")).lower() in ("yes", "true"):
                    radius_enabled = True
                    active_profile = p.get("name")
                    break
            
            return {
                "radius_enabled": radius_enabled,
                "active_profile": active_profile,
                "radius_clients": [
                    {"address": r.get("address"), "service": r.get("service"), "comment": r.get("comment")}
                    for r in radius_clients
                ]
            }
        except Exception as e:
            return {"radius_enabled": False, "radius_clients": [], "error": str(e)}

    # ── Walled Garden (ROS 6.x API Protocol) ──
    async def list_walled_garden(self) -> list:
        try:
            items = await asyncio.to_thread(self._list_resource, "/ip/hotspot/walled-garden")
            return self._normalize_items(items)
        except Exception:
            return []

    async def add_walled_garden_entry(self, server: str, dst_host: str, comment: str = "") -> dict:
        try:
            existing = await self.list_walled_garden()
            for e in existing:
                if e.get("dst-host") == dst_host:
                    return {"skipped": True}
            
            data = {"dst-host": dst_host, "action": "allow"}
            if server and server != "all":
                data["server"] = server
            if comment:
                data["comment"] = comment
            
            return await asyncio.to_thread(self._add_resource, "/ip/hotspot/walled-garden", data)
        except Exception:
            return {"success": False}

    async def setup_walled_garden(self, entries: list, server: str = "all") -> dict:
        added = 0
        skipped = 0
        for entry in entries:
            host = entry.get("dst-host") or entry.get("host") if isinstance(entry, dict) else str(entry)
            comment = entry.get("comment", "") if isinstance(entry, dict) else ""
            if not host: continue
            
            res = await self.add_walled_garden_entry(server, host, comment)
            if res.get("skipped"): skipped += 1
            else: added += 1
            
        return {"success": True, "added": added, "skipped": skipped}

# Backward compatibility alias
MikroTikRouterAPI = MikroTikLegacyAPI


# ═══════════════════════════════════════════════════════════
# Helper — extract hanya host dari ip_address (tanpa port)
# Digunakan untuk SNMP dan ICMP ping yang memerlukan plain IP
# ═══════════════════════════════════════════════════════════
def get_host_only(ip_address: str) -> str:
    """Ambil hanya bagian host dari 'host:port' format."""
    host, _ = parse_host_port(ip_address)
    return host


# ═══════════════════════════════════════════════════════════
# Discovery & Version Detection
# ═══════════════════════════════════════════════════════════
async def discover_device(device: dict) -> dict:
    """
    Deteksi otomatis mode API yang tepat untuk device ini.

    Urutan coba:
      1. REST API (port 443 HTTPS atau 80 HTTP) → mode=rest  (ROS 7.x)
      2. API Protocol (port 8728)               → mode=api   (ROS 6.x)

    Return dict:
      {
        "api_mode":      "rest" | "api" | "unknown",
        "version_major": 7 | 6 | 0,
        "ros_version":   "7.x.x" | "6.x.x" | "",
        "board_name":    str,
        "detected_at":   float (timestamp),
        "success":       bool,
      }

    Simpan hasil ke DB agar tidak re-discover setiap siklus 30 detik.
    Caller (polling) cukup re-discover jika `api_mode` belum ada di device,
    atau jika polling gagal berkali-kali dan mau coba mode lain.
    """
    import time
    raw_ip = device.get("ip_address", "")
    parsed_host, port_from_ip = parse_host_port(raw_ip)

    result = {
        "api_mode":      "unknown",
        "version_major": 0,
        "ros_version":   "",
        "board_name":    "",
        "detected_at":   time.time(),
        "success":       False,
    }

    # ── Coba REST API (ROS 7.x) ───────────────────────────────────────────────
    # Urutan port: custom port dari ip_address → 443 (HTTPS) → 80 (HTTP)
    rest_ports_ssl = []
    if port_from_ip is not None:
        rest_ports_ssl.append((port_from_ip, port_from_ip in (443, 8443)))
    rest_ports_ssl += [(443, True), (80, False)]

    for rest_port, use_ssl in rest_ports_ssl:
        try:
            rest_client = MikroTikRestAPI(
                host=parsed_host, username=device.get("api_username", "admin"),
                password=device.get("api_password", ""),
                port=rest_port, use_ssl=use_ssl,
            )
            # Override timeout menjadi pendek (5s) agar discovery cepat
            rest_client.timeout = 5
            test = await rest_client.test_connection()
            if test.get("success"):
                # Ambil versi ROS
                try:
                    sys_res = await asyncio.wait_for(
                        rest_client._async_req("GET", "system/resource"), timeout=5
                    )
                    ros_ver = sys_res.get("version", "") if isinstance(sys_res, dict) else ""
                    board   = sys_res.get("board-name", "") if isinstance(sys_res, dict) else ""
                except Exception:
                    ros_ver, board = "", ""

                ver_major = 7
                if ros_ver and ros_ver[0].isdigit():
                    try:
                        ver_major = int(ros_ver.split(".")[0])
                    except Exception:
                        pass

                result.update({
                    "api_mode":      "rest",
                    "version_major": ver_major,
                    "ros_version":   ros_ver,
                    "board_name":    board,
                    "success":       True,
                    "rest_port":     rest_port,
                    "use_https":     use_ssl,
                })
                logger.info(
                    f"Discovery [{device.get('name','?')}@{parsed_host}]: "
                    f"REST API OK port={rest_port} ssl={use_ssl} ROS={ros_ver}"
                )
                return result
        except Exception:
            pass

    # ── Coba API Protocol (ROS 6.x) ───────────────────────────────────────────
    api_port = port_from_ip if port_from_ip is not None else (device.get("api_port") or 8728)
    try:
        api_client = MikroTikRouterAPI(
            host=parsed_host,
            username=device.get("api_username", "admin"),
            password=device.get("api_password", ""),
            port=api_port,
            use_ssl=device.get("api_ssl", False),
            plaintext_login=device.get("api_plaintext_login", True),
        )
        test = await asyncio.wait_for(api_client.test_connection(), timeout=8)
        if test.get("success"):
            try:
                sys_res = await asyncio.wait_for(api_client.get_system_resource(), timeout=5)
                ros_ver = sys_res.get("version", "") if isinstance(sys_res, dict) else ""
                board   = sys_res.get("board-name", "") if isinstance(sys_res, dict) else ""
            except Exception:
                ros_ver, board = "", ""

            ver_major = 6
            if ros_ver and ros_ver[0].isdigit():
                try:
                    ver_major = int(ros_ver.split(".")[0])
                except Exception:
                    pass

            result.update({
                "api_mode":      "api",
                "version_major": ver_major,
                "ros_version":   ros_ver,
                "board_name":    board,
                "success":       True,
                "api_port":      api_port,
            })
            logger.info(
                f"Discovery [{device.get('name','?')}@{parsed_host}]: "
                f"API Protocol OK port={api_port} ROS={ros_ver}"
            )
            return result
    except Exception as e:
        logger.debug(f"Discovery API Protocol gagal [{parsed_host}]: {e}")

    logger.warning(
        f"Discovery [{device.get('name','?')}@{parsed_host}]: "
        f"Semua mode gagal — pastikan kredensial dan port benar"
    )
    return result


# ═══════════════════════════════════════════════════════════
# Factory function
# ═══════════════════════════════════════════════════════════
def get_api_client(device: dict) -> MikroTikBase:
    """
    Create the appropriate MikroTik API client based on device config.
    Mendukung ip_address dalam format 'host' atau 'host:port'.
    Jika ip_address mengandung port (host:port), port tersebut digunakan
    secara otomatis dan WWW Port / API Port field diabaikan.
    """
    mode = device.get("api_mode", "rest")
    raw_ip = device.get("ip_address", "")

    # Parse host:port dari ip_address
    parsed_host, port_from_ip = parse_host_port(raw_ip)

    if mode == "api":
        # RouterOS 6.x — API Protocol (MikroTikLegacyAPI)
        port = port_from_ip if port_from_ip is not None else (device.get("api_port") or 8728)
        logger.info(f"Creating MikroTikLegacyAPI client: host={parsed_host}, port={port}")
        return MikroTikLegacyAPI(
            host=parsed_host,
            username=device.get("api_username", "admin"),
            password=device.get("api_password", ""),
            port=port,
            use_ssl=device.get("api_ssl", False),
            plaintext_login=device.get("api_plaintext_login", True),
        )
    else:
        # RouterOS 7.x — REST API (MikroTikRestAPI)
        use_https = device.get("use_https", False)
        default_port = 443 if use_https else 80
        port = port_from_ip if port_from_ip is not None else (device.get("api_port") or default_port)
        logger.info(f"Creating MikroTikRestAPI client: host={parsed_host}, port={port}, https={use_https}")
        return MikroTikRestAPI(
            host=parsed_host,
            username=device.get("api_username", "admin"),
            password=device.get("api_password", ""),
            port=port,
            use_ssl=use_https,
        )
