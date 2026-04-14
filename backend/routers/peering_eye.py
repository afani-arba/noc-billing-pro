"""
Sentinel Peering-Eye API Router
================================
Endpoints untuk membaca data dari collection:
  - peering_eye_stats      : DNS + NetFlow aggregate per platform per device
  - peering_eye_bgp_status : BGP peer status snapshot

Mount prefix: /api/peering-eye
"""

from fastapi import APIRouter, Depends, Query, HTTPException, Body
from datetime import datetime, timezone, timedelta
from collections import defaultdict
from pydantic import BaseModel
import subprocess
import asyncio
import uuid
import os
import re
from core.db import get_db
from core.auth import get_current_user, require_write, require_admin
from mikrotik_api import get_api_client

router = APIRouter(prefix="/peering-eye", tags=["Peering Eye"])

# ─── BGP Traffic Steering ──────────────────────────────────────────────────────

# Daftar platform populer + ikon default yang selalu tersedia sebagai pilihan
STEERING_PLATFORM_CATALOG = [
    {"name": "YouTube",        "icon": "▶️",  "asn": 15169,  "color": "#ff0000"},
    {"name": "Netflix",        "icon": "🎬",  "asn": 2906,   "color": "#e50914"},
    {"name": "TikTok",         "icon": "🎵",  "asn": 396986, "color": "#69c9d0"},
    {"name": "Facebook",       "icon": "👤",  "asn": 32934,  "color": "#1877f2"},
    {"name": "Instagram",      "icon": "📷",  "asn": 32934,  "color": "#e4405f"},
    {"name": "WhatsApp",       "icon": "💬",  "asn": 32934,  "color": "#25d366"},
    {"name": "Telegram",       "icon": "✈️",  "asn": 62041,  "color": "#2ca5e0"},
    {"name": "Google",         "icon": "🔍",  "asn": 15169,  "color": "#4285f4"},
    {"name": "Cloudflare",     "icon": "☁️",  "asn": 13335,  "color": "#f48120"},
    {"name": "Zoom",           "icon": "📹",  "asn": 3356,   "color": "#2d8cff"},
    {"name": "Shopee",         "icon": "🛍️",  "asn": 45102,  "color": "#ee4d2d"},
    {"name": "Tokopedia",      "icon": "🏪",  "asn": 10208,  "color": "#42b549"},
    {"name": "Steam",          "icon": "🎮",  "asn": 32590,  "color": "#1b2838"},
    {"name": "Mobile Legends", "icon": "⚔️",  "asn": 45102,  "color": "#d4a017"},
    {"name": "Indihome/Telkom","icon": "🇮🇩",  "asn": 7713,   "color": "#cc0000"},
    {"name": "Biznet",         "icon": "🌐",  "asn": 17451,  "color": "#0057a8"},
    {"name": "Akamai",         "icon": "🔗",  "asn": 20940,  "color": "#009bde"},
    {"name": "AWS",            "icon": "☁",   "asn": 16509,  "color": "#ff9900"},
    {"name": "Custom",         "icon": "🔧",  "asn": 0,      "color": "#6366f1"},
]


class BgpSteeringPolicy(BaseModel):
    platform_name: str                        # Nama platform (YouTube, Netflix, dsb.)
    gateway_ip: str                           # Next-hop / IP Gateway ISP tujuan
    target_peer: str = ""                     # Spesifikasi BGP Peer (IP) yg akan menerima rute ini (Opsional)
    isp_label: str = ""                       # Label ISP (contoh: "ISP Dedicated Video")
    enabled: bool = True
    icon: str = "🌐"
    color: str = "#6366f1"
    custom_prefixes: list[str] = []           # Prefix manual (opsional, contoh CIDR tambahan)
    description: str = ""


@router.get("/bgp-steering/catalog")
async def get_steering_catalog(user=Depends(get_current_user)):
    """Daftar platform populer yang bisa dipilih sebagai target steering."""
    return STEERING_PLATFORM_CATALOG


@router.get("/bgp-steering")
async def list_steering_policies(user=Depends(get_current_user)):
    """List semua kebijakan BGP Content Steering yang dibuat oleh admin."""
    db = get_db()
    policies = await db.bgp_steering_policies.find({}, {"_id": 0}).to_list(200)
    return policies


@router.post("/bgp-steering")
async def create_steering_policy(data: BgpSteeringPolicy, user=Depends(require_write)):
    """Buat kebijakan BGP Steering baru untuk sebuah platform."""
    db = get_db()
    # Cek duplikat nama platform
    existing = await db.bgp_steering_policies.find_one({"platform_name": data.platform_name})
    if existing:
        raise HTTPException(400, f"Kebijakan untuk platform '{data.platform_name}' sudah ada. Gunakan PUT untuk mengupdate.")
    doc = data.dict()
    doc["id"] = str(uuid.uuid4())
    doc["created_at"] = datetime.now(timezone.utc).isoformat()
    doc["updated_at"] = doc["created_at"]
    doc["injected_prefix_count"] = 0
    doc["last_inject_at"] = None
    await db.bgp_steering_policies.insert_one(doc)
    doc.pop("_id", None)
    # Log event
    await db.sdwan_events.insert_one({
        "type": "bgp_steering_created",
        "platform": data.platform_name,
        "gateway_ip": data.gateway_ip,
        "created_by": user.get("username", ""),
        "timestamp": doc["created_at"],
    })
    return doc


@router.put("/bgp-steering/{policy_id}")
async def update_steering_policy(policy_id: str, data: BgpSteeringPolicy, user=Depends(require_write)):
    """Update kebijakan BGP Steering (gateway, ISP label, prefixes, dsb.)."""
    db = get_db()
    update = data.dict()
    update["updated_at"] = datetime.now(timezone.utc).isoformat()
    res = await db.bgp_steering_policies.update_one({"id": policy_id}, {"$set": update})
    if res.matched_count == 0:
        raise HTTPException(404, "Policy tidak ditemukan")
    await db.sdwan_events.insert_one({
        "type": "bgp_steering_updated",
        "policy_id": policy_id,
        "platform": data.platform_name,
        "gateway_ip": data.gateway_ip,
        "updated_by": user.get("username", ""),
        "timestamp": update["updated_at"],
    })
    return {"message": "Updated"}


@router.delete("/bgp-steering/{policy_id}")
async def delete_steering_policy(policy_id: str, user=Depends(require_admin)):
    """Hapus kebijakan BGP Steering. Daemon akan otomatis mencabut prefix injeksi."""
    db = get_db()
    policy = await db.bgp_steering_policies.find_one({"id": policy_id}, {"_id": 0})
    if not policy:
        raise HTTPException(404, "Policy tidak ditemukan")
    await db.bgp_steering_policies.delete_one({"id": policy_id})
    # Hapus status injeksi
    await db.bgp_steering_status.delete_many({"policy_id": policy_id})
    await db.sdwan_events.insert_one({
        "type": "bgp_steering_deleted",
        "platform": policy.get("platform_name", ""),
        "deleted_by": user.get("username", ""),
        "timestamp": datetime.now(timezone.utc).isoformat(),
    })
    return {"message": "Deleted"}


@router.post("/bgp-steering/{policy_id}/toggle")
async def toggle_steering_policy(policy_id: str, user=Depends(require_write)):
    """Toggle ON/OFF kebijakan BGP Steering. Daemon akan merespons dalam 5 menit."""
    db = get_db()
    policy = await db.bgp_steering_policies.find_one({"id": policy_id}, {"_id": 0})
    if not policy:
        raise HTTPException(404, "Policy tidak ditemukan")
    new_state = not policy.get("enabled", True)
    await db.bgp_steering_policies.update_one(
        {"id": policy_id},
        {"$set": {"enabled": new_state, "updated_at": datetime.now(timezone.utc).isoformat()}}
    )
    action = "enabled" if new_state else "disabled"
    await db.sdwan_events.insert_one({
        "type": f"bgp_steering_{action}",
        "platform": policy.get("platform_name", ""),
        "toggled_by": user.get("username", ""),
        "timestamp": datetime.now(timezone.utc).isoformat(),
    })

    # Trigger inject langsung saat policy di-ON-kan (tanpa tunggu 30 menit)
    if new_state:
        try:
            from services.bgp_steering_injector import trigger_inject
            trigger_inject()
        except Exception:
            pass  # Injector mungkin belum aktif, tidak masalah

    return {"enabled": new_state, "message": f"BGP Steering untuk {policy.get('platform_name')} {'diaktifkan' if new_state else 'dinonaktifkan'}"}


@router.get("/bgp-steering/status")
async def get_steering_status(user=Depends(get_current_user)):
    """
    Ambil status real-time injeksi prefix:
    - Berapa prefix yang saat ini aktif di BGP per platform
    - Timestamp terakhir injeksi
    - Status daemon GoBGP
    """
    db = get_db()
    policies = await db.bgp_steering_policies.find({}, {"_id": 0}).to_list(200)

    result = []
    for p in policies:
        result.append({
            **p,
            "active_prefix_count": p.get("injected_prefix_count", 0),
            "last_inject_at": p.get("last_inject_at", None),
            "sample_ips": [], # Not used in frontend currently
        })

    total_active = sum(1 for p in policies if p.get("enabled"))
    total_prefixes = sum(p.get("injected_prefix_count", 0) for p in policies)

    return {
        "policies": result,
        "summary": {
            "total_policies": len(policies),
            "active_policies": total_active,
            "total_injected_prefixes": total_prefixes,
        }
    }



# ─── Endpoint: Sentinel Eye Service Status ────────────────────────────────────
@router.get("/service-status")
async def sentinel_eye_service_status(user=Depends(get_current_user)):
    """
    Cek apakah collector service (syslog_server) sedang berjalan di proses ini,
    dan apakah ada data yang baru diterima (dalam 5 menit terakhir).
    """
    db = get_db()

    # 1. Cek apakah syslog listener jalan
    syslog_running = False
    try:
        import syslog_server as _ss
        syslog_running = bool(getattr(_ss, "SYSLOG_PORT", None))
    except Exception:
        pass

    # 2. Cek data fresh dalam 5 menit terakhir
    cutoff = (datetime.now(timezone.utc) - timedelta(minutes=5)).isoformat()
    fresh_count = await db.peering_eye_stats.count_documents({"timestamp": {"$gte": cutoff}})
    
    # 3. Total semua data
    total_count = await db.peering_eye_stats.count_documents({})
    
    # 4. Waktu data terakhir diterima
    last_doc = await db.peering_eye_stats.find_one({}, {"_id": 0, "timestamp": 1}, sort=[("timestamp", -1)])
    last_seen = last_doc["timestamp"] if last_doc else None
    
    syslog_port  = int(os.environ.get("SYSLOG_PORT", "5514"))
    syslog_enabled  = os.environ.get("ENABLE_SYSLOG", "true").lower() == "true"

    return {
        "syslog_enabled":   syslog_enabled,
        "syslog_running":   syslog_running,
        "syslog_port":      syslog_port,
        "has_fresh_data":   fresh_count > 0,
        "total_records":    total_count,
        "last_seen":        last_seen,
        "collector_active": syslog_enabled,
    }

@router.post("/service-restart")
async def sentinel_eye_service_restart(user=Depends(get_current_user)):
    """
    Cek dan/atau restart syslog collector.
    Jika port sudah terbuka (sudah running) → kembalikan pesan 'already running'.
    """
    import asyncio
    import socket

    def _port_listening(port: int) -> bool:
        sock = None
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            sock.bind(("0.0.0.0", port))
            sock.close()
            return False
        except OSError:
            return True
        finally:
            if sock:
                try:
                    sock.close()
                except Exception:
                    pass

    syslog_port = int(os.environ.get("SYSLOG_PORT", "5514"))
    syslog_up = _port_listening(syslog_port)
    
    if syslog_up:
        status_msg = f"✅ Syslog port :{syslog_port} sudah aktif. Pastikan MikroTik mengirim log kesini."
        return {
            "ok": True,
            "already_running": True,
            "message": status_msg,
        }
    
    msgs = []
    try:
        from syslog_server import start_syslog_server
        loop = asyncio.get_running_loop()
        tasks = await start_syslog_server(loop)
        if tasks:
            msgs.append(f"✅ Syslog berhasil direstart (:{syslog_port})")
        else:
            msgs.append(f"⚠️ Syslog gagal start — port {syslog_port} mungkin dipakai aplikasi lain")
    except Exception as e:
        msgs.append(f"❌ Syslog error: {e}")
    
    return {
        "ok": True,
        "already_running": False,
        "message": " | ".join(msgs),
    }




# ─── Endpoint: Platforms Management ──────────────────────────────────────────
class PeeringPlatform(BaseModel):
    name: str
    regex_pattern: str
    icon: str = "🌐"
    color: str = "#64748b"
    alert_threshold_hits: int = 0
    alert_threshold_mb: int = 0

