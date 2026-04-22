"""
UDP Syslog server for receiving syslog messages from MikroTik devices.
Listens on port 5514 (configurable via SYSLOG_PORT env var).
Parses RFC3164 syslog format and stores in MongoDB.

Peering-Eye Integration:
  Secara paralel, server ini juga mendeteksi baris DNS query dari MikroTik,
  mengekstrak domain + client_ip, mencocokkan platform, dan mengakumulasi
  stats setiap 60 detik ke collection peering_eye_stats.

MikroTik config:
  /system logging action add name=noc-dns target=remote remote=<IP_NOC> remote-port=5514 bsd-syslog=yes
  /system logging add topics=dns action=noc-dns
"""
import asyncio
import logging
import os
import re
import time
import uuid
from collections import defaultdict, deque
from datetime import datetime, timezone, timedelta
from core.db import get_db

logger = logging.getLogger(__name__)
SYSLOG_PORT    = int(os.environ.get("SYSLOG_PORT",    "5514"))
FLUSH_INTERVAL = int(os.environ.get("PEERING_FLUSH",  "60"))    # detik

# ── Rate Limiter per-IP ───────────────────────────────────────────────────────
# Mencegah 1 MikroTik flooding syslog hingga membebani CPU server.
# Konfigurasi via env var SYSLOG_RATE_LIMIT (default: 200 paket/detik per IP)
# Untuk disable rate limiting, set SYSLOG_RATE_LIMIT=0
SYSLOG_RATE_LIMIT = int(os.environ.get("SYSLOG_RATE_LIMIT", "200"))  # paket/detik
SYSLOG_RATE_WINDOW = 1.0  # window 1 detik

# { ip_address: deque of timestamps }
_rate_tracker: dict = defaultdict(lambda: deque())
_rate_drop_counter: dict = defaultdict(int)  # track total dropped per IP


def _is_rate_limited(ip: str) -> bool:
    """Return True jika IP ini sudah melewati batas rate limit."""
    if SYSLOG_RATE_LIMIT <= 0:
        return False  # rate limiting disabled
    now = time.monotonic()
    dq = _rate_tracker[ip]
    # Hapus timestamp yang sudah lewat window
    cutoff = now - SYSLOG_RATE_WINDOW
    while dq and dq[0] < cutoff:
        dq.popleft()
    if len(dq) >= SYSLOG_RATE_LIMIT:
        _rate_drop_counter[ip] += 1
        # Log warning setiap 1000 paket yang di-drop agar tidak banjir log
        if _rate_drop_counter[ip] % 1000 == 0:
            logger.warning(
                f"[RateLimit] {ip} melebihi {SYSLOG_RATE_LIMIT} pkt/s — "
                f"total dropped: {_rate_drop_counter[ip]}"
            )
        return True
    dq.append(now)
    return False

# ── Regex untuk NOC-METRICS push dari MikroTik Scheduler ─────────────────────
# Format yang di-push oleh script MikroTik:
#   log info "NOC-METRICS: cpu=35 ram=62"
# Syslog yang diterima berisi string tersebut di field message.
_METRICS_RE = re.compile(
    r"NOC-METRICS:\s*cpu=(\d+)\s+ram=(\d+)",
    re.IGNORECASE
)

# ══════════════════════════════════════════════════════════════════════════════
# RFC3164 Parser
# ══════════════════════════════════════════════════════════════════════════════

SEVERITY = ["emergency", "alert", "critical", "error", "warning", "notice", "info", "debug"]
FACILITY = ["kern", "user", "mail", "system", "security", "syslogd", "lpd", "news",
            "uucp", "clockd", "security2", "ftp", "ntp", "logaudit", "logalert", "cron",
            "local0", "local1", "local2", "local3", "local4", "local5", "local6", "local7"]

RFC3164_RE = re.compile(
    r"^<(\d+)>"
    r"(?:(\w{3}\s+\d+\s+\d{2}:\d{2}:\d{2})\s+)?"  # optional timestamp
    r"(?:(\S+)\s+)?"                                  # optional hostname
    r"(.+)$",                                         # message
    re.DOTALL,
)

# ══════════════════════════════════════════════════════════════════════════════
# Peering-Eye DNS Platform Patterns (default — will merge with DB patterns)
# ══════════════════════════════════════════════════════════════════════════════