@router.get("/platforms")
async def get_platforms(user=Depends(get_current_user)):
    db = get_db()
    docs = await db.peering_platforms.find({}, {"_id": 0}).to_list(1000)
    if not docs:
        from syslog_server import DEFAULT_PLATFORM_PATTERNS
        seed = []
        for pat, name, icon, color in DEFAULT_PLATFORM_PATTERNS:
            seed.append({
                "id": str(uuid.uuid4()),
                "name": name,
                "regex_pattern": pat,
                "icon": icon,
                "color": color,
                "alert_threshold_hits": 0,
                "alert_threshold_mb": 0
            })
        await db.peering_platforms.insert_many(seed)
        docs = seed
        for d in docs:
            d.pop("_id", None)
            
    return docs

@router.post("/platforms")
async def create_platform(data: PeeringPlatform, user=Depends(require_write)):
    db = get_db()
    existing = await db.peering_platforms.find_one({"name": data.name})
    if existing:
        raise HTTPException(400, "Platform dengan nama tersebut sudah ada")
    
    doc = data.dict()
    doc["id"] = str(uuid.uuid4())
    await db.peering_platforms.insert_one(doc)
    doc.pop("_id", None)
    return doc

@router.put("/platforms/{plat_id}")
async def update_platform(plat_id: str, data: PeeringPlatform, user=Depends(require_write)):
    db = get_db()
    res = await db.peering_platforms.update_one({"id": plat_id}, {"$set": data.dict()})
    if res.matched_count == 0:
        raise HTTPException(404, "Platform tidak ditemukan")
    return {"message": "Updated"}

@router.delete("/platforms/{plat_id}")
async def delete_platform(plat_id: str, user=Depends(require_admin)):
    db = get_db()
    res = await db.peering_platforms.delete_one({"id": plat_id})
    if res.deleted_count == 0:
        raise HTTPException(404, "Platform tidak ditemukan")
    return {"message": "Deleted"}

async def get_platform_meta(db) -> dict:
    docs = await db.peering_platforms.find({}, {"_id": 0, "name": 1, "icon": 1, "color": 1}).to_list(1000)
    meta = {}
    for d in docs:
        meta[d["name"]] = {"icon": d.get("icon", "🌐"), "color": d.get("color", "#64748b")}
    return meta

# Platform metadata is now fetched dynamically from DB via get_platform_meta()

def fmt_bytes(b: int) -> str:
    if b >= 1e9:
        return f"{b/1e9:.2f} GB"
    if b >= 1e6:
        return f"{b/1e6:.2f} MB"
    if b >= 1e3:
        return f"{b/1e3:.1f} KB"
    return f"{b} B"


def range_to_start(range_str: str) -> str:
    """Convert range string (1h/6h/12h/24h/7d/30d) to ISO start timestamp."""
    hours_map = {"1h": 1, "6h": 6, "12h": 12, "24h": 24, "7d": 168, "30d": 720}
    hours = hours_map.get(range_str, 24)
    start = datetime.now(timezone.utc) - timedelta(hours=hours)
    return start.isoformat()


async def _resolve_device_ids(db, device_id: str) -> list:
    """
    Resolve device identifier ke semua kemungkinan device_id yang tersimpan di peering_eye_stats.
    Data di stats bisa disimpan sebagai UUID, IP address, atau nama device
    (tergantung kondisi cache saat syslog diterima).
    Fungsi ini mencari device dari berbagai field agar filter selalu cocok.
    """
    if not device_id or device_id == "all":
        return []

    # Cari device berdasarkan UUID, IP address, ATAU name
    dev = await db.devices.find_one(
        {"$or": [
            {"id": device_id},
            {"ip_address": {"$regex": f"^{re.escape(device_id.split(':')[0])}(:\\d+)?$"}},
            {"name": device_id},
            {"bgp_peer_ip": device_id},
        ]},
        {"id": 1, "ip_address": 1, "name": 1, "bgp_peer_ip": 1}
    )

    if dev:
        res = set()
        if dev.get("id"):        res.add(dev["id"])
        if dev.get("name"):      res.add(dev["name"])
        # IP address (tanpa port)
        ip = (dev.get("ip_address") or "").split(":")[0].strip()
        if ip: res.add(ip)
        # BGP/Tunnel IP
        bgp_ip = (dev.get("bgp_peer_ip") or "").strip()
        if bgp_ip: res.add(bgp_ip)
        # Tambahkan device_id asli yang dikirim juga (fallback jika tidak ditemukan di devices)
        res.add(device_id)
        return list(res)

    # Device tidak ditemukan di DB — kembalikan apa adanya agar query tidak kosong
    return [device_id]


# ─── Endpoint: List Device IDs yang ada datanya ──────────────────────────────
@router.get("/devices")
async def peering_eye_devices(user=Depends(get_current_user)):
    """Return list of ALL devices, optionally merged with peering-eye stats."""
    db = get_db()
    
    # 1. Ambil semua device — ekspos field 'id' (UUID string), bukan _id
    all_devs = await db.devices.find({}, {"_id": 0, "id": 1, "name": 1, "ip_address": 1}).to_list(200)
    
    # 2. Ambil statistik total hit jika ada
    pipeline = [
        {"$group": {
            "_id": "$device_id",
            "last_seen": {"$max": "$timestamp"},
            "total_hits": {"$sum": "$hits"},
        }}
    ]
    stats_docs = await db.peering_eye_stats.aggregate(pipeline).to_list(200)
    stats_map = {d["_id"]: {"last_seen": d.get("last_seen"), "hits": d.get("total_hits", 0)} for d in stats_docs}
    
    result = []
    for d in all_devs:
        dev_id = d.get("id") or str(d.get("_id", ""))  # gunakan UUID 'id'
        if not dev_id:
            continue
        
        # Combine hits for IP/Name/UUID automatically
        ip = (d.get("ip_address") or "").split(":")[0].strip()
        hits = 0
        last_seen = None
        for k in (dev_id, d.get("name"), ip):
            if k and k in stats_map:
                hits += stats_map[k]["hits"]
                if stats_map[k]["last_seen"]:
                    if not last_seen or stats_map[k]["last_seen"] > last_seen:
                        last_seen = stats_map[k]["last_seen"]
        
        result.append({
            "device_id":   dev_id,
            "device_name": d.get("name", dev_id),
            "last_seen":   last_seen or "",
            "total_hits":  hits,
        })
    return sorted(result, key=lambda x: x["device_name"].lower())



# ─── Endpoint: Stats — aggregate per platform ─────────────────────────────────
@router.get("/stats")
async def peering_eye_stats(
    device_id: str = "",
    range: str = "24h",
    user=Depends(get_current_user),
):
    """Aggregate platform statistics (hits + bytes) for a device or all devices."""
    db = get_db()
    start = range_to_start(range)

    # Build list of known device IPs + names to EXCLUDE unknown sources
    all_devs = await db.devices.find({}, {"_id": 0, "id": 1, "name": 1, "ip_address": 1}).to_list(200)
    known_ids = set()
    for d in all_devs:
        if d.get("id"): known_ids.add(d["id"])
        if d.get("name"): known_ids.add(d["name"])
        ip = (d.get("ip_address") or "").split(":")[0].strip()
        if ip: known_ids.add(ip)

    match: dict = {"timestamp": {"$gte": start}}
    if device_id and device_id != "all":
        ids = await _resolve_device_ids(db, device_id)
        match["device_id"] = {"$in": ids}
    elif known_ids:
        # Filter hanya device yang terdaftar — buang IP liar (VPS, gateway, dll)
        match["device_id"] = {"$in": list(known_ids)}

    pipeline = [
        {"$match": match},
        {"$group": {
            "_id": "$platform",
            "icon":  {"$last": "$icon"},
            "color": {"$last": "$color"},
            "hits":  {"$sum": "$hits"},
            "bytes": {"$sum": "$bytes"},
            "device_name": {"$last": "$device_name"},
        }},
        {"$sort": {"hits": -1}},
    ]

    docs = await db.peering_eye_stats.aggregate(pipeline).to_list(100)

    total_hits  = sum(d.get("hits", 0) for d in docs)
    total_bytes = sum(d.get("bytes", 0) for d in docs)

    platforms = []
    meta_map = await get_platform_meta(db)
    for d in docs:
        p = d["_id"]
        meta = meta_map.get(p, {"icon": "🌐", "color": "#64748b"})
        hits  = d.get("hits", 0)
        bytes_val = d.get("bytes", 0)
        platforms.append({
            "platform":    p,
            "icon":        d.get("icon") or meta["icon"],
            "color":       d.get("color") or meta["color"],
            "hits":        hits,
            "bytes":       bytes_val,
            "bytes_fmt":   fmt_bytes(bytes_val),
            "pct_hits":    round(hits / total_hits * 100, 1) if total_hits else 0,
            "pct_bytes":   round(bytes_val / total_bytes * 100, 1) if total_bytes else 0,
        })

    return {
        "device_id":   device_id or "all",
        "range":       range,
        "total_hits":  total_hits,
        "total_bytes": total_bytes,
        "total_bytes_fmt": fmt_bytes(total_bytes),
        "platform_count": len(platforms),
        "platforms":   platforms,
    }


# ─── Endpoint: Platform Domains Detail (untuk klik-detail di frontend) ────────
@router.get("/platform-domains")
async def peering_eye_platform_domains(
    platform: str = Query(..., description="Nama platform, misal: TikTok, Google"),
    device_id: str = Query("", description="Filter device tertentu (opsional)"),
    range: str = Query("24h", description="Rentang waktu: 1h/6h/12h/24h/7d/30d"),
    limit: int = Query(30, description="Jumlah domain maksimal yang dikembalikan"),
    user=Depends(get_current_user),
):
    """
    Mengembalikan daftar domain teratas untuk satu platform tertentu.
    Digunakan untuk fitur klik-untuk-detail di tabel Platform Traffic.
    """
    db = get_db()
    start = range_to_start(range)

    match: dict = {"timestamp": {"$gte": start}, "platform": platform}
    if device_id and device_id != "all":
        ids = await _resolve_device_ids(db, device_id)
        match["device_id"] = {"$in": ids}

    docs = await db.peering_eye_stats.find(
        match, {"_id": 0, "top_domains": 1, "top_clients": 1, "hits": 1, "bytes": 1, "device_id": 1, "device_name": 1}
    ).to_list(5000)

    # Aggregate domains
    domain_agg: dict = defaultdict(int)
    client_agg: dict = defaultdict(int)
    total_hits = 0
    total_bytes = 0

    for doc in docs:
        total_hits += doc.get("hits", 0)
        total_bytes += doc.get("bytes", 0)
        for domain, hits in (doc.get("top_domains") or {}).items():
            domain_agg[domain] += hits
        for ip, stats in (doc.get("top_clients") or {}).items():
            h = stats.get("hits", 0) if isinstance(stats, dict) else stats
            client_agg[ip] += h

    sorted_domains = sorted(domain_agg.items(), key=lambda x: x[1], reverse=True)[:limit]
    sorted_clients = sorted(client_agg.items(), key=lambda x: x[1], reverse=True)[:10]

    return {
        "platform": platform,
        "device_id": device_id or "all",
        "range": range,
        "total_hits": total_hits,
        "total_bytes": total_bytes,
        "total_bytes_fmt": fmt_bytes(total_bytes),
        "domains": [
            {"domain": d, "hits": h, "pct": round(h / total_hits * 100, 1) if total_hits else 0}
            for d, h in sorted_domains
        ],
        "top_clients": [
            {"ip": ip, "hits": h}
            for ip, h in sorted_clients
        ],
    }


# ─── Endpoint: Timeline — time-series per platform ────────────────────────────
@router.get("/timeline")
async def peering_eye_timeline(
    device_id: str = "",
    platform:  str = "",
    range:     str = "12h",
    user=Depends(get_current_user),
):
    """Time-series data for charting (bucket per hour or 10 min)."""
    db = get_db()
    start = range_to_start(range)

    match: dict = {"timestamp": {"$gte": start}}
    if device_id and device_id != "all":
        ids = await _resolve_device_ids(db, device_id)
        match["device_id"] = {"$in": ids}
    if platform and platform != "all":
        match["platform"] = platform

    # Bucket size: 1h for long ranges, 10min for short ranges
    bucket_ms = 600_000 if range in ("1h", "6h", "12h") else 3_600_000

    pipeline = [
        {"$match": match},
        {"$addFields": {
            "ts_ms": {"$toLong": {"$dateFromString": {"dateString": "$timestamp"}}},
        }},
        {"$group": {
            "_id": {
                "bucket":   {"$subtract": ["$ts_ms", {"$mod": ["$ts_ms", bucket_ms]}]},
                "platform": "$platform",
            },
            "hits":  {"$sum": "$hits"},
            "bytes": {"$sum": "$bytes"},
            "icon":  {"$last": "$icon"},
            "color": {"$last": "$color"},
        }},
        {"$sort": {"_id.bucket": 1}},
    ]

    docs = await db.peering_eye_stats.aggregate(pipeline).to_list(5000)

    # Reshape: { time: [{ platform, hits, bytes }] }
    time_map: dict = {}
    meta_map = await get_platform_meta(db)
    for d in docs:
        bucket_ms_val = d["_id"]["bucket"]
        if not isinstance(bucket_ms_val, (int, float)):
            continue
        utc = datetime.fromtimestamp(bucket_ms_val / 1000, tz=timezone.utc)
        local = utc + timedelta(hours=7)  # WIB
        label = local.strftime("%H:%M" if range in ("1h","6h","12h") else "%d/%m %H:%M")

        p = d["_id"]["platform"]
        meta = meta_map.get(p, {"icon": "🌐", "color": "#64748b"})

        if label not in time_map:
            time_map[label] = {"time": label}
        time_map[label][p] = {
            "hits": d.get("hits", 0),
            "bytes": d.get("bytes", 0),
            "icon": d.get("icon") or meta["icon"],
            "color": d.get("color") or meta["color"],
        }

    return {
        "device_id": device_id or "all",
        "range":     range,
        "platform":  platform or "all",
        "data":      list(time_map.values()),
    }


# ─── Endpoint: Top Domains ────────────────────────────────────────────────────
@router.get("/top-domains")
async def peering_eye_top_domains(
    device_id: str = "",
    platform:  str = "",
    range:     str = "24h",
    limit:     int = 20,
    user=Depends(get_current_user),
):
    """Return top raw domains ordered by hit count."""
    db = get_db()
    start = range_to_start(range)

    match: dict = {"timestamp": {"$gte": start}}
    if device_id and device_id != "all":
        ids = await _resolve_device_ids(db, device_id)
        match["device_id"] = {"$in": ids}
    if platform and platform != "all":
        match["platform"] = platform

    docs = await db.peering_eye_stats.find(
        match, {"_id": 0, "top_domains": 1, "platform": 1, "icon": 1, "color": 1}
    ).to_list(5000)

    domain_agg: dict = defaultdict(lambda: {"hits": 0, "platform": "", "icon": "🌐", "color": "#64748b"})
    for doc in docs:
        td = doc.get("top_domains") or {}
        for domain, hits in td.items():
            domain_agg[domain]["hits"] += hits
            if not domain_agg[domain]["platform"]:
                domain_agg[domain]["platform"] = doc.get("platform", "Others")
                domain_agg[domain]["icon"]     = doc.get("icon", "🌐")
                domain_agg[domain]["color"]    = doc.get("color", "#64748b")

    sorted_domains = sorted(domain_agg.items(), key=lambda x: x[1]["hits"], reverse=True)[:limit]

    return {
        "device_id": device_id or "all",
        "range":     range,
        "domains": [
            {
                "domain":   domain,
                "hits":     info["hits"],
                "platform": info["platform"],
                "icon":     info["icon"],
                "color":    info["color"],
            }
            for domain, info in sorted_domains
        ]
    }

@router.get("/debug-clients")
async def debug_clients(limit: int = 5):
    db = get_db()
    docs = await db.peering_eye_stats.find(
        {"top_clients": {"$exists": True, "$ne": {}}},
        {"_id": 0, "device_id": 1, "platform": 1, "timestamp": 1, "top_clients": 1}
    ).to_list(limit)
    return {"data": docs}



# ─── Endpoint: Top Clients ────────────────────────────────────────────────────

async def get_active_ip_mapping(db, device_id: str) -> dict:
    """Map IP ke nama user PPPoE/Hotspot jika tersedia. Fallback kosong jika belum ada."""
    return {}

@router.get("/top-clients")
async def peering_eye_top_clients(
    device_id: str = "",
    platform:  str = "",
    range:     str = "24h",
    limit:     int = 20,
    user=Depends(get_current_user),
):
    """Return top client IPs ordered by hit count."""
    db = get_db()
    start = range_to_start(range)

    match: dict = {"timestamp": {"$gte": start}}
    if device_id and device_id != "all":
        ids = await _resolve_device_ids(db, device_id)
        match["device_id"] = {"$in": ids}
    if platform and platform != "all":
        match["platform"] = platform

    docs = await db.peering_eye_stats.find(
        match, {"_id": 0, "top_clients": 1, "platform": 1, "icon": 1, "color": 1}
    ).to_list(5000)

    client_agg: dict = defaultdict(lambda: {"hits": 0, "bytes": 0, "platform": "", "icon": "🌐", "color": "#64748b"})
    for doc in docs:
        tc = doc.get("top_clients") or {}
        for ip, stats in tc.items():
            if isinstance(stats, dict):
                h = stats.get("hits", 0)
                b = stats.get("bytes", 0)
            else:
                h = stats
                b = 0
                
            client_agg[ip]["hits"] += h
            client_agg[ip]["bytes"] += b
            if not client_agg[ip]["platform"]:
                client_agg[ip]["platform"] = doc.get("platform", "Others")
                client_agg[ip]["icon"]     = doc.get("icon", "🌐")
                client_agg[ip]["color"]    = doc.get("color", "#64748b")

    # Sort by Bytes if available, otherwise Hits
    sorted_clients = sorted(client_agg.items(), key=lambda x: (x[1]["bytes"], x[1]["hits"]), reverse=True)[:limit]

    # Fetch mapping
    ip_mapping = await get_active_ip_mapping(db, device_id)

    return {
        "device_id": device_id or "all",
        "range":     range,
        "clients": [
            {
                "ip":       ip,
                "name":     ip_mapping.get(ip, {}).get("name", "Unknown"),
                "mac":      ip_mapping.get(ip, {}).get("mac", ""),
                "hits":     info["hits"],
                "bytes":    info["bytes"],
                "platform": info["platform"],
                "icon":     info["icon"],
                "color":    info["color"],
            }
            for ip, info in sorted_clients
        ]
    }