DEFAULT_PLATFORM_PATTERNS = [
    # ── Perbankan Indonesia (Digital & Komersial) ───────────────────────────
    (r"(bca\.co\.id|klikbca\.com|bca\.id|mybca\.id)", "Bank BCA", "🏦", "#1e3a8a"),
    (r"(bankmandiri\.co\.id|livinbymandiri\.com)", "Bank Mandiri", "🏦", "#fbbf24"),
    (r"(bri\.co\.id|brimo\.id|linkaja\.id)", "Bank BRI", "🏦", "#0369a1"),
    (r"(bni\.co\.id|bni-it\.com)", "Bank BNI", "🏦", "#ea580c"),
    (r"(bankbsi\.co\.id)", "Bank Syariah Indonesia", "🏦", "#0d9488"),
    (r"(btn\.co\.id)", "Bank BTN", "🏦", "#1d4ed8"),
    (r"(cimbniaga\.co\.id|octoclicks\.co\.id)", "Bank CIMB Niaga", "🏦", "#be123c"),
    (r"(danamon\.co\.id)", "Bank Danamon", "🏦", "#f97316"),
    (r"(permatabank\.com)", "Bank Permata", "🏦", "#10b981"),
    (r"(jenius\.com|btpn\.com)", "Bank Jenius / BTPN", "🏦", "#0ea5e9"),
    (r"(jago\.com)", "Bank Jago", "🏦", "#fbbf24"),
    (r"(seabank\.co\.id)", "Bank Seabank", "🏦", "#f97316"),
    (r"(allobank\.com)", "Bank Allo", "🏦", "#9333ea"),
    (r"(blubybcadigital\.id)", "Bank Blu by BCA", "🏦", "#06b6d4"),

    # ── Situs Pemerintah & Edukasi (Indonesia) ──────────────────────────
    (r"(pajak\.go\.id)", "Pajak Online (DJP)", "🏛️", "#0369a1"),
    (r"(kemdikbud\.go\.id|belajar\.id|simpkb\.id)", "Kemdikbud / Edukasi", "🎓", "#3b82f6"),
    (r"(kemenkes\.go\.id|pedulilindungi\.id|satusehat\.kemkes\.go\.id)", "Kemenkes / SatuSehat", "🏥", "#0d9488"),
    (r"(polri\.go\.id)", "Kepolisian RI", "👮", "#1e40af"),
    (r"(tni\.mil\.id)", "TNI RI", "🪖", "#166534"),
    (r"(go\.id|bps\.go\.id|menpan\.go\.id|setneg\.go\.id)", "Situs Pemerintah RI", "🏛️", "#ef4444"),
    (r"(ac\.id|sch\.id|dikti\.go\.id)", "Institusi Pendidikan", "🎓", "#6366f1"),

    # ── Marketplaces & Shopping ──────────────────────────────────────────
    (r"(tokopedia\.com|tkpd\.io)", "Tokopedia", "🛒", "#22c55e"),
    (r"(shopee\.co\.id|seacdn\.com|shopeemobile\.com)", "Shopee", "🛍️", "#f97316"),
    (r"(bukalapak\.com|bl\.id)", "Bukalapak", "🛒", "#be123c"),
    (r"(blibli\.com|bliblicdn\.net)", "Blibli", "🛒", "#0ea5e9"),
    (r"(lazada\.co\.id|lzdcdn\.net)", "Lazada", "🛍️", "#1d4ed8"),
    (r"(zalora\.co\.id)", "Zalora", "🛍️", "#000000"),
    (r"(traveloka\.com)", "Traveloka", "✈️", "#0ea5e9"),
    (r"(tiket\.com)", "Tiket.com", "🎫", "#2563eb"),
    (r"(gojek\.com|gotogroup\.com)", "Gojek/GoTo", "🚗", "#10b981"),
    (r"(grab\.com)", "Grab", "🚕", "#059669"),

    # ── Media Berita & Portal Lokal ─────────────────────────────────────
    (r"(detik\.com|detik\.net)", "Detikcom", "📰", "#1e40af"),
    (r"(kompas\.com|kompasiana\.com|kompas\.id)", "Kompas", "📰", "#ea580c"),
    (r"(viva\.co\.id)", "VivaNews", "📰", "#dc2626"),
    (r"(merdeka\.com)", "Merdeka", "📰", "#dc2626"),
    (r"(kaskus\.co\.id|kcdn\.id)", "Kaskus", "👥", "#1e3a8a"),
    (r"(suara\.com)", "Suara", "📰", "#dc2626"),
    (r"(tribunnews\.com|tribunx\.com)", "TribunNews", "📰", "#2563eb"),
    (r"(idntimes\.com)", "IDN Times", "📰", "#ef4444"),
    (r"(liputan6\.com)", "Liputan6", "📰", "#f97316"),
    (r"(sindonews\.com)", "SindoNews", "📰", "#1d4ed8"),

    # ── Gaming & Esports (Sangat Penting) ────────────────────────────────
    (r"(riotgames\.com|leagueoflegends\.com|valorant\.com|pvp\.net)", "Valorant / Riot", "⚔️", "#e11d48"),
    (r"(garena\.com|garenanow\.com|pb\.id|freefiremobile\.com)", "Garena / Free Fire", "🎮", "#f97316"),
    (r"(hoyoverse\.com|mihoyo\.com|hoyolab\.com|genshin\.com)", "HoYoverse (Genshin)", "⚔️", "#6366f1"),
    (r"(ml\.igg\.com|moonton\.com|mobilelegends\.com|waywubi83\.com|fa4wu9a4f\.com)", "Mobile Legends", "⚔️", "#eab308"),
    (r"(pubgmobile\.com|tencentgames\.com)", "PUBG Mobile", "🔫", "#f59e0b"),
    (r"(roblox\.com|rbxcdn\.com)", "Roblox", "🧱", "#f8fafc"),
    (r"(steampowered\.com|steamcontent\.com|steamcommunity\.com)", "Steam", "🎮", "#1b2838"),
    (r"(epicgames\.com|unrealengine\.com)", "Epic Games", "🎮", "#334155"),
    (r"(supercell\.com|clashofclans\.com)", "Supercell", "⚔️", "#fbbf24"),
    (r"(ubisoft\.com)", "Ubisoft", "🎮", "#2563eb"),
    (r"(activision\.com|callofduty\.com)", "Activision", "🔫", "#000000"),

    # ── Video & Musik Streaming ─────────────────────────────────────────
    (r"(youtube\.com|googlevideo\.com|ytimg\.com|youtu\.be)", "YouTube", "▶️", "#ef4444"),
    (r"(netflix\.com|nflxvideo\.net|nflximg\.net|nflxso\.net)", "Netflix", "🎬", "#f43f5e"),
    (r"(tiktok\.com|tiktokv\.com|tiktokcdn\.com|byteoversea\.com|ibyteimg\.com|snssdk\.com|bytedance\.com|bytewlb|pglstatp\.com|byteglb\.com)", "TikTok", "🎵", "#ec4899"),
    (r"(spotify\.com|scdn\.co|spotifycdn\.com)", "Spotify", "🎧", "#22c55e"),
    (r"(vidio\.com)", "Vidio", "📺", "#be123c"),
    (r"(mola\.tv)", "Mola TV", "📺", "#1d4ed8"),
    (r"(disneyplus\.com|bamgrid\.com)", "Disney+", "🎬", "#3b82f6"),
    (r"(twitch\.tv|twitchsvc\.net)", "Twitch", "🎮", "#a855f7"),

    # ── Sosial & Messaging ──────────────────────────────────────────────
    (r"(facebook\.com|fb\.com|fbcdn\.net|fbsbx\.com|facebook\.net)", "Facebook", "👥", "#3b82f6"),
    (r"(instagram\.com|cdninstagram\.com|ig\.me)", "Instagram", "📸", "#d946ef"),
    (r"(twitter\.com|x\.com|twimg\.com|t\.co)", "Twitter/X", "🐦", "#e2e8f0"),
    (r"(whatsapp\.com|whatsapp\.net)", "WhatsApp", "💬", "#10b981"),
    (r"(telegram\.org|t\.me|telegram\.me)", "Telegram", "✈️", "#0ea5e9"),
    (r"(discord\.com|discordapp\.com|discord\.gg)", "Discord", "🎮", "#6366f1"),
    (r"(reddit\.com|redditstatic\.com)", "Reddit", "👽", "#ff4500"),
    (r"(snackvideo\.com|kwaicdn\.com|kwai\.net|kwai-pro\.com|kwaipros\.com|adaether\.com)", "SnackVideo", "🎵", "#fbbf24"),

    # ── Judi & Porn (Wajib Blokir/Monitor) ──────────────────────────────
    (r"(sbobet|m88|slot88|pragmatic|joker123|togel|mahjongways|zeus138|slotgacor|maxwin|bet365|1xbet|dafabet|w88)", "Judi Online", "🎲", "#be123c"),
    (r"(pornhub|xvideos|xnxx|redtube|xhamster|brazzers|onlyfans|spankbang|nhentai|bokep|simontok)", "Situs Dewasa", "🔞", "#000000"),

    # ── Infrastruktur & Cloud ───────────────────────────────────────────
    (r"(googleapis\.com|gstatic\.com|google\.com|goo\.gl|googletagmanager|ggpht\.com|doubleclick\.net|google-analytics\.com|gvt2\.com|crashlytics\.com)", "Google", "🔍", "#4285f4"),
    (r"(microsoft\.com|msn\.com|live\.com|hotmail\.com|outlook\.com|office\.com|windows\.com|azureedge\.net|microsoftonline\.com|skype\.com|bing\.com)", "Microsoft", "🪟", "#38bdf8"),
    (r"(icloud\.com|apple\.com|mzstatic\.com|cdn-apple\.com|apple-dns\.net|aaplimg\.com)", "Apple/iCloud", "🍎", "#94a3b8"),
    (r"(cloudflare\.com|cloudflare\.net|cloudflare-dns\.com)", "Cloudflare", "☁️", "#f97316"),
    (r"(amazon\.com|amazonaws\.com|cloudfront\.net|awsstatic\.com|amazonvideo\.com)", "Amazon/AWS", "📦", "#f59e0b"),
    (r"(akamai\.net|akamaiedge\.net|akamaitechnologies\.com|edgekey\.net|edgesuite\.net)", "Akamai CDN", "🌍", "#14b8a6"),
    (r"(fastly\.net|fastlylb\.net)", "Fastly CDN", "🌍", "#f43f5e"),
    (r"(xiaomi\.com|miui\.com|mi\.com|micloud\.com|mipush\.com|xiaomi\.eu)", "Xiaomi / POCO", "📱", "#f97316"),
    (r"(samsung\.com|samsungcloud\.com|samsungosp\.com|samsungapps\.com)", "Samsung", "📱", "#1d4ed8"),
    (r"(coloros\.com|oppomobile\.com|heytapmobile\.com|oppo\.com|heytap\.com|heytapdl\.com|otidapi\.com)", "Oppo", "📱", "#16a34a"),
    (r"(realmemobile\.com|realme\.com)", "Realme", "📱", "#fbbf24"),
    (r"(vivoglobal\.com|vivo\.com|vivosmartphone\.cn)", "Vivo / iQOO", "📱", "#3b82f6"),
    (r"(infinixmobility\.com|tecno-mobile\.com|itel-mobile\.com|oraimo\.com|transsion\.com|shalltry\.com|transsion-os\.com)", "Infinix / Tecno (Transsion)", "📱", "#0ea5e9"),
    (r"(huawei\.com|hihonor\.com|hicloud\.com|vmall\.com|dbankcloud\.com|hwccpc\.com|hwclouds-dns\.com)", "Huawei / Honor", "📱", "#dc2626"),
    (r"(asus\.com|asuscomm\.com)", "Asus / ROG", "📱", "#082f49"),
    (r"(oneplus\.com|oneplusbbs\.com)", "OnePlus", "📱", "#ef4444"),
    (r"(pool\.ntp\.org|time\.android\.com|time\.g\.aaplimg\.com)", "Time/NTP Services", "🕒", "#94a3b8"),
    (r"(allawntech\.com|emptyfieldgrassm\.com|appsflyersdk\.com|mythad\.com|vungle\.com|ap4r\.com|app-analytics-services\.com|applovin\.com)", "Ads & Mobile Tracking", "🕵️", "#000000"),
    (r"(3gppnetwork\.org)", "Telco Services (VoWiFi/VoLTE)", "📶", "#f97316"),
    (r"(jquery\.com|bootstrapcdn\.com|cdnjs\.cloudflare\.com)", "Web Libs & CDN", "📦", "#6366f1"),
]