# ─── Endpoint: Client Activity (akses apa saja per IP) ───────────────────────
@router.get("/client-activity")
async def client_activity(
    ip:        str = Query(..., description="IP address pelanggan"),
    device_id: str = Query("", description="Filter device tertentu (opsional)"),
    range:     str = Query("6h", description="Rentang waktu: 1h/6h/12h/24h/7d"),
    user=Depends(get_current_user),
):
    """
    Detail aktivitas satu IP pelanggan:
    - Breakdown platform (hits, bytes, pct)
    - Top 20 domain yang dikunjungi
    - Nama user PPPoE/Hotspot jika terdeteksi
    - Timeline aktivitas (per 10 menit untuk range pendek)
    - Total traffic dalam range
    """
    db = get_db()
    start = range_to_start(range)

    # ── Query: cari semua dokumen di mana IP ini ada di top_clients ──────────
    # Gunakan $expr dan $objectToArray agar MongoDB bisa melakukan pencarian pada field
    # yang memiliki karakter titik (dot notation issue) pada key dictionarinya.
    match: dict = {
        "timestamp": {"$gte": start},
        "$expr": {
            "$in": [
                ip,
                {
                    "$map": {
                        "input": {"$objectToArray": {"$ifNull": ["$top_clients", {}]}},
                        "as": "item",
                        "in": "$$item.k"
                    }
                }
            ]
        }
    }
    if device_id and device_id != "all":
        ids = await _resolve_device_ids(db, device_id)
        match["device_id"] = {"$in": ids}

    raw_docs = await db.peering_eye_stats.find(
        match,
        {
            "_id": 0,
            "timestamp": 1,
            "platform": 1,
            "icon": 1,
            "color": 1,
            "device_id": 1,
            "top_clients": 1,
            "top_domains": 1,   # domain hanya bisa dikaitkan via platform
        }
    ).to_list(10000)

    # Filter di Python aman jika untuk key dict
    docs = [doc for doc in raw_docs if ip in doc.get("top_clients", {})]

    if not docs:
        # Coba cek apakah IP ini memang ada di DB historis untuk info fallback
        fallback_match = {
            "$expr": {
                "$in": [
                    ip,
                    {
                        "$map": {
                            "input": {"$objectToArray": {"$ifNull": ["$top_clients", {}]}},
                            "as": "item",
                            "in": "$$item.k"
                        }
                    }
                ]
            }
        }
        any_doc = await db.peering_eye_stats.find_one(
            fallback_match,
            {"_id": 0, "timestamp": 1}
        )
        return {
            "ip": ip,
            "found": False,
            "message": "Tidak ada aktivitas untuk IP ini dalam rentang waktu yang dipilih.",
            "has_historical": any_doc is not None,
            "platform_breakdown": [],
            "top_domains": [],
            "timeline": [],
            "total_hits": 0,
            "total_bytes": 0,
            "total_bytes_fmt": "0 B",
            "user_info": {},
        }

    # ── Cari nama PPPoE / Hotspot dari DB sesi aktif ─────────────────────────
    user_info = {}
    # Cek pppoe_sessions
    pppoe_sess = await db.pppoe_sessions.find_one(
        {"ip_address": ip},
        {"_id": 0, "username": 1, "service": 1, "uptime": 1, "mac_address": 1}
    )
    if pppoe_sess:
        user_info = {
            "name":    pppoe_sess.get("username", ""),
            "type":    "PPPoE",
            "uptime":  pppoe_sess.get("uptime", ""),
            "mac":     pppoe_sess.get("mac_address", ""),
            "service": pppoe_sess.get("service", ""),
        }
    else:
        # Cek hotspot_sessions
        hotspot_sess = await db.hotspot_sessions.find_one(
            {"ip_address": ip},
            {"_id": 0, "username": 1, "uptime": 1, "mac_address": 1}
        )
        if hotspot_sess:
            user_info = {
                "name":    hotspot_sess.get("username", ""),
                "type":    "Hotspot",
                "uptime":  hotspot_sess.get("uptime", ""),
                "mac":     hotspot_sess.get("mac_address", ""),
                "service": "",
            }
        else:
            # Cek peering_clients (custom client list jika ada)
            client_doc = await db.peering_clients.find_one(
                {"ip": ip},
                {"_id": 0, "name": 1, "label": 1}
            )
            if client_doc:
                user_info = {
                    "name":    client_doc.get("name", client_doc.get("label", "")),
                    "type":    "Static",
                    "uptime":  "",
                    "mac":     "",
                    "service": "",
                }

    # ── Agregasi breakdown per platform ──────────────────────────────────────
    plat_agg: dict = defaultdict(lambda: {"hits": 0, "bytes": 0, "icon": "🌐", "color": "#64748b"})

    # Untuk timeline: bucket per 10 menit
    # format: { "HH:MM": { platform: {hits, bytes} } }
    timeline_agg: dict = {}

    for doc in docs:
        platform = doc.get("platform", "Others")
        icon     = doc.get("icon", "🌐")
        color    = doc.get("color", "#64748b")
        client_d = doc.get("top_clients", {}).get(ip, {})

        if isinstance(client_d, dict):
            hits  = client_d.get("hits", 0)
            bytes_ = client_d.get("bytes", 0)
        else:
            hits  = int(client_d) if client_d else 0
            bytes_ = 0

        plat_agg[platform]["hits"]  += hits
        plat_agg[platform]["bytes"] += bytes_
        if not plat_agg[platform]["icon"] or plat_agg[platform]["icon"] == "🌐":
            plat_agg[platform]["icon"]  = icon
            plat_agg[platform]["color"] = color

        # Timeline bucket
        ts_str = doc.get("timestamp", "")
        try:
            ts_dt = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
            # Snap ke 10-menit bucket
            bucket_min = (ts_dt.minute // 10) * 10
            wib_dt = ts_dt + timedelta(hours=7)
            label = wib_dt.strftime(f"%H:{bucket_min:02d}")
            if range in ("7d", "30d"):
                label = wib_dt.strftime("%d/%m %H:%M")

            if label not in timeline_agg:
                timeline_agg[label] = {}
            if platform not in timeline_agg[label]:
                timeline_agg[label][platform] = {"hits": 0, "bytes": 0, "color": color}
            timeline_agg[label][platform]["hits"]  += hits
            timeline_agg[label][platform]["bytes"] += bytes_
        except Exception:
            pass

    # ── Hitung total ──────────────────────────────────────────────────────────
    total_hits  = sum(v["hits"]  for v in plat_agg.values())
    total_bytes = sum(v["bytes"] for v in plat_agg.values())

    # ── Susun breakdown per platform (sorted by hits desc) ───────────────────
    meta_map = await get_platform_meta(db)
    platform_breakdown = []
    for plat, info in sorted(plat_agg.items(), key=lambda x: x[1]["hits"], reverse=True):
        meta = meta_map.get(plat, {})
        platform_breakdown.append({
            "platform":  plat,
            "icon":      info["icon"] or meta.get("icon", "🌐"),
            "color":     info["color"] or meta.get("color", "#64748b"),
            "hits":      info["hits"],
            "bytes":     info["bytes"],
            "bytes_fmt": fmt_bytes(info["bytes"]),
            "pct_hits":  round(info["hits"]  / total_hits  * 100, 1) if total_hits  else 0,
            "pct_bytes": round(info["bytes"] / total_bytes * 100, 1) if total_bytes else 0,
        })

    # ── Cari top domains yang diakses oleh IP ini ─────────────────────────────
    # Strategi: ambil top_domains dari platform yang paling banyak diakses
    # IP ini, proportionally. Ini adalah approximation karena top_domains
    # tidak menyimpan per-client breakdown, hanya per-platform.
    domain_agg: dict = defaultdict(lambda: {"hits": 0, "platform": "", "icon": "🌐", "color": "#64748b"})

    # Hitung ratio hits IP ini vs total hits per platform/doc
    for doc in docs:
        platform = doc.get("platform", "Others")
        client_d = doc.get("top_clients", {}).get(ip, {})
        top_domains_raw = doc.get("top_domains") or {}

        if not top_domains_raw:
            continue

        # Hits IP ini di doc ini
        if isinstance(client_d, dict):
            ip_hits = client_d.get("hits", 0)
        else:
            ip_hits = int(client_d) if client_d else 0

        # Total hits semua client di doc ini (estimasi dari total hits doc)
        doc_total_hits = doc.get("hits", 0)
        if doc_total_hits == 0:
            # Hitung manual dari top_clients
            tc = doc.get("top_clients", {})
            for v in tc.values():
                doc_total_hits += (v.get("hits", 0) if isinstance(v, dict) else int(v or 0))

        # Ratio: berapa proporsi IP ini dari total hits di doc ini
        ratio = ip_hits / doc_total_hits if doc_total_hits > 0 else 0

        # Apply ratio ke top_domains untuk estimasi kontribusi IP ini
        for domain, d_hits in top_domains_raw.items():
            est_hits = max(1, round(d_hits * ratio)) if ratio > 0 else 0
            if est_hits > 0:
                domain_agg[domain]["hits"] += est_hits
                if not domain_agg[domain]["platform"]:
                    domain_agg[domain]["platform"] = platform
                    domain_agg[domain]["icon"]     = doc.get("icon", "🌐")
                    domain_agg[domain]["color"]    = doc.get("color", "#64748b")

    top_domains = []
    for domain, info in sorted(domain_agg.items(), key=lambda x: x[1]["hits"], reverse=True)[:20]:
        top_domains.append({
            "domain":   domain,
            "hits":     info["hits"],
            "platform": info["platform"],
            "icon":     info["icon"],
            "color":    info["color"],
        })

    # ── Susun timeline (sorted by time) ──────────────────────────────────────
    timeline = []
    for label in sorted(timeline_agg.keys()):
        entry = {"time": label}
        for plat, pdata in timeline_agg[label].items():
            entry[plat] = pdata
        timeline.append(entry)

    return {
        "ip":           ip,
        "found":        True,
        "range":        range,
        "device_id":    device_id or "all",
        "user_info":    user_info,
        "total_hits":   total_hits,
        "total_bytes":  total_bytes,
        "total_bytes_fmt": fmt_bytes(total_bytes),
        "platform_breakdown": platform_breakdown,
        "top_domains":  top_domains,
        "timeline":     timeline,
        "data_points":  len(docs),
    }


# ─── Endpoint: BGP Status ────────────────────────────────────────────────────
@router.get("/bgp/status")
async def bgp_status(user=Depends(get_current_user)):
    """Return current BGP peer status from MongoDB snapshot."""
    db = get_db()
    docs = await db.peering_eye_bgp_status.find(
        {}, {"_id": 0}
    ).to_list(200)

    # Augment with human-readable uptime
    for d in docs:
        uptime_s = d.get("uptime_sec", 0)
        if uptime_s:
            days  = uptime_s // 86400
            hrs   = (uptime_s % 86400) // 3600
            mins  = (uptime_s % 3600) // 60
            d["uptime_fmt"] = f"{days}d {hrs}h {mins}m" if days else f"{hrs}h {mins}m"
        else:
            d["uptime_fmt"] = "—"

    established = sum(1 for d in docs if d.get("state") == "ESTABLISHED")
    return {
        "peers":       docs,
        "total":       len(docs),
        "established": established,
        "updated_at":  docs[0].get("updated_at") if docs else None,
    }


# ─── Endpoint: BGP Manual Sync trigger ───────────────────────────────────────
@router.post("/bgp/sync")
async def bgp_sync(user=Depends(get_current_user)):
    """Trigger immediate BGP peer sync (writes a flag to DB for sentinel_bgp.py)."""
    db = get_db()
    await db.peering_eye_control.update_one(
        {"_id": "bgp_sync"},
        {"$set": {"trigger": True, "requested_at": datetime.now(timezone.utc).isoformat()}},
        upsert=True,
    )
    return {"status": "ok", "message": "BGP sync requested — sentinel_bgp.py will process within 30 seconds"}


# ─── Endpoint: Ingest — receive data from sentinel_eye.py ────────────────────
@router.post("/ingest")
async def peering_eye_ingest(payload: dict, user=Depends(get_current_user)):
    """
    Receive pre-aggregated data from sentinel_eye.py running on the Ubuntu VPS.
    This allows the collector to push data in batch.
    """
    db = get_db()
    required = ["device_id", "platform"]
    for f in required:
        if f not in payload:
            raise HTTPException(400, f"Missing field: {f}")

    now = datetime.now(timezone.utc).isoformat()
    platform = payload["platform"]
    meta_map = await get_platform_meta(db)
    meta = meta_map.get(platform, {"icon": "🌐", "color": "#64748b"})

    doc = {
        "device_id":   payload["device_id"],
        "device_name": payload.get("device_name", payload["device_id"]),
        "platform":    platform,
        "icon":        payload.get("icon", meta["icon"]),
        "color":       payload.get("color", meta["color"]),
        "hits":        int(payload.get("hits", 0)),
        "bytes":       int(payload.get("bytes", 0)),
        "packets":     int(payload.get("packets", 0)),
        "top_domains": payload.get("top_domains", {}),
        "top_clients": payload.get("top_clients", {}),
        "timestamp":   payload.get("timestamp", now),
    }

    await db.peering_eye_stats.insert_one(doc)
    return {"status": "ok", "inserted": 1}


# ─── Endpoint: Summary for header cards ──────────────────────────────────────
@router.get("/summary")
async def peering_eye_summary(
    device_id: str = "",
    range:     str = "24h",
    user=Depends(get_current_user),
):
    """Quick summary: total hits, top platform, unique domains, bytes."""
    db = get_db()
    start = range_to_start(range)

    match: dict = {"timestamp": {"$gte": start}}
    if device_id and device_id != "all":
        ids = await _resolve_device_ids(db, device_id)
        match["device_id"] = {"$in": ids}

    pipeline = [
        {"$match": match},
        {"$group": {
            "_id":         "$platform",
            "hits":        {"$sum": "$hits"},
            "bytes":       {"$sum": "$bytes"},
            "domain_count": {"$sum": {"$size": {"$objectToArray": {"$ifNull": ["$top_domains", {}]}}}},
        }},
        {"$sort": {"hits": -1}},
    ]

    docs = await db.peering_eye_stats.aggregate(pipeline).to_list(100)
    if not docs:
        return {
            "total_hits": 0, "total_bytes": 0, "total_bytes_fmt": "0 B",
            "top_platform": "—", "top_platform_icon": "🌐",
            "unique_platforms": 0, "unique_domains": 0,
        }

    total_hits   = sum(d["hits"] for d in docs)
    total_bytes  = sum(d["bytes"] for d in docs)
    total_domains = sum(d["domain_count"] for d in docs)
    top = docs[0]
    meta_map = await get_platform_meta(db)
    top_meta = meta_map.get(top["_id"], {"icon": "🌐"})

    return {
        "total_hits":       total_hits,
        "total_bytes":      total_bytes,
        "total_bytes_fmt":  fmt_bytes(total_bytes),
        "top_platform":     top["_id"],
        "top_platform_icon": top_meta["icon"],
        "top_platform_hits": top["hits"],
        "unique_platforms": len(docs),
        "unique_domains":   total_domains,
    }


# ─── Endpoint: 1-Click Block ─────────────────────────────────────────────────
@router.post("/block")
async def peering_eye_block(
    device_id: str = Body(..., embed=True),
    target_type: str = Body(..., embed=True), # 'domain' atau 'client'
    target: str = Body(..., embed=True), # namadomain.com atau nama_pelanggan/ip
    user=Depends(get_current_user),
):
    """Blokir domain atau klien via MikroTik API."""
    db = get_db()
    
    if not device_id or device_id == "all":
        raise HTTPException(status_code=400, detail="Pilih device spesifik untuk melakukan blokir.")
        
    dev = await db.devices.find_one({"id": device_id}, {"_id": 0})
    if not dev:
        raise HTTPException(status_code=404, detail="Device tidak ditemukan")
        
    api = get_api_client(dev)
    await api.test_connection()
    
    try:
        if target_type == "domain":
            # Add to Address List 'peering_eye_block'
            await api.add_firewall_address_list(
                list_name="peering_eye_block",
                address=target,
                comment="Auto-blocked by Sentinel Peering-Eye"
            )
            val = f"Domain {target} berhasil diblokir"

        elif target_type == "client":
            # Target is the client name (from PPPoE/Hotspot)
            # Find and disable in PPPoE
            try:
                await api.disable_pppoe_user(target)
                val = f"PPPoE User '{target}' diisolir"
            except Exception as e:
                # If not PPPoE, check Hotspot
                try:
                    await api.disable_hotspot_user(target)
                    val = f"Hotspot User '{target}' diisolir"
                except Exception as e2:
                    # If not found mapped, block by target (IP)
                    await api.add_firewall_address_list(
                        list_name="peering_eye_block",
                        address=target,
                        comment="Client IP Auto-blocked by Sentinel Peering-Eye"
                    )
                    val = f"Client IP {target} berhasil diblokir via Address List"
        else:
            raise HTTPException(status_code=400, detail="Invalid target_type. Use 'domain' or 'client'")
            
        return {"success": True, "message": val}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))



@router.get("/bgp/service/status")
async def bgp_service_status(user=Depends(get_current_user)):
    """Check GoBGP daemon status — daemon berjalan di HOST via systemd, backend connect via nsenter."""
    import json as _json

    bgp_info = {}
    is_running = False
    
    # Check 1: Systemctl is-active via nsenter
    try:
        ps_host = subprocess.run(
            ["nsenter", "-t", "1", "-m", "-u", "-i", "-n", "-p", "--", "systemctl", "is-active", "gobgpd"],
            capture_output=True, text=True, timeout=5
        )
        if ps_host.stdout.strip() == "active":
            is_running = True
    except Exception:
        pass
        
    # Check 2: gobgp global config info via nsenter
    if is_running:
        try:
            gi = subprocess.run(
                ["nsenter", "-t", "1", "-m", "-u", "-i", "-n", "-p", "--", "/usr/local/bin/gobgp", "global", "-j"],
                capture_output=True, text=True, timeout=5
            )
            if gi.returncode == 0 and gi.stdout.strip():
                bgp_info = _json.loads(gi.stdout)
        except Exception:
            pass

    return {
        "status": "active" if is_running else "inactive",
        "pid": "",
        "gobgp_host": "Host OS (via nsenter)",
        "gobgp_available": is_running,
        "global": bgp_info,
        "raw": f"GoBGP daemon {'terhubung dan aktif' if is_running else 'tidak aktif atau gagal diverifikasi'}"
    }


@router.get("/bgp/peers/log")
async def bgp_peers_log(lines: int = 80, user=Depends(get_current_user)):
    """
    Ambil log GoBGP daemon dari journald di HOST via nsenter.
    Returns list of recent log lines.
    """
    log_lines = []
    try:
        result = subprocess.run(
            ["nsenter", "-t", "1", "-m", "-u", "-i", "-n", "-p", "--",
             "journalctl", "-u", "gobgpd", "--no-pager", "-n", str(lines), "--output", "short-iso"],
            capture_output=True, text=True, timeout=10
        )
        if result.returncode == 0 and result.stdout.strip():
            raw = result.stdout.strip().split("\n")
            # Parse dan annotate tiap baris
            for line in raw:
                level = "info"
                if any(w in line.lower() for w in ["error", "fail", "panic", "fatal"]):
                    level = "error"
                elif any(w in line.lower() for w in ["warn", "warning"]):
                    level = "warn"
                elif any(w in line.lower() for w in ["established", "connect", "open"]):
                    level = "success"
                elif any(w in line.lower() for w in ["idle", "active", "notification"]):
                    level = "notice"
                log_lines.append({"text": line, "level": level})
        elif result.stderr.strip():
            log_lines.append({"text": result.stderr.strip(), "level": "error"})
        else:
            log_lines.append({"text": "Tidak ada log tersedia. Pastikan gobgpd berjalan dan journald aktif.", "level": "warn"})
    except Exception as e:
        log_lines.append({"text": f"Gagal ambil log: {str(e)}", "level": "error"})

    return {"lines": log_lines, "count": len(log_lines)}