# ══════════════════════════════════════════════════════════════════════════════
# In-memory accumulators (flushed every FLUSH_INTERVAL)
# ══════════════════════════════════════════════════════════════════════════════

# {(device_id, platform): {"hits": N, "bytes": 0, "device_name": "", "icon": .., "color": .., "domains": {}, "clients": {}}}
_dns_acc: dict = defaultdict(lambda: {"hits": 0, "bytes": 0, "device_name": "", "icon": "🌐", "color": "#64748b", "domains": defaultdict(int), "clients": defaultdict(int)})
_platform_cache: list = []      # list of (regex, name, icon, color)
_platform_cache_ts: float = 0.0
_device_cache: dict = {}        # ip → {id, name}
_device_cache_ts: float = 0.0
_db_miss_ts: dict = {}          # {ip: timestamp} — IP yg sudah di-cari ke DB tapi tidak ketemu
DB_MISS_COOLDOWN = 300          # detik — jeda sebelum retry DB lookup untuk IP yg sama

# ── DNS regex helpers ──────────────────────────────────────────────────────────
_DNS_QUERY_RE  = re.compile(r"query\s+from\s+([0-9.]+).*?:\s+#?\d*\s*([a-z0-9\-\.]+\.[a-z]{2,})", re.IGNORECASE)
_DNS_QUERY_RE2 = re.compile(r"got\s+query\s+from\s+([0-9.]+)", re.IGNORECASE)
# ROS 7 format: "dns query: 192.168.1.10 for youtube.com" atau "dns,debug query youtube.com from 192.168.1.10"
_DNS_QUERY_RE3 = re.compile(r"(?:dns\s+query[:\s]+|query\s+)([a-z0-9\-\.]+\.[a-z]{2,})\s+from\s+([0-9.]+)", re.IGNORECASE)
_DOMAIN_RE     = re.compile(r"\b((?:[a-z0-9\-]+\.)+(?:com|net|org|id|io|co|tv|me|app|dev|biz|info|cloud|media|cdn))\b", re.IGNORECASE)
_CLIENT_IP_RE  = re.compile(r"from\s+([0-9]{1,3}\.[0-9]{1,3}\.[0-9]{1,3}\.[0-9]{1,3})", re.IGNORECASE)

SKIP_DOMAINS = ("in-addr.arpa", ".local", "localhost", "wpad", ".arpa")


def _match_platform(domain: str) -> tuple:
    """Match domain to platform. Returns (name, icon, color)."""
    d = domain.lower().strip(".")
    for pattern, name, icon, color in _platform_cache:
        try:
            if re.search(pattern, d):
                return name, icon, color
        except re.error:
            continue
    return "Others", "🌐", "#64748b"


def _is_dns_query(message: str) -> bool:
    """Detect if a syslog message is a MikroTik DNS query log.
    
    Format yang didukung:
    - ROS 6: 'query from 192.168.1.10: 1234 A youtube.com'
    - ROS 7: 'dns,debug query youtube.com from 192.168.1.10'
    - ROS 7 alt: 'dns query: youtube.com from 192.168.1.10'
    """
    msg = message.lower()
    # ROS 6 format
    if "query" in msg and ("from" in msg or "dns" in msg):
        return True
    # ROS 7 dns,debug format
    if "dns" in msg and ("query" in msg or "lookup" in msg):
        return True
    return False


def _parse_dns_entry(source_ip: str, hostname: str, message: str) -> dict | None:
    """Extract DNS info from a syslog message. Returns None if not a DNS query."""
    if not _is_dns_query(message):
        return None

    # Extract domain
    domain_m = _DOMAIN_RE.search(message)
    if not domain_m:
        return None
    domain = domain_m.group(1).lower().strip(".")

    # Skip infrastructure domains
    if any(domain.endswith(s) or domain == s.strip(".") for s in SKIP_DOMAINS):
        return None
    if len(domain) < 4:
        return None

    # Extract client IP
    client_m = _CLIENT_IP_RE.search(message)
    client_ip = client_m.group(1) if client_m else None

    # Resolve device_id from sender IP
    # ── PENTING: jika device cache kosong (baru start), gunakan IP dulu
    # Cache akan diisi oleh _refresh_caches() yang jalan paralel
    dev = _device_cache.get(source_ip, {})
    # SELALU gunakan UUID jika tersedia, fallback ke IP jika belum ada di cache
    device_id   = dev.get("id") or source_ip    # UUID jika ada, IP jika tidak
    device_name = dev.get("name") or hostname or source_ip

    platform, icon, color = _match_platform(domain)

    return {
        "device_id":   device_id,
        "device_name": device_name,
        "domain":      domain,
        "client_ip":   client_ip,
        "platform":    platform,
        "icon":        icon,
        "color":       color,
    }