class BGPServiceControl(BaseModel):
    action: str  # "start", "stop", "restart"

@router.post("/bgp/service/control")
async def bgp_service_control(payload: BGPServiceControl, user=Depends(require_write)):
    """
    Control GoBGP daemon di HOST Ubuntu via nsenter + systemctl.
    GoBGP berjalan sebagai systemd service di host, bukan di dalam container.

    PENTING: sentinel-bgp.service memiliki Wants=gobgpd.service, sehingga
    setiap kali sentinel-bgp restart, gobgpd ikut di-start otomatis oleh systemd.

    Solusi:
      - stop  → stop gobgpd + stop sentinel-bgp (mencegah auto-restart dependency)
      - start → start gobgpd + start sentinel-bgp
      - restart → restart gobgpd + restart sentinel-bgp
    """
    action = payload.action.lower()
    if action not in ["start", "stop", "restart"]:
        raise HTTPException(status_code=400, detail="Invalid action")

    def run_nsenter(args, timeout=15):
        return subprocess.run(
            ["nsenter", "-t", "1", "-m", "-u", "-i", "-n", "-p", "--"] + args,
            capture_output=True, text=True, timeout=timeout
        )

    try:
        steps = []

        if action == "stop":
            # 1. Stop sentinel-bgp.service terlebih dahulu (ini yang memicu restart gobgpd)
            r1 = run_nsenter(["systemctl", "stop", "sentinel-bgp.service"])
            steps.append(f"sentinel-bgp.service stop: {'OK' if r1.returncode == 0 else r1.stderr.strip()}")

            # 2. Stop gobgpd
            r2 = run_nsenter(["systemctl", "stop", "gobgpd"])
            if r2.returncode != 0:
                err = r2.stderr.strip() or r2.stdout.strip()
                raise HTTPException(status_code=500, detail=f"systemctl stop gobgpd gagal: {err}")
            steps.append("gobgpd stop: OK")

        elif action == "start":
            # 1. Start gobgpd
            r1 = run_nsenter(["systemctl", "start", "gobgpd"])
            if r1.returncode != 0:
                err = r1.stderr.strip() or r1.stdout.strip()
                raise HTTPException(status_code=500, detail=f"systemctl start gobgpd gagal: {err}")
            steps.append("gobgpd start: OK")

            # 2. Start sentinel-bgp.service juga
            r2 = run_nsenter(["systemctl", "start", "sentinel-bgp.service"])
            steps.append(f"sentinel-bgp.service start: {'OK' if r2.returncode == 0 else r2.stderr.strip()}")

        elif action == "restart":
            # Stop sentinel-bgp dulu, restart gobgpd, lalu start sentinel-bgp kembali
            r0 = run_nsenter(["systemctl", "stop", "sentinel-bgp.service"])
            steps.append(f"sentinel-bgp.service stop: {'OK' if r0.returncode == 0 else r0.stderr.strip()}")

            r1 = run_nsenter(["systemctl", "restart", "gobgpd"])
            if r1.returncode != 0:
                err = r1.stderr.strip() or r1.stdout.strip()
                raise HTTPException(status_code=500, detail=f"systemctl restart gobgpd gagal: {err}")
            steps.append("gobgpd restart: OK")

            r2 = run_nsenter(["systemctl", "start", "sentinel-bgp.service"])
            steps.append(f"sentinel-bgp.service start: {'OK' if r2.returncode == 0 else r2.stderr.strip()}")

        await asyncio.sleep(2)

        # Verifikasi status akhir
        status_r = run_nsenter(["systemctl", "is-active", "gobgpd"])
        final_status = status_r.stdout.strip()

        return {
            "success": True,
            "message": f"GoBGP daemon berhasil di-{action}. Status sekarang: {final_status}",
            "action": action,
            "gobgpd_status": final_status,
            "steps": steps,
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))




async def _sync_bgp_peers_to_gobgp(db) -> dict:
    """
    Sinkronisasi peer BGP dari database ke gobgpd di HOST Ubuntu via nsenter.
    Jika device memiliki bgp_peer_ip (manual override, misal SSTP/VPN IP), gunakan itu
    sebagai neighbor address. Jika tidak ada, fallback ke ip_address.
    """
    import json as _json

    # Cek apakah gobgpd is active dulu
    test = subprocess.run(
        ["nsenter", "-t", "1", "-m", "-u", "-i", "-n", "-p", "--", "systemctl", "is-active", "gobgpd"],
        capture_output=True, text=True, timeout=5
    )
    if test.stdout.strip() != "active":
        return {"success": False, "error": "gobgpd daemon di host belum aktif. Jalankan service BGP terlebih dahulu."}

    # Ambil semua device BGP-enabled (termasuk field bgp_peer_ip)
    devices = await db.devices.find(
        {"bgp_enabled": True},
        {"_id": 0, "id": 1, "name": 1, "ip_address": 1, "bgp_peer_as": 1, "bgp_peer_ip": 1}
    ).to_list(None)

    if not devices:
        return {"success": True, "added": 0, "message": "Tidak ada device dengan BGP diaktifkan."}

    added = 0
    errors = []

    for dev in devices:
        # Prioritas: bgp_peer_ip (SSTP/VPN manual IP override) → ip_address default
        override_ip = (dev.get("bgp_peer_ip") or "").strip()
        default_ip  = dev.get("ip_address", "").split(":")[0].strip()
        neighbor_ip = override_ip if override_ip else default_ip

        if not neighbor_ip:
            continue

        try:
            peer_as = int(str(dev.get("bgp_peer_as", 65000)).strip())
            if peer_as <= 0:
                peer_as = 65000
        except (ValueError, TypeError):
            peer_as = 65000

        # 1. Pastikan IP valid
        import ipaddress
        try:
            ipaddress.ip_address(neighbor_ip)
        except ValueError:
            errors.append(f"{dev.get('name', '')}: IP {neighbor_ip} tidak valid")
            continue

        # 2. Sync via nsenter host
        # Kami hapus dulu (jika ada) agar parameter (TTL/Passive) terupdate jika ada perubahan di DB
        del_cmd = ["nsenter", "-t", "1", "-m", "-u", "-i", "-n", "-p", "--", "/usr/local/bin/gobgp", "neighbor", "del", neighbor_ip]
        subprocess.run(del_cmd, capture_output=True, timeout=5)

        # Tambahkan kembali dengan TTL 255 (Multihop) dan Passive mode
        cmd = [
            "nsenter", "-t", "1", "-m", "-u", "-i", "-n", "-p", "--",
            "/usr/local/bin/gobgp", "neighbor", "add", neighbor_ip,
            "as", str(peer_as),
            "ebgp-multihop-ttl", "255"
        ]
        
        res = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
        if res.returncode == 0:
            added += 1
        else:
            err = res.stderr.strip() or res.stdout.strip()
            errors.append(f"{neighbor_ip}: {err}")

    return {
        "success": True,
        "added": added,
        "total_bgp_devices": len(devices),
        "errors": errors,
        "message": f"{added}/{len(devices)} peer berhasil ditambahkan ke gobgpd di host."
    }



async def _poll_bgp_status(db) -> dict:
    """
    Poll status semua BGP neighbor dari gobgpd yang berjalan,
    simpan ke MongoDB agar frontend bisa membacanya.
    """
    import json as _json

    # Ambil info nama device dari DB untuk enrichment
    devices_info = {}
    async for d in db.devices.find({}, {"_id": 0, "ip_address": 1, "name": 1, "bgp_peer_as": 1}):
        ip = d.get("ip_address", "").split(":")[0]
        devices_info[ip] = {"name": d.get("name", ""), "bgp_peer_as": d.get("bgp_peer_as", 0)}

    # Query via nsenter
    result = subprocess.run(
        ["nsenter", "-t", "1", "-m", "-u", "-i", "-n", "-p", "--", "/usr/local/bin/gobgp", "neighbor", "-j"],
        capture_output=True, text=True, timeout=10
    )
    if result.returncode != 0 or not result.stdout.strip():
        return {"peers": [], "established": 0, "total": 0}

    try:
        neighbors = _json.loads(result.stdout)
    except Exception:
        return {"peers": [], "established": 0, "total": 0}

    peers = []
    from datetime import datetime, timezone
    now_iso = datetime.now(timezone.utc).isoformat()
    BGP_FSM = {0: "UNKNOWN", 1: "IDLE", 2: "CONNECT", 3: "ACTIVE", 4: "OPENSENT", 5: "OPENCONFIRM", 6: "ESTABLISHED"}

    for n in neighbors:
        state = n.get("state", {})
        conf  = n.get("conf", {})

        ip = (conf.get("neighbor_address") or conf.get("neighbor-address") or conf.get("neighborAddress") or
              state.get("neighbor_address") or state.get("neighbor-address") or state.get("neighborAddress") or "unknown")

        peer_as = (conf.get("peer_asn") or conf.get("peer-as") or conf.get("peerAs") or
                   state.get("peer_asn") or state.get("peer-as") or state.get("peerAs") or 0)

        raw_state = state.get("session_state") or state.get("session-state") or state.get("sessionState")
        if isinstance(raw_state, int):
            session_state = BGP_FSM.get(raw_state, str(raw_state))
        else:
            session_state = str(raw_state).upper() if raw_state else "UNKNOWN"

        pfx = {}
        afi_safis = n.get("afi-safis") or n.get("afiSafis") or []
        if afi_safis:
            pfx = afi_safis[0].get("state", {})

        dev_info   = devices_info.get(ip, {})
        device_name = dev_info.get("name") or ip

        peer = {
            "neighbor_ip":   ip,
            "peer_as":       peer_as,
            "state":         session_state,
            "uptime_sec":    state.get("uptime") or state.get("upTime") or 0,
            "prefixes_rx":   pfx.get("received") or pfx.get("received-prefixes") or 0,
            "prefixes_tx":   pfx.get("advertised") or pfx.get("advertised-prefixes") or 0,
            "device_name":   device_name,
            "updated_at":    now_iso,
        }
        peers.append(peer)

    # Simpan ke MongoDB
    await db.peering_eye_bgp_status.delete_many({})
    if peers:
        await db.peering_eye_bgp_status.insert_many([{**p} for p in peers])

    established = sum(1 for p in peers if p["state"] == "ESTABLISHED")
    return {"peers": peers, "established": established, "total": len(peers), "updated_at": now_iso}


@router.post("/bgp/peers/sync")
async def bgp_peers_sync(user=Depends(require_write)):
    """Sinkronisasi manual: kirim semua peer BGP dari DB ke gobgpd."""
    db = get_db()
    result = await _sync_bgp_peers_to_gobgp(db)
    if not result.get("success"):
        raise HTTPException(status_code=503, detail=result.get("error", "Gagal sync peers"))
    # Setelah sync, langsung poll status
    await _poll_bgp_status(db)
    return result