# ══════════════════════════════════════════════════════════════════════════════
# RFC3164 Syslog Parser
# ══════════════════════════════════════════════════════════════════════════════

def parse_syslog(data: bytes, addr: tuple) -> dict:
    """Parse a syslog UDP packet into a structured dict."""
    try:
        raw = data.decode("utf-8", errors="replace").strip()
    except Exception:
        raw = str(data)

    now = datetime.now(timezone.utc).isoformat()
    source_ip = addr[0]

    m = RFC3164_RE.match(raw)
    if m:
        pri_str, ts_str, hostname, message = m.groups()
        pri = int(pri_str)
        facility_num = pri >> 3
        severity_num = pri & 7
        severity = SEVERITY[severity_num] if severity_num < len(SEVERITY) else "unknown"
        facility = FACILITY[facility_num] if facility_num < len(FACILITY) else "local"
        hostname = hostname or source_ip
        message = (message or "").strip()
    else:
        severity = "info"
        facility = "local"
        hostname = source_ip
        message = raw

    return {
        "timestamp":  now,
        "source_ip":  source_ip,
        "hostname":   hostname or source_ip,
        "facility":   facility,
        "severity":   severity,
        "message":    message,
        "raw":        raw[:500],
    }


# ══════════════════════════════════════════════════════════════════════════════
# Asyncio Protocol
# ══════════════════════════════════════════════════════════════════════════════

class SyslogProtocol(asyncio.DatagramProtocol):
    def __init__(self, syslog_queue: asyncio.Queue, dns_queue: asyncio.Queue, metrics_queue: asyncio.Queue):
        self.syslog_q   = syslog_queue
        self.dns_q      = dns_queue
        self.metrics_q  = metrics_queue

    def datagram_received(self, data: bytes, addr: tuple):
        source_ip = addr[0]

        # ── Rate Limiter per-IP ────────────────────────────────────────────────
        # Drop paket jika IP ini mengirim terlalu cepat (>200 pkt/s default).
        # NOC-METRICS TETAP diproses meskipun terkena rate limit (prioritas tinggi).
        entry = parse_syslog(data, addr)
        msg   = entry.get("message", "")

        # ── NOC-METRICS interceptor (SELALU diproses, tidak terkena rate limit) ─
        # Jika MikroTik mengirim baris NOC-METRICS, proses terpisah dan JANGAN
        # simpan ke syslog_entries agar tidak mencemari log.
        m = _METRICS_RE.search(msg)
        if m:
            try:
                self.metrics_q.put_nowait({
                    "source_ip": entry["source_ip"],
                    "cpu":       int(m.group(1)),
                    "ram":       int(m.group(2)),
                })
            except asyncio.QueueFull:
                pass
            return   # STOP — tidak lanjut ke syslog_queue

        # Terapkan rate limit untuk paket non-METRICS
        if _is_rate_limited(source_ip):
            return   # Drop paket — IP ini flooding

        # → syslog_entries (raw log)
        try:
            self.syslog_q.put_nowait(entry)
        except asyncio.QueueFull:
            logger.warning(f"Syslog queue full! Dropped from {source_ip}")
        # → DNS queue for Peering-Eye processing
        if _is_dns_query(msg):
            try:
                self.dns_q.put_nowait((entry["source_ip"], entry["hostname"], msg))
            except asyncio.QueueFull:
                pass

    def error_received(self, exc):
        logger.warning(f"Syslog UDP error: {exc}")