@router.get("/bgp/peers/status")
async def bgp_peers_status(user=Depends(get_current_user)):
    """Ambil daftar peer status GoBGP langsung dari HOST via nsenter."""
    import json as _json

    try:
        ni = subprocess.run(
            ["nsenter", "-t", "1", "-m", "-u", "-i", "-n", "-p", "--", "/usr/local/bin/gobgp", "neighbor", "-j"],
            capture_output=True, text=True, timeout=5
        )
        if ni.returncode != 0:
            return {"peers": [], "total": 0, "established": 0, "error": "Connection refused to GoBGP API. Pastikan Daemon aktif."}
        
        peers_data = []
        # ... (logic parsing)
        return await _poll_bgp_status(get_db())
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/bgp/peers/diagnose")
async def bgp_peers_diagnose(user=Depends(get_current_user)):
    """
    Endpoint diagnostik: cek koneksi API ke semua device BGP-enabled,
    baca BGP connection/peer dari RouterOS (ROS6 atau ROS7), dan tampilkan hasilnya.
    - ROS 7: REST API  → GET /routing/bgp/connection
    - ROS 6: Legacy API Protocol → /routing/bgp/peer
    """
    db = get_db()
    devices = await db.devices.find(
        {},
        {"_id": 0, "id": 1, "name": 1, "ip_address": 1,
         "api_mode": 1, "bgp_enabled": 1, "bgp_peer_as": 1,
         "bgp_peer_ip": 1, "api_username": 1, "api_port": 1,
         "use_https": 1, "ros_version": 1}
    ).to_list(100)
    results = []

    for dev in devices:
        api_mode = dev.get("api_mode", "rest")
        ros_ver  = dev.get("ros_version", "")

        # Deteksi ROS generasi berdasarkan api_mode & ros_version
        is_ros6 = (api_mode == "api") or (ros_ver.startswith("6"))
        is_ros7 = (api_mode == "rest") or (ros_ver.startswith("7"))

        info = {
            "device_id":   dev.get("id"),
            "name":        dev.get("name"),
            "ip":          dev.get("ip_address"),
            "bgp_peer_ip": dev.get("bgp_peer_ip") or None,  # SSTP/VPN IP override
            "api_mode":    api_mode,
            "ros_version": ros_ver or ("6.x" if is_ros6 else "7.x"),
            "ros_gen":     "ROS 6" if is_ros6 else "ROS 7",
            "bgp_enabled": dev.get("bgp_enabled", False),
            "bgp_peer_as": dev.get("bgp_peer_as"),
            "reachable":   False,
            "bgp_connections": [],
            "error":       None
        }

        mt_api = get_api_client(dev)

        # ── ROS 7 (REST API) ─────────────────────────────────────────────────
        if is_ros7 and hasattr(mt_api, "_async_req"):
            try:
                ident = await mt_api._async_req("GET", "system/identity")
                info["reachable"] = True
                info["identity"]  = ident.get("name") if isinstance(ident, dict) else str(ident)
                # Detect ROS version from resource if not stored
                if not ros_ver:
                    try:
                        res = await mt_api._async_req("GET", "system/resource")
                        info["ros_version"] = res.get("version", "") if isinstance(res, dict) else ""
                        info["ros_gen"] = "ROS 6" if info["ros_version"].startswith("6") else "ROS 7"
                    except Exception:
                        pass
            except Exception as e:
                info["error"] = f"[ROS 7] Gagal terhubung ke REST API: {e}"
                results.append(info)
                continue

            try:
                conns = await mt_api._async_req("GET", "routing/bgp/connection")
                info["bgp_connections"]     = conns if conns else []
                info["bgp_connection_count"] = len(conns) if conns else 0
            except Exception as e:
                info["error"] = f"[ROS 7] Terhubung OK, tapi gagal baca BGP connections: {e}"

        # ── ROS 6 (Legacy API Protocol / port 8728) ──────────────────────────
        elif is_ros6 and hasattr(mt_api, "_list_resource"):
            try:
                # Test koneksi via legacy API
                test_result = await mt_api.test_connection()
                if not test_result.get("success"):
                    raise Exception(test_result.get("error", "Connection failed"))
                info["reachable"] = True
                # Ambil identity
                try:
                    info["identity"] = await mt_api.get_system_identity() or ""
                except Exception:
                    info["identity"] = ""
                # Detect ROS version from system resource
                if not ros_ver:
                    try:
                        res = await mt_api.get_system_resource()
                        info["ros_version"] = res.get("version", "") if isinstance(res, dict) else ""
                        info["ros_gen"] = "ROS 6" if info["ros_version"].startswith("6") else "ROS 7"
                    except Exception:
                        pass
            except Exception as e:
                info["error"] = f"[ROS 6] Gagal terhubung via API Protocol (port 8728): {e}"
                results.append(info)
                continue

            # Baca BGP peers (ROS 6 menggunakan /routing/bgp/peer)
            try:
                peers = await mt_api.list_bgp_peers()
                if peers:
                    # Normalisasi format ROS 6 ke format yang sama
                    normalized = []
                    for p in peers:
                        normalized.append({
                            ".id":              p.get(".id", ""),
                            "name":             p.get("name", ""),
                            "as":               p.get("as", ""),
                            "remote-address":   p.get("remote-address", ""),
                            "remote-as":        p.get("remote-as", ""),
                            "connection-state": p.get("state", p.get("connection-state", "unknown")),
                            "_ros6":            True,
                        })
                    info["bgp_connections"]      = normalized
                    info["bgp_connection_count"] = len(normalized)
                else:
                    info["bgp_connections"]      = []
                    info["bgp_connection_count"] = 0
            except Exception as e:
                info["error"] = f"[ROS 6] Terhubung OK, tapi gagal baca BGP peers: {e}"


        else:
            # Tidak bisa determine mode
            info["error"] = (
                f"Mode API tidak dikenali (api_mode={api_mode}). "
                "Pastikan api_mode diset ke 'rest' (ROS 7) atau 'api' (ROS 6) di pengaturan device."
            )

        results.append(info)

    return {
        "total_devices": len(devices),
        "results": results,
        "tip": "Pastikan api_mode=rest (ROS 7) atau api_mode=api (ROS 6), bgp_enabled=true, dan credential benar di pengaturan device"
    }



@router.get("/bgp/settings")
async def get_bgp_settings(user=Depends(get_current_user)):
    """Ambil konfigurasi BGP global: local_as dan router_id (IP GoBGP server)."""
    db = get_db()
    settings = await db.bgp_settings.find_one({}, {"_id": 0}) or {}
    return {
        "local_as": int(settings.get("local_as", 65000)),
        "router_id": str(settings.get("router_id", "")),
    }


@router.post("/bgp/settings")
async def save_bgp_settings(payload: dict = Body(...), user=Depends(require_write)):
    """Simpan konfigurasi BGP global: local_as dan router_id."""
    db = get_db()
    update = {}
    if "local_as" in payload:
        update["local_as"] = int(payload["local_as"])
    if "router_id" in payload:
        update["router_id"] = str(payload["router_id"]).strip()
    if not update:
        raise HTTPException(400, "Tidak ada field yang diupdate")
    await db.bgp_settings.update_one({}, {"$set": update}, upsert=True)
    
    # Update config file di host
    config_text = f"""[global.config]
  as = {update.get("local_as", 65000)}
  router-id = "{update.get("router_id", "")}"
"""
    try:
        subprocess.run(
            ["nsenter", "-t", "1", "-m", "-u", "-i", "-n", "-p", "--", "bash", "-c", "cat > /etc/gobgpd/gobgpd.conf"],
            input=config_text,
            text=True,
            check=True
        )
        subprocess.run(["nsenter", "-t", "1", "-m", "-u", "-i", "-n", "-p", "--", "systemctl", "restart", "gobgpd"], check=True)
    except Exception as e:
        raise HTTPException(500, f"Gagal update config host: {e}")
        
    return {"success": True, "settings": update}


@router.post("/bgp/peers/autofix")
async def bgp_peers_autofix(payload: dict = Body(...), user=Depends(require_write)):
    """
    Auto-fix RouterOS v7 BGP Connection yang bermasalah (AS Number missing / remote addr salah).
    Setelah fix berhasil, otomatis re-sync gobgpd dan poll status.
    """
    neighbor_ip = payload.get("neighbor_ip")
    if not neighbor_ip:
        raise HTTPException(status_code=400, detail="Missing neighbor_ip")

    db = get_db()

    # Ambil BGP settings — router_id adalah IP server GoBGP yang harus di-reach MikroTik
    bgp_settings = await db.bgp_settings.find_one({}, {"_id": 0}) or {}
    server_as    = int(bgp_settings.get("local_as", 65000))
    # Prioritas server_ip: payload → router_id di DB → tolak
    server_ip = (
        (payload.get("server_ip") or "").strip()
        or str(bgp_settings.get("router_id", "")).strip()
    )
    if not server_ip or server_ip in ("127.0.0.1", "0.0.0.0"):
        raise HTTPException(
            status_code=400,
            detail=(
                "IP GoBGP server (router_id) belum dikonfigurasi. "
                "Masukkan IP server NOC Sentinel yang bisa diakses MikroTik di pengaturan BGP."
            )
        )

    # 1. Kumpulkan devices untuk diautofix
    devices_to_fix = []
    if neighbor_ip in ("unknown", "All", "all"):
        async for d in db.devices.find({"bgp_enabled": True}):
            devices_to_fix.append(d)
        if not devices_to_fix:
            async for d in db.devices.find():
                devices_to_fix.append(d)
        if not devices_to_fix:
            raise HTTPException(status_code=404, detail="Tidak ada device sama sekali di Database NOC.")
    else:
        # Cari berdasarkan IP
        async for d in db.devices.find():
            ip = d.get("ip_address", "").split(":")[0]
            if ip == neighbor_ip:
                devices_to_fix.append(d)
                break
        if not devices_to_fix:
            raise HTTPException(status_code=404, detail=f"Router dengan IP {neighbor_ip} tidak ditemukan.")

    total_fixed = 0
    errors = []
    detail_log = []

    for dev in devices_to_fix:
        dev_name = dev.get("name", "unknown")
        dev_log  = {"device": dev_name, "ip": dev.get("ip_address"), "steps": []}

        try:
            device_as = int(dev.get("bgp_peer_as") or 0)
        except Exception:
            device_as = 0
        if device_as <= 0:
            device_as = server_as + 1  # Default eBGP: server+1

        mt_api = get_api_client(dev)
        if not hasattr(mt_api, "_async_req"):
            msg = f"{dev_name}: mode API bukan REST — ubah api_mode ke 'rest' di pengaturan device"
            errors.append(msg)
            dev_log["steps"].append(msg)
            detail_log.append(dev_log)
            continue

        # Step 1: Test koneksi dasar
        try:
            ident = await mt_api._async_req("GET", "system/identity")
            dev_log["steps"].append(f"✅ Terhubung ke: {ident.get('name', dev_name) if isinstance(ident, dict) else ident}")
        except Exception as e:
            msg = f"{dev_name}: Gagal terhubung ke REST API — {e}"
            errors.append(msg)
            dev_log["steps"].append(f"❌ {msg}")
            detail_log.append(dev_log)
            continue

        # Step 2: Baca BGP connections
        try:
            conns = await mt_api._async_req("GET", "routing/bgp/connection")
        except Exception as e:
            msg = f"{dev_name}: Gagal baca BGP connections — {e}"
            errors.append(msg)
            dev_log["steps"].append(f"❌ {msg}")
            detail_log.append(dev_log)
            continue

        if conns is None:
            conns = []
        dev_log["steps"].append(f"ℹ️ Ditemukan {len(conns)} BGP connection di MikroTik")
        dev_log["existing_connections"] = conns

        found_server_conn = False
        role = "ebgp" if device_as != server_as else "ibgp"

        for c in conns:
            cid = c.get(".id")
            if not cid:
                continue

            asn      = str(c.get("as", "0"))
            name     = c.get("name", "")
            remote_obj = c.get("remote") or {}

            if isinstance(remote_obj, dict):
                remote_addr = str(remote_obj.get("address", ""))
                ras         = str(remote_obj.get("as", "0"))
            else:
                remote_addr = str(c.get("remote.address", ""))
                ras         = str(c.get("remote.as", "0"))

            # Perbaiki jika: AS hilang, remote.as hilang, atau remote.address salah / kosong
            needs_fix = (
                asn in ("0", "", None)
                or ras in ("0", "", None)
                or not remote_addr
                or remote_addr in ("0.0.0.0", "")
                or (server_ip and server_ip not in remote_addr)
            )

            if needs_fix:
                found_server_conn = True
                new_name = name if name and name not in ("unknown", "") else "NOC-Sentinel"
                update_data: dict = {
                    "name": new_name,
                    "as": str(device_as),
                    "remote": {
                        "address": server_ip,
                        "as": str(server_as),
                    },
                    "local": {"role": role},
                }
                try:
                    await mt_api._async_req("PATCH", f"routing/bgp/connection/{cid}", update_data)
                    total_fixed += 1
                    dev_log["steps"].append(
                        f"✅ PATCH sukses: '{new_name}' → AS={device_as}, "
                        f"remote.as={server_as}, remote.address={server_ip}"
                    )
                    # Pastikan bgp_enabled=True di DB
                    await db.devices.update_one(
                        {"id": dev.get("id")},
                        {"$set": {"bgp_enabled": True, "bgp_peer_as": device_as}}
                    )
                except Exception as e:
                    msg = f"{dev_name} PATCH [{cid}]: {e}"
                    errors.append(msg)
                    dev_log["steps"].append(f"❌ {msg}")

        # Jika tidak ada connection → buat baru
        if not found_server_conn:
            try:
                await mt_api._async_req("POST", "routing/bgp/connection", {
                    "name": "NOC-Sentinel",
                    "as":   str(device_as),
                    "remote": {
                        "address": server_ip,
                        "as":      str(server_as),
                    },
                    "local": {"role": role},
                })
                total_fixed += 1
                dev_log["steps"].append(
                    f"✅ POST sukses: BGP connection baru 'NOC-Sentinel' → {server_ip} AS{server_as}"
                )
                await db.devices.update_one(
                    {"id": dev.get("id")},
                    {"$set": {"bgp_enabled": True, "bgp_peer_as": device_as}}
                )
            except Exception as e:
                msg = f"{dev_name} POST BGP baru: {e}"
                errors.append(msg)
                dev_log["steps"].append(f"❌ {msg}")

        detail_log.append(dev_log)

    # Setelah fix berhasil → re-sync & poll gobgpd agar status ikut update
    if total_fixed > 0:
        try:
            test = subprocess.run(["nsenter", "-t", "1", "-m", "-u", "-i", "-n", "-p", "--", "systemctl", "is-active", "gobgpd"], capture_output=True, text=True)
            if test.stdout.strip() == "active":
                await _sync_bgp_peers_to_gobgp(db)
                await _poll_bgp_status(db)
        except Exception:
            pass  # Jangan biarkan kegagalan sync membatalkan respons sukses

        return {
            "success": True,
            "message": f"{total_fixed} BGP connection berhasil diperbaiki! GoBGP telah di-sync ulang.",
            "fixed": total_fixed,
            "server_ip": server_ip,
            "server_as": server_as,
            "detail": detail_log,
        }
    elif errors:
        raise HTTPException(
            status_code=400,
            detail={
                "message": f"Gagal memproses {len(devices_to_fix)} device",
                "errors": errors,
                "detail": detail_log,
                "hint": "Buka /api/peering-eye/bgp/peers/diagnose untuk diagnosis lengkap",
            }
        )
    else:
        return {
            "success": True,
            "message": "Tidak ada perubahan — semua BGP connection sudah terkonfigurasi dengan benar.",
            "server_ip": server_ip,
            "detail": detail_log,
        }



@router.post("/bgp/peers/push-community-filter")
async def push_bgp_community_filter(
    payload: dict = Body(default={}),
    user=Depends(require_write)
):
    """
    Push BGP Community Filter ke MikroTik (ROS v7).

    Endpoint ini secara otomatis mengkonfigurasi routing filter rule
    di MikroTik sehingga setiap peer HANYA menerima prefix BGP dengan
    community yang sesuai dari GoBGP (format: LOCAL_AS:LAST_OCTET).

    Contoh:
      - NIKI (10.254.254.251) → hanya terima prefix dengan community 65000:251
      - ARIPIN (10.254.254.252) → hanya terima prefix dengan community 65000:252

    Syntax ROS v7 yang digunakan (sudah benar):
      if (bgp-communities.any(65000:252)) { accept } else { reject }

    Body (optional):
      neighbor_ip: "all" | "10.254.254.252"  — default: "all"
    """
    db = get_db()
    neighbor_ip = (payload.get("neighbor_ip") or "all").strip()

    bgp_settings = await db.bgp_settings.find_one({}, {"_id": 0}) or {}
    local_as = int(bgp_settings.get("local_as", 65000))

    # Ambil BGP peers dari DB status
    peers = await db.peering_eye_bgp_status.find({}, {"_id": 0}).to_list(100)
    if not peers:
        raise HTTPException(status_code=404, detail="Tidak ada BGP peer ditemukan di database.")

    if neighbor_ip not in ("all", "All", "ALL"):
        peers = [p for p in peers if p.get("neighbor_ip") == neighbor_ip]
        if not peers:
            raise HTTPException(status_code=404, detail=f"Peer {neighbor_ip} tidak ditemukan.")

    results = []

    for peer in peers:
        peer_ip = peer.get("neighbor_ip", "")
        device_name = peer.get("device_name", peer_ip)
        last_octet = peer_ip.split(".")[-1] if peer_ip else ""
        community_val = f"{local_as}:{last_octet}"

        peer_result: dict = {
            "peer": peer_ip,
            "device": device_name,
            "community": community_val,
            "success": False,
            "steps": [],
            "error": None,
        }

        # Cari device di DB berdasarkan IP
        dev = await db.devices.find_one(
            {"ip_address": {"$regex": f"^{peer_ip}"}},
            {"_id": 0}
        )
        if not dev:
            peer_result["error"] = f"Device dengan IP {peer_ip} tidak ditemukan di database devices."
            peer_result["hint"] = "Pastikan device sudah di-add dan ip_address cocok."
            results.append(peer_result)
            continue

        mt_api = get_api_client(dev)
        if not hasattr(mt_api, "_async_req"):
            peer_result["error"] = f"Device {device_name} menggunakan API mode lama (non-REST). Ubah ke REST API (ROS 7+)."
            results.append(peer_result)
            continue

        # Test koneksi
        try:
            ident = await mt_api._async_req("GET", "system/identity")
            router_name = ident.get("name", device_name) if isinstance(ident, dict) else device_name
            peer_result["steps"].append(f"✅ Terhubung ke: {router_name}")
        except Exception as conn_err:
            peer_result["error"] = f"Gagal terhubung ke REST API: {conn_err}"
            results.append(peer_result)
            continue

        # Push community filter
        try:
            filter_result = await mt_api.ensure_bgp_community_filter(
                community_value=community_val,
                local_as=local_as
            )
            peer_result["steps"].extend(filter_result.get("steps", []))
            peer_result["success"] = filter_result.get("success", False)
            peer_result["filter_chain"] = filter_result.get("chain", "sentinel-bgp-in")
            peer_result["filter_rule_id"] = filter_result.get("filter_rule_id", "")
            if not filter_result.get("success"):
                peer_result["error"] = filter_result.get("error", "Unknown error")
        except Exception as e:
            peer_result["error"] = str(e)
            peer_result["steps"].append(f"❌ Exception: {e}")

        results.append(peer_result)

    total_ok = sum(1 for r in results if r.get("success"))
    return {
        "success": total_ok > 0,
        "message": (
            f"Community filter berhasil di-push ke {total_ok}/{len(results)} peer MikroTik. "
            f"Setiap peer sekarang hanya menerima prefix dengan community BGP yang sesuai."
        ),
        "syntax_info": "ROS v7: if (bgp-communities.any(LOCAL_AS:LAST_OCTET)) { accept } else { reject }",
        "local_as": local_as,
        "results": results,
    }


import httpx
from services.peering_intelligence_cache import cache_get, cache_set


# Major content providers untuk latency map
CONTENT_PROVIDERS = [
    {"name": "Google",        "icon": "G",  "ips": ["8.8.8.8", "142.250.4.1"],      "asn": 15169},
    {"name": "Cloudflare",    "icon": "CF", "ips": ["1.1.1.1", "104.16.0.1"],       "asn": 13335},
    {"name": "Netflix",       "icon": "NF", "ips": ["45.57.0.0", "198.38.96.0"],    "asn": 2906},
    {"name": "Akamai",        "icon": "AK", "ips": ["23.32.0.0", "184.85.0.0"],     "asn": 20940},
    {"name": "Meta/Facebook", "icon": "FB", "ips": ["157.240.0.1", "31.13.64.1"],   "asn": 32934},
    {"name": "AWS",           "icon": "AW", "ips": ["54.239.0.0", "52.94.0.0"],     "asn": 16509},
    {"name": "TikTok",        "icon": "TK", "ips": ["23.105.0.0", "128.242.0.0"],   "asn": 396986},
    {"name": "Telegram",      "icon": "TG", "ips": ["149.154.160.0", "91.108.4.0"], "asn": 62041},
    {"name": "WhatsApp",      "icon": "WA", "ips": ["157.240.0.1", "31.13.71.1"],   "asn": 32934},
    {"name": "Indihome/Telkom","icon": "TL", "ips": ["103.28.82.0", "118.98.0.0"],  "asn": 7713},
    {"name": "Biznet",        "icon": "BN", "ips": ["36.86.0.0", "114.4.0.0"],      "asn": 17451},
    {"name": "YouTube",       "icon": "YT", "ips": ["216.58.0.0", "142.250.0.0"],   "asn": 15169},
]


async def _enrich_asn_bgpview(asn: int, db) -> dict:
    """Fetch ASN info dari BGPView API dengan cache 6 jam."""
    key = f"asn:{asn}"
    cached = await cache_get(db, key)
    if cached:
        return cached
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            r = await client.get(
                f"https://api.bgpview.io/asn/{asn}",
                headers={"User-Agent": "NOC-Sentinel/3"}
            )
            if r.status_code == 200:
                d = r.json().get("data", {})
                result = {
                    "asn": asn,
                    "name": d.get("name", "N/A"),
                    "description": d.get("description_short", ""),
                    "country_code": d.get("country_code", ""),
                    "website": d.get("website", ""),
                }
                await cache_set(db, key, result, ttl_seconds=21600)
                return result
    except Exception:
        pass
    return {"asn": asn, "name": "N/A", "description": "", "country_code": ""}


async def _enrich_asn_prefixes(asn: int, db) -> dict:
    """Fetch prefix count dari BGPView /asn/{asn}/prefixes dengan cache 6 jam."""
    key = f"prefixes:{asn}"
    cached = await cache_get(db, key)
    if cached:
        return cached
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            r = await client.get(
                f"https://api.bgpview.io/asn/{asn}/prefixes",
                headers={"User-Agent": "NOC-Sentinel/3"}
            )
            if r.status_code == 200:
                d = r.json().get("data", {})
                result = {
                    "ipv4_count": len(d.get("ipv4_prefixes", [])),
                    "ipv6_count": len(d.get("ipv6_prefixes", [])),
                }
                await cache_set(db, key, result, ttl_seconds=21600)
                return result
    except Exception:
        pass
    return {"ipv4_count": 0, "ipv6_count": 0}


async def _fetch_peeringdb(asn: int, db) -> dict:
    """Fetch IX membership dari PeeringDB dengan cache 6 jam."""
    key = f"peeringdb:{asn}"
    cached = await cache_get(db, key)
    if cached:
        return cached
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            r = await client.get(
                f"https://www.peeringdb.com/api/net?asn={asn}&fields=name,info_type,info_prefixes4,info_prefixes6,policy_general",
                headers={"User-Agent": "NOC-Sentinel/3"}
            )
            net_info = {}
            ix_list = []
            if r.status_code == 200:
                data = r.json().get("data", [])
                if data:
                    net = data[0]
                    net_info = {
                        "name": net.get("name", ""),
                        "type": net.get("info_type", ""),
                        "policy": net.get("policy_general", ""),
                        "prefixes4": net.get("info_prefixes4", 0),
                        "prefixes6": net.get("info_prefixes6", 0),
                    }
                    r2 = await client.get(
                        f"https://www.peeringdb.com/api/netixlan?net__asn={asn}&fields=name,speed",
                        headers={"User-Agent": "NOC-Sentinel/3"}
                    )
                    if r2.status_code == 200:
                        for ix in r2.json().get("data", [])[:15]:
                            ix_list.append({
                                "name": ix.get("name", ""),
                                "speed_mbps": ix.get("speed", 0),
                            })
            result = {"net": net_info, "ix_list": ix_list}
            await cache_set(db, key, result, ttl_seconds=21600)
            return result
    except Exception:
        pass
    return {"net": {}, "ix_list": []}


async def _ip_to_asn(ip: str, db) -> dict:
    """Lookup IP ke ASN via ip-api.com dengan cache 6 jam."""
    if not ip or ip == "*":
        return {"ip": ip, "asn": 0, "org": "", "isp": "", "country": ""}
    key = f"ipasn:{ip}"
    cached = await cache_get(db, key)
    if cached:
        return cached
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            r = await client.get(
                f"http://ip-api.com/json/{ip}?fields=as,org,country,city,isp,status",
                headers={"User-Agent": "NOC-Sentinel/3"}
            )
            if r.status_code == 200:
                d = r.json()
                asn_raw = d.get("as", "")
                asn_num = 0
                if asn_raw:
                    try:
                        asn_num = int(asn_raw.split(" ")[0].replace("AS", ""))
                    except ValueError:
                        pass
                result = {
                    "ip": ip,
                    "asn_raw": asn_raw,
                    "asn": asn_num,
                    "org": d.get("org", ""),
                    "isp": d.get("isp", ""),
                    "country": d.get("country", ""),
                    "city": d.get("city", ""),
                }
                await cache_set(db, key, result, ttl_seconds=21600)
                return result
    except Exception:
        pass
    return {"ip": ip, "asn": 0, "org": "", "isp": "", "country": ""}