# ══════════════════════════════════════════════════════════════════════════════
# NOC-METRICS Consumer: tulis CPU & RAM ke MongoDB
# ══════════════════════════════════════════════════════════════════════════════

async def _metrics_processor(metrics_queue: asyncio.Queue):
    """
    Konsumer untuk pesan NOC-METRICS dari MikroTik.
    Mencocokkan source_ip ke device di DB lalu update cpu_load & memory_usage.
    """
    logger.info("[NOC-METRICS] Processor dimulai — menunggu update CPU/RAM dari MikroTik...")
    while True:
        try:
            item = await metrics_queue.get()
            try:
                source_ip = item["source_ip"]
                cpu       = item["cpu"]
                ram       = item["ram"]

                # Lookup device_id dari cache (diisi oleh _refresh_caches)
                dev = _device_cache.get(source_ip, {})
                device_id = dev.get("id", "")

                if not device_id:
                    # Fallback: cari ke DB via ip_address, bgp_peer_ip, atau vpn_ip
                    db     = get_db()
                    ip_esc = re.escape(source_ip)
                    doc    = await db.devices.find_one(
                        {"$or": [
                            {"ip_address": {"$regex": f"^{ip_esc}(:\\d+)?$"}},
                            {"bgp_peer_ip": source_ip},
                            {"vpn_ip": source_ip},
                        ]},
                        {"id": 1, "name": 1, "_id": 0}
                    )
                    if doc:
                        device_id = doc["id"]
                        # Masukkan ke cache agar tidak re-query
                        _device_cache[source_ip] = {"id": device_id, "name": doc.get("name", source_ip)}

                if device_id:
                    db = get_db()
                    await db.devices.update_one(
                        {"id": device_id},
                        {"$set": {
                            "cpu_load":     cpu,
                            "memory_usage": ram,
                            # Update last_traffic juga agar Wall Display langsung baca
                            "last_traffic.cpu":    cpu,
                            "last_traffic.memory_percent": ram,
                        }}
                    )
                    logger.debug(f"[NOC-METRICS] {source_ip} → cpu={cpu}% ram={ram}%")
                else:
                    logger.debug(f"[NOC-METRICS] IP tidak dikenal: {source_ip}")

            except Exception as e:
                logger.error(f"[NOC-METRICS] Error proses item: {e}")
            finally:
                metrics_queue.task_done()

        except asyncio.CancelledError:
            logger.info("[NOC-METRICS] Processor dihentikan")
            break


# ══════════════════════════════════════════════════════════════════════════════
# Background Workers
# ══════════════════════════════════════════════════════════════════════════════

async def _db_writer(queue: asyncio.Queue):
    """Consumer: reads from syslog queue and inserts into MongoDB."""
    while True:
        try:
            entry = await queue.get()
            try:
                db = get_db()
                await db.syslog_entries.insert_one(entry)
            except Exception as e:
                logger.error(f"Syslog DB write error: {e}")
            finally:
                queue.task_done()
        except asyncio.CancelledError:
            logger.info("Syslog DB writer shutting down")
            break


async def _refresh_caches():
    """Refresh device + platform caches from MongoDB every 5 minutes."""
    global _device_cache, _device_cache_ts, _platform_cache, _platform_cache_ts
    import time as _t
    while True:
        try:
            db = get_db()
            # Device cache: ip_address → {id, name}
            devs = await db.devices.find({}, {"_id": 0, "id": 1, "name": 1, "ip_address": 1, "bgp_peer_ip": 1, "vpn_ip": 1}).to_list(1000)
            new_dev = {}
            for d in devs:
                device_info = {"id": d.get("id", ""), "name": d.get("name", "")}

                # Index by management IP
                ip = (d.get("ip_address") or "").split(":")[0].strip()
                if ip:
                    new_dev[ip] = device_info

                # Index by BGP/Tunnel IP (PENTING untuk Peering-Eye via VPN)
                tunnel_ip = (d.get("bgp_peer_ip") or "").strip()
                if tunnel_ip:
                    new_dev[tunnel_ip] = device_info

                # Index by VPN IP khusus (field vpn_ip jika dikonfigurasi)
                vpn_ip_field = (d.get("vpn_ip") or "").strip()
                if vpn_ip_field and vpn_ip_field not in new_dev:
                    new_dev[vpn_ip_field] = device_info

            _device_cache = new_dev
            _device_cache_ts = _t.time()
            # Bersihkan _db_miss_ts untuk IP yang sekarang sudah diketahui
            for _miss_ip in list(_db_miss_ts.keys()):
                if _miss_ip in _device_cache:
                    del _db_miss_ts[_miss_ip]
            logger.info(f"[PeeringEye] Device cache refreshed: {len(_device_cache)} devices")

            # Platform cache from DB
            docs = await db.peering_platforms.find({"is_active": {"$ne": False}}, {"_id": 0}).to_list(500)
            if docs:
                _platform_cache = [(d.get("regex_pattern", ""), d["name"], d.get("icon", "🌐"), d.get("color", "#64748b")) for d in docs]
                logger.info(f"[PeeringEye] Platform cache refreshed: {len(_platform_cache)} platforms from DB")
            else:
                # Seed DB with defaults and use defaults
                ops = []
                for pat, name, icon, color in DEFAULT_PLATFORM_PATTERNS:
                    ops.append({"id": str(uuid.uuid4()), "name": name, "regex_pattern": pat, "icon": icon, "color": color, "is_active": True})
                if ops:
                    try:
                        await db.peering_platforms.insert_many(ops)
                        logger.info(f"[PeeringEye] Seeded {len(ops)} default platforms to DB")
                    except Exception:
                        pass
                _platform_cache = DEFAULT_PLATFORM_PATTERNS
        except asyncio.CancelledError:
            break
        except Exception as e:
            logger.warning(f"[PeeringEye] Cache refresh error: {e}")
            if not _platform_cache:
                _platform_cache = DEFAULT_PLATFORM_PATTERNS

        await asyncio.sleep(300)  # refresh every 5 minutes


async def _dns_processor(dns_queue: asyncio.Queue):
    """Consumer: reads DNS entries from queue and accumulates for Peering-Eye."""
    # Import broadcaster lazily agar tidak circular import saat startup
    try:
        from services.dns_feed_broadcaster import push_dns_event as _push_feed
    except ImportError:
        _push_feed = None

    while True:
        try:
            source_ip, hostname, message = await dns_queue.get()
            try:
                # ── DB Fallback: IP VPN MikroTik yang belum ada di cache ──────────
                # Setiap IP asing dicoba resolve ke device sekali per DB_MISS_COOLDOWN.
                # Ini mengatasi syslog yang dikirim dari IP tunnel VPN (bukan ip_address).
                if source_ip not in _device_cache:
                    _now_ts    = time.time()
                    _last_miss = _db_miss_ts.get(source_ip, 0)
                    if (_now_ts - _last_miss) > DB_MISS_COOLDOWN:
                        try:
                            _fb_db  = get_db()
                            _ip_esc = re.escape(source_ip)
                            _fb_doc = await _fb_db.devices.find_one(
                                {"$or": [
                                    {"ip_address": {"$regex": f"^{_ip_esc}(:\\d+)?$"}},
                                    {"bgp_peer_ip": source_ip},
                                    {"vpn_ip": source_ip},
                                ]},
                                {"id": 1, "name": 1, "_id": 0}
                            )
                            if _fb_doc:
                                _device_cache[source_ip] = {"id": _fb_doc["id"], "name": _fb_doc.get("name", source_ip)}
                                logger.info(f"[PeeringEye] DB fallback OK: {source_ip} → {_fb_doc['id']} ({_fb_doc.get('name','')})")
                            else:
                                _db_miss_ts[source_ip] = _now_ts
                                logger.debug(f"[PeeringEye] DB fallback miss: {source_ip} tidak ada di tabel devices")
                        except Exception as _fb_err:
                            logger.debug(f"[PeeringEye] DB fallback error {source_ip}: {_fb_err}")

                result = _parse_dns_entry(source_ip, hostname, message)
                if result:
                    key = (result["device_id"], result["platform"])
                    acc = _dns_acc[key]
                    acc["hits"]  += 1
                    acc["icon"]   = result["icon"]
                    acc["color"]  = result["color"]
                    # Simpan device_name untuk di-flush ke stats
                    if not acc["device_name"] and result["device_name"]:
                        acc["device_name"] = result["device_name"]
                    acc["domains"][result["domain"]] += 1
                    if result.get("client_ip"):
                        acc["clients"][result["client_ip"]] += 1

                    # ── Push ke live DNS feed WebSocket broadcaster ──────────────
                    if _push_feed is not None:
                        feed_event = {
                            "ts":          time.time(),
                            "device_id":   result["device_id"],
                            "device_name": result["device_name"],
                            "domain":      result["domain"],
                            "platform":    result["platform"],
                            "icon":        result["icon"],
                            "color":       result["color"],
                            "client_ip":   result.get("client_ip"),
                        }
                        asyncio.create_task(_push_feed(feed_event))

            except Exception as e:
                logger.debug(f"[PeeringEye] DNS parse error: {e}")
            finally:
                dns_queue.task_done()
        except asyncio.CancelledError:
            logger.info("[PeeringEye] DNS processor shutting down")
            break