# ─── Endpoint 1: Auto-Mode Detection ─────────────────────────────────────────
@router.get("/intelligence/mode")
async def intelligence_mode(user=Depends(get_current_user)):
    """Auto-detect apakah mode BGP atau Broadband."""
    db = get_db()
    bgp_count = await db.peering_eye_bgp_status.count_documents({})
    if bgp_count > 0:
        peers = await db.peering_eye_bgp_status.find(
            {}, {"_id": 0, "remote_as": 1, "name": 1, "state": 1}
        ).to_list(5)
        return {
            "mode": "bgp",
            "bgp_peer_count": bgp_count,
            "established": sum(1 for p in peers if p.get("state") == "ESTABLISHED"),
            "sample_peers": peers,
            "description": "BGP peering aktif. Gunakan ASN Enrichment untuk analisis peer.",
        }
    return {
        "mode": "broadband",
        "bgp_peer_count": 0,
        "description": "Tidak ada BGP session. Mode Broadband aktif — gunakan Upstream Path Analysis.",
    }


# ─── Endpoint 2: ASN Enrichment (BGP Mode) ───────────────────────────────────
@router.get("/intelligence/asn-enrichment")
async def asn_enrichment(user=Depends(get_current_user)):
    """
    Enrich semua BGP peer dengan data BGPView + PeeringDB.
    Cache 6 jam per ASN.
    """
    db = get_db()
    peers = await db.peering_eye_bgp_status.find({}, {"_id": 0}).to_list(100)
    if not peers:
        raise HTTPException(404, "Tidak ada BGP peer data. Pastikan sentinel-bgp.service aktif.")

    asn_set = set()
    for p in peers:
        asn = p.get("remote_as", 0)
        try:
            asn_set.add(int(str(asn).replace("AS", "").strip()))
        except (ValueError, TypeError):
            pass

    enriched_asns = {}
    for asn in asn_set:
        info = await _enrich_asn_bgpview(asn, db)
        prefixes = await _enrich_asn_prefixes(asn, db)
        pdb = await _fetch_peeringdb(asn, db)
        enriched_asns[asn] = {**info, **prefixes, "peeringdb": pdb,
                              "ix_count": len(pdb.get("ix_list", [])),
                              "ix_list": pdb.get("ix_list", [])}

    result_peers = []
    for p in peers:
        try:
            asn_int = int(str(p.get("remote_as", 0)).replace("AS", "").strip())
        except (ValueError, TypeError):
            asn_int = 0
        enr = enriched_asns.get(asn_int, {})
        result_peers.append({
            "name": p.get("name", ""),
            "remote_as": p.get("remote_as", 0),
            "state": p.get("state", ""),
            "uptime_fmt": p.get("uptime_fmt", ""),
            "prefix_count": p.get("prefix_count", 0),
            "enrich": enr,
        })

    return {
        "mode": "bgp",
        "peers": result_peers,
        "total_peers": len(result_peers),
        "total_asns": len(asn_set),
    }


# ─── Endpoint 3: Upstream Path Analysis (Broadband Mode) ─────────────────────
@router.get("/intelligence/upstream-path")
async def upstream_path(
    device_id: str = Query(...),
    target: str = Query("1.1.1.1"),
    user=Depends(get_current_user),
):
    """
    Traceroute dari MikroTik ke target. Setiap hop di-enrich ASN via ip-api.com.
    Fallback ke server-side traceroute jika MikroTik tidak support.
    """
    db = get_db()
    dev = await db.devices.find_one({"id": device_id}, {"_id": 0})
    if not dev:
        raise HTTPException(404, "Device tidak ditemukan")

    raw_hops = []
    try:
        api = get_api_client(dev)
        result = await api.run("/tool/traceroute", {"address": target, "count": "3"})
        for entry in (result or []):
            addr = entry.get("address", entry.get("host", ""))
            hop_n = int(entry.get("#", entry.get("hop", len(raw_hops) + 1)))
            if addr:
                raw_hops.append({
                    "hop": hop_n, "ip": addr,
                    "loss": entry.get("loss", "0%"),
                    "avg_ms": entry.get("avg", entry.get("time", "")),
                })
    except Exception as mt_err:
        fallback_ok = False
        try:
            # Fallback manual: Simulasi Traceroute menggunakan ping -t (TTL)
            # Sangat andal untuk Docker environment karena ping biasanya diizinkan
            import re
            max_hops = 20
            target_reached = False
            
            for ttl in range(1, max_hops + 1):
                proc = await asyncio.create_subprocess_exec(
                    "ping", "-c", "1", "-t", str(ttl), "-W", "1", "-n", target,
                    stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
                )
                stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=3)
                out_str = stdout.decode(errors="replace")
                
                # Cari baris yang mengandung "Time to live exceeded" (Hop di tengah jalan)
                # Format: From 192.168.1.1 icmp_seq=1 Time to live exceeded
                ttl_match = re.search(r"From ([\d\.]+).+Time to live exceeded", out_str, re.IGNORECASE)
                
                # Cari baris yang mengandung success reply (Sudah sampai target)
                # Format: 64 bytes from 1.1.1.1: icmp_seq=1 ttl=58 time=14.3 ms
                reply_match = re.search(r"bytes from ([\d\.]+).*time=([\d\.]+)", out_str, re.IGNORECASE)

                if ttl_match:
                    hop_ip = ttl_match.group(1)
                    raw_hops.append({"hop": ttl, "ip": hop_ip, "avg_ms": "*", "loss": ""})
                elif reply_match:
                    hop_ip = reply_match.group(1)
                    ms_val = reply_match.group(2)
                    raw_hops.append({"hop": ttl, "ip": hop_ip, "avg_ms": ms_val, "loss": ""})
                    target_reached = True
                    break
                else:
                    # Timeout / Bintang
                    raw_hops.append({"hop": ttl, "ip": "*", "avg_ms": None, "loss": ""})

            if len(raw_hops) > 0:
                fallback_ok = True
        except Exception as ping_err:
            pass

        if not fallback_ok:
            raise HTTPException(503, f"Traceroute MikroTik gagal ({mt_err}) & fallback server-side timeout. Pastikan NET_RAW aktif.")


    enriched_hops = []
    seen_asns = []
    for hop in raw_hops:
        ip = hop.get("ip", "*")
        asn_info = await _ip_to_asn(ip, db) if ip != "*" else {}
        asn_num = asn_info.get("asn", 0)
        new_asn = asn_num and asn_num not in seen_asns
        if new_asn:
            seen_asns.append(asn_num)
        enriched_hops.append({
            **hop,
            "asn": asn_num,
            "asn_raw": asn_info.get("asn_raw", ""),
            "org": asn_info.get("org") or asn_info.get("isp", ""),
            "country": asn_info.get("country", ""),
            "city": asn_info.get("city", ""),
            "new_asn": new_asn,
        })

    upstream = next((h for h in enriched_hops if h.get("asn")), {})
    return {
        "mode": "broadband",
        "device_id": device_id,
        "target": target,
        "hops": enriched_hops,
        "total_hops": len(enriched_hops),
        "upstream_isp": upstream.get("org", "Unknown"),
        "upstream_asn": upstream.get("asn", 0),
        "upstream_country": upstream.get("country", ""),
        "path_asns": [
            {"asn": a, "org": next(
                (h["org"] for h in enriched_hops if h.get("asn") == a), ""
            )} for a in seen_asns
        ],
    }


# ─── Endpoint 4: Content Provider Latency Map ────────────────────────────────
@router.get("/intelligence/content-map")
async def content_map(
    device_id: str = Query(...),
    force: bool = Query(False),
    user=Depends(get_current_user),
):
    """
    Ping ke major content providers dari MikroTik.
    Return latency, packet loss, dan status per provider.
    Cache 15 menit. Gunakan ?force=true untuk bypass cache.
    """
    db = get_db()
    cache_key = f"content_map:{device_id}"
    if not force:
        cached = await cache_get(db, cache_key)
        if cached:
            return {**cached, "from_cache": True}

    dev = await db.devices.find_one({"id": device_id}, {"_id": 0})
    if not dev:
        raise HTTPException(404, "Device tidak ditemukan")

    api = get_api_client(dev)
    results = []

    for provider in CONTENT_PROVIDERS:
        ip = provider["ips"][0]
        latency_ms = None
        loss_pct = 100
        status = "offline"

        # ── Coba MikroTik API ping ──────────────────────────────────────────
        try:
            ping_result = await api.run("/tool/ping", {
                "address": ip, "count": "5", "interval": "0.2"
            })
            times = []
            rx = 0
            for entry in (ping_result or []):
                t = entry.get("time") or entry.get("avg", "")
                if t and str(t) not in ("timeout", ""):
                    try:
                        times.append(float(str(t).replace("ms", "").strip()))
                        rx += 1
                    except ValueError:
                        pass
            if times:
                latency_ms = round(sum(times) / len(times), 1)
                loss_pct = round((5 - rx) / 5 * 100)
                if loss_pct == 0:
                    status = "good" if latency_ms < 50 else "fair" if latency_ms < 150 else "poor"
                else:
                    status = "degraded"
        except Exception:
            pass

        # ── Fallback: server-side multi-port TCP probe ──────────────────────
        if status == "offline":
            import time as _t
            # Coba 3 metode: ICMP ping → TCP 443 → TCP 80 → TCP 53
            probe_success = False

            # Metode 1: ICMP ping (hanya jika NET_RAW tersedia)
            try:
                ping_proc = await asyncio.create_subprocess_exec(
                    "ping", "-c", "3", "-W", "2", "-q", ip,
                    stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
                )
                ping_out, _ = await asyncio.wait_for(ping_proc.communicate(), timeout=10)
                out_str = ping_out.decode(errors="replace")
                # Parse "rtt min/avg/max/mdev = X/Y/Z/W ms"
                rtt_m = re.search(r"rtt.+=\s*([\d.]+)/([\d.]+)", out_str)
                loss_m = re.search(r"(\d+)%\s+packet loss", out_str)
                if rtt_m:
                    latency_ms = round(float(rtt_m.group(2)), 1)
                    loss_pct   = int(loss_m.group(1)) if loss_m else 0
                    status     = "good" if latency_ms < 50 else "fair" if latency_ms < 150 else "poor"
                    if loss_pct > 0:
                        status = "degraded"
                    probe_success = True
            except Exception:
                pass

            # Metode 2: TCP multi-port (443 → 80 → 53)
            if not probe_success:
                for port in [443, 80, 53]:
                    try:
                        t0 = _t.monotonic()
                        reader, writer = await asyncio.wait_for(
                            asyncio.open_connection(ip, port),
                            timeout=4
                        )
                        writer.close()
                        try:
                            await writer.wait_closed()
                        except Exception:
                            pass
                        latency_ms = round((_t.monotonic() - t0) * 1000, 1)
                        loss_pct   = 0
                        status     = "good" if latency_ms < 50 else "fair" if latency_ms < 150 else "poor"
                        probe_success = True
                        break
                    except asyncio.TimeoutError:
                        continue
                    except OSError as e:
                        if hasattr(e, 'errno') and e.errno in (111, 61):  # ECONNREFUSED = host alive!
                            t_conn = round((_t.monotonic() - t0) * 1000, 1) if 't0' in dir() else 0
                            # Host responded (refused) → it's reachable
                            latency_ms = t_conn if t_conn > 0 else None
                            loss_pct   = 0
                            status     = "fair"
                            probe_success = True
                            break
                        continue
                    except Exception:
                        continue

        asn_info = await _ip_to_asn(ip, db)
        results.append({
            "name": provider["name"],
            "icon": provider["icon"],
            "ip": ip,
            "asn": provider["asn"],
            "asn_name": asn_info.get("org", ""),
            "latency_ms": latency_ms,
            "loss_pct": loss_pct,
            "status": status,
        })
        await asyncio.sleep(0.3)

    payload = {
        "mode": "content_map",
        "device_id": device_id,
        "providers": results,
        "good_count": sum(1 for r in results if r["status"] == "good"),
        "fair_count": sum(1 for r in results if r["status"] in ("fair", "poor")),
        "degraded_count": sum(1 for r in results if r["status"] == "degraded"),
        "offline_count": sum(1 for r in results if r["status"] == "offline"),
        "measured_at": datetime.now(timezone.utc).isoformat(),
    }
    await cache_set(db, cache_key, payload, ttl_seconds=900)
    return {**payload, "from_cache": False}


# ─── Endpoint 5: Internet Exchange Lookup ────────────────────────────────────
@router.get("/intelligence/ix-lookup")
async def ix_lookup(
    asn: int = Query(..., description="ASN number to look up"),
    user=Depends(get_current_user),
):
    """Lookup IX membership + ASN info dari PeeringDB dan BGPView."""
    db = get_db()
    asn_info = await _enrich_asn_bgpview(asn, db)
    pdb_info = await _fetch_peeringdb(asn, db)
    prefixes = await _enrich_asn_prefixes(asn, db)
    return {
        "asn": asn,
        "bgpview": asn_info,
        "peeringdb": pdb_info,
        "prefixes": prefixes,
        "ix_count": len(pdb_info.get("ix_list", [])),
    }