async def _peering_eye_flusher():
    """Periodic flush: accumulate DNS stats → MongoDB peering_eye_stats."""
    logger.info(f"[PeeringEye] DNS flush loop started (interval={FLUSH_INTERVAL}s)")
    # Wait for initial cache load
    await asyncio.sleep(10)

    while True:
        await asyncio.sleep(FLUSH_INTERVAL)
        try:
            if not _dns_acc:
                continue

            # Snapshot and clear
            snapshot = {}
            keys = list(_dns_acc.keys())
            for k in keys:
                snapshot[k] = dict(_dns_acc.pop(k))

            now_iso = datetime.now(timezone.utc).isoformat()
            db      = get_db()

            from pymongo import UpdateOne
            ops = []
            for (device_id, platform), data in snapshot.items():
                top_domains = dict(sorted(data["domains"].items(), key=lambda x: x[1], reverse=True)[:20])
                top_clients = {ip: {"hits": cnt, "bytes": 0} for ip, cnt in sorted(data["clients"].items(), key=lambda x: x[1], reverse=True)[:20]}

                doc = {
                    "device_id":   device_id,
                    "platform":    platform,
                    "icon":        data["icon"],
                    "color":       data["color"],
                    "hits":        data["hits"],
                    "bytes":       data.get("bytes", 0),
                    "packets":     0,
                    "device_name": data.get("device_name", ""),
                    "top_domains": top_domains,
                    "top_clients": top_clients,
                    "timestamp":   now_iso,
                }
                ops.append(UpdateOne(
                    {"device_id": device_id, "platform": platform, "timestamp": now_iso},
                    {"$set": doc},
                    upsert=True,
                ))

            if ops:
                await db.peering_eye_stats.bulk_write(ops)
                total_hits = sum(v["hits"] for v in snapshot.values())
                logger.info(f"[PeeringEye] Flushed {len(ops)} platform records ({total_hits} DNS hits) to MongoDB")

                # ── Trigger auto-alert check ──────────────────────────────────
                try:
                    from services.peering_alert_service import check_alerts_from_snapshot
                    asyncio.create_task(check_alerts_from_snapshot(dict(snapshot)))
                except ImportError:
                    pass

        except asyncio.CancelledError:
            logger.info("[PeeringEye] Flusher shutting down")
            break
        except Exception as e:
            logger.error(f"[PeeringEye] Flush error: {e}")


async def _cleanup_old_logs():
    """Periodically delete syslog entries older than 30 days."""
    while True:
        try:
            cutoff = (datetime.now(timezone.utc) - timedelta(days=30)).isoformat()
            db = get_db()
            r = await db.syslog_entries.delete_many({"timestamp": {"$lt": cutoff}})
            if r.deleted_count > 0:
                logger.info(f"Cleaned {r.deleted_count} old syslog entries")
        except asyncio.CancelledError:
            break
        except Exception as e:
            logger.error(f"Syslog cleanup error: {e}")
        await asyncio.sleep(3600)


# ══════════════════════════════════════════════════════════════════════════════
# Entry Point
# ══════════════════════════════════════════════════════════════════════════════

async def start_syslog_server(loop: asyncio.AbstractEventLoop) -> list:
    """
    Start the UDP syslog server + Peering-Eye DNS processor + NOC-METRICS processor.
    Returns list of background task references.
    """
    # Queue size diperbesar 5x dari default untuk menangani lonjakan traffic syslog.
    # syslog_queue: buffer syslog raw sebelum ditulis ke MongoDB
    # dns_queue: buffer DNS query untuk Peering-Eye processor
    # metrics_queue: buffer NOC-METRICS (CPU/RAM push dari MikroTik scheduler)
    syslog_queue:   asyncio.Queue = asyncio.Queue(maxsize=50000)
    dns_queue:      asyncio.Queue = asyncio.Queue(maxsize=100000)
    metrics_queue:  asyncio.Queue = asyncio.Queue(maxsize=5000)

    try:
        transport, protocol = await loop.create_datagram_endpoint(
            lambda: SyslogProtocol(syslog_queue, dns_queue, metrics_queue),
            local_addr=("0.0.0.0", SYSLOG_PORT),
            family=2,  # AF_INET
        )
        logger.info(f"Syslog UDP server listening on port {SYSLOG_PORT}")
        logger.info(f"[PeeringEye] DNS processor integrated into syslog_server (port {SYSLOG_PORT})")
        logger.info(f"[NOC-METRICS] CPU/RAM interceptor aktif (port {SYSLOG_PORT})")
    except OSError as e:
        logger.error(f"Failed to start syslog server on port {SYSLOG_PORT}: {e}")
        logger.warning("Syslog server disabled — port already in use or permission denied.")
        return []

    tasks = [
        asyncio.create_task(_db_writer(syslog_queue),       name="syslog-db-writer"),
        asyncio.create_task(_cleanup_old_logs(),             name="syslog-cleanup"),
        asyncio.create_task(_refresh_caches(),               name="peering-eye-cache"),
        asyncio.create_task(_dns_processor(dns_queue),      name="peering-eye-dns-processor"),
        asyncio.create_task(_peering_eye_flusher(),          name="peering-eye-flusher"),
        asyncio.create_task(_metrics_processor(metrics_queue), name="noc-metrics-processor"),
    ]
    return tasks
