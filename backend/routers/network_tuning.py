"""
NOC Billing Pro — Network Tuning Router
=========================================
API endpoints untuk 6 service tuning MikroTik:
  1. Smart Queue (SQM) Manager     — GET/POST /api/network-tuning/sqm
  2. Connection Tracking Optimizer — GET/POST /api/network-tuning/conntrack
  3. TCP MSS Clamping              — GET/POST /api/network-tuning/mss
  4. Raw Firewall (CPU Saver)      — GET/POST /api/network-tuning/raw-firewall
  5. Latency Monitor               — GET      /api/network-tuning/latency
  6. Interface Health Monitor      — GET      /api/network-tuning/interface-health

Mount prefix: /api/network-tuning
"""

from fastapi import APIRouter, Depends, HTTPException, Body
from pydantic import BaseModel
from typing import Optional
from datetime import datetime, timezone
import logging

from core.db import get_db
from core.auth import get_current_user, require_write
from mikrotik_api import get_api_client

logger = logging.getLogger("network_tuning")

router = APIRouter(prefix="/network-tuning", tags=["Network Tuning"])

NOC_COMMENT_PREFIX = "NOC-"

# ── Helper: ambil device dari DB ──────────────────────────────────────────────

async def _get_device(device_id: str) -> dict:
    """Ambil device document dari DB, raise 404 jika tidak ditemukan."""
    db = get_db()
    dev = await db.devices.find_one({"id": device_id})
    if not dev:
        raise HTTPException(404, f"Device '{device_id}' tidak ditemukan")
    return dev


# ═══════════════════════════════════════════════════════════════════════════════
# 1. SMART QUEUE (SQM) MANAGER
# ═══════════════════════════════════════════════════════════════════════════════

class SqmApplyRequest(BaseModel):
    device_id: str
    queue_type: str = "fq-codel"   # "fq-codel" atau "cake" (ROS 7.14+)


@router.get("/sqm/{device_id}")
async def get_sqm_status(device_id: str, user=Depends(get_current_user)):
    """Baca semua Simple Queue di router dan identifikasi queue type masing-masing."""
    dev = await _get_device(device_id)
    mt = get_api_client(dev)

    try:
        queues = await mt.list_simple_queues()
    except Exception as e:
        raise HTTPException(502, f"Gagal membaca queue dari router: {e}")

    result = []
    optimized_count = 0
    for q in queues:
        qt = q.get("queue", "default/default")
        is_optimal = "fq-codel" in qt.lower() or "cake" in qt.lower() or "sfq" in qt.lower()
        if is_optimal:
            optimized_count += 1
        result.append({
            "id": q.get(".id", ""),
            "name": q.get("name", ""),
            "target": q.get("target", ""),
            "max_limit": q.get("max-limit", ""),
            "queue_type": qt,
            "is_optimal": is_optimal,
            "disabled": q.get("disabled", "false") == "true",
        })

    return {
        "device_id": device_id,
        "device_name": dev.get("name", ""),
        "total_queues": len(result),
        "optimized_count": optimized_count,
        "queues": result,
    }


@router.post("/sqm/apply")
async def apply_sqm(body: SqmApplyRequest, user=Depends(require_write)):
    """
    Apply Smart Queue ke semua Simple Queue di router.
    Buat queue type custom jika belum ada, lalu update semua queue.
    """
    dev = await _get_device(body.device_id)
    mt = get_api_client(dev)
    qt_name = body.queue_type  # "fq-codel" or "cake"

    # Nama queue type upload/download
    up_name = f"noc-{qt_name}-up"
    down_name = f"noc-{qt_name}-down"

    try:
        # 1. Cek/buat queue type
        try:
            existing_types = await mt._async_req("GET", "queue/type")
            existing_names = {t.get("name", "") for t in existing_types} if isinstance(existing_types, list) else set()
        except Exception:
            existing_names = set()

        if down_name not in existing_names:
            try:
                await mt._async_req("PUT", "queue/type", {
                    "name": down_name,
                    "kind": qt_name,
                })
            except Exception as e:
                if "already" not in str(e).lower():
                    logger.warning(f"Gagal buat queue type {down_name}: {e}")

        if up_name not in existing_names:
            try:
                await mt._async_req("PUT", "queue/type", {
                    "name": up_name,
                    "kind": qt_name,
                })
            except Exception as e:
                if "already" not in str(e).lower():
                    logger.warning(f"Gagal buat queue type {up_name}: {e}")

        # 2. Update semua simple queue
        queues = await mt.list_simple_queues()
        updated = 0
        failed = 0
        queue_value = f"{up_name}/{down_name}"

        for q in queues:
            q_id = q.get(".id")
            if not q_id:
                continue
            current_qt = q.get("queue", "")
            if current_qt == queue_value:
                continue  # sudah optimal
            try:
                await mt.update_simple_queue(q_id, {"queue": queue_value})
                updated += 1
            except Exception as e:
                logger.warning(f"Gagal update queue {q.get('name')}: {e}")
                failed += 1

        return {
            "message": f"SQM {qt_name} berhasil diterapkan",
            "updated": updated,
            "failed": failed,
            "total": len(queues),
            "queue_type_applied": queue_value,
        }

    except Exception as e:
        raise HTTPException(502, f"Gagal menerapkan SQM: {e}")


# ═══════════════════════════════════════════════════════════════════════════════
# 2. CONNECTION TRACKING OPTIMIZER
# ═══════════════════════════════════════════════════════════════════════════════

class ConntrackOptimizeRequest(BaseModel):
    device_id: str
    max_entries: int = 65536
    tcp_established_timeout: str = "00:30:00"
    tcp_close_timeout: str = "00:00:10"
    udp_timeout: str = "00:00:30"


@router.get("/conntrack/{device_id}")
async def get_conntrack_status(device_id: str, user=Depends(get_current_user)):
    """Baca status connection tracking dari router."""
    dev = await _get_device(device_id)
    mt = get_api_client(dev)

    try:
        # Baca conntrack settings
        ct_settings = await mt._async_req("GET", "ip/firewall/connection/tracking")
        if isinstance(ct_settings, list):
            ct_settings = ct_settings[0] if ct_settings else {}

        # Hitung total koneksi aktif
        try:
            ct_count_resp = await mt._async_req("POST", "ip/firewall/connection/print", {
                ".query": ["count-only="]
            })
            if isinstance(ct_count_resp, dict):
                total_connections = int(ct_count_resp.get("ret", 0))
            else:
                # Fallback: ambil list dan count
                connections = await mt._async_req("GET", "ip/firewall/connection")
                total_connections = len(connections) if isinstance(connections, list) else 0
        except Exception:
            try:
                connections = await mt._async_req("GET", "ip/firewall/connection")
                total_connections = len(connections) if isinstance(connections, list) else 0
            except Exception:
                total_connections = 0

        max_entries = int(ct_settings.get("max-entries", 16384))
        usage_pct = round(total_connections / max_entries * 100, 1) if max_entries > 0 else 0

        severity = "ok"
        if usage_pct > 95:
            severity = "critical"
        elif usage_pct > 80:
            severity = "warning"

        return {
            "device_id": device_id,
            "device_name": dev.get("name", ""),
            "total_connections": total_connections,
            "max_entries": max_entries,
            "usage_percent": usage_pct,
            "severity": severity,
            "tcp_established_timeout": ct_settings.get("tcp-established-timeout", ""),
            "tcp_close_timeout": ct_settings.get("tcp-close-timeout", ""),
            "udp_timeout": ct_settings.get("udp-timeout", ""),
            "enabled": ct_settings.get("enabled", "auto"),
        }

    except Exception as e:
        raise HTTPException(502, f"Gagal membaca conntrack: {e}")


@router.post("/conntrack/optimize")
async def optimize_conntrack(body: ConntrackOptimizeRequest, user=Depends(require_write)):
    """Apply conntrack optimization ke router."""
    dev = await _get_device(body.device_id)
    mt = get_api_client(dev)

    try:
        await mt._async_req("POST", "ip/firewall/connection/tracking/set", {
            "max-entries": str(body.max_entries),
            "tcp-established-timeout": body.tcp_established_timeout,
            "tcp-close-timeout": body.tcp_close_timeout,
            "udp-timeout": body.udp_timeout,
        })
        return {
            "message": "Connection Tracking berhasil dioptimasi",
            "applied": {
                "max_entries": body.max_entries,
                "tcp_established_timeout": body.tcp_established_timeout,
                "tcp_close_timeout": body.tcp_close_timeout,
                "udp_timeout": body.udp_timeout,
            }
        }
    except Exception as e:
        raise HTTPException(502, f"Gagal mengoptimasi conntrack: {e}")


# ═══════════════════════════════════════════════════════════════════════════════
# 3. TCP MSS CLAMPING
# ═══════════════════════════════════════════════════════════════════════════════

MSS_COMMENT = "NOC-MSS-Clamp"


@router.get("/mss/{device_id}")
async def get_mss_status(device_id: str, user=Depends(get_current_user)):
    """Cek apakah MSS Clamping rule sudah ada di router."""
    dev = await _get_device(device_id)
    mt = get_api_client(dev)

    try:
        rules = await mt._async_req("GET", "ip/firewall/mangle")
        if not isinstance(rules, list):
            rules = []

        mss_rule = None
        for r in rules:
            if MSS_COMMENT in str(r.get("comment", "")):
                mss_rule = r
                break

        return {
            "device_id": device_id,
            "device_name": dev.get("name", ""),
            "applied": mss_rule is not None,
            "rule_id": mss_rule.get(".id", "") if mss_rule else "",
            "disabled": mss_rule.get("disabled", "false") == "true" if mss_rule else False,
        }

    except Exception as e:
        raise HTTPException(502, f"Gagal membaca mangle rules: {e}")


class MssToggleRequest(BaseModel):
    device_id: str
    enable: bool = True


@router.post("/mss/apply")
async def apply_mss(body: MssToggleRequest, user=Depends(require_write)):
    """Enable atau disable TCP MSS Clamping pada router."""
    dev = await _get_device(body.device_id)
    mt = get_api_client(dev)

    try:
        # Cek existing rule
        rules = await mt._async_req("GET", "ip/firewall/mangle")
        existing = None
        if isinstance(rules, list):
            for r in rules:
                if MSS_COMMENT in str(r.get("comment", "")):
                    existing = r
                    break

        if body.enable:
            if existing:
                # Sudah ada — pastikan enabled
                if existing.get("disabled", "false") == "true":
                    await mt._async_req("PATCH", f"ip/firewall/mangle/{existing['.id']}", {
                        "disabled": "false"
                    })
                    return {"message": "MSS Clamping rule sudah ada, berhasil di-enable kembali"}
                return {"message": "MSS Clamping sudah aktif"}
            else:
                # Buat rule baru
                await mt._async_req("PUT", "ip/firewall/mangle", {
                    "chain": "forward",
                    "protocol": "tcp",
                    "tcp-flags": "syn",
                    "action": "change-mss",
                    "new-mss": "clamp-to-pmtu",
                    "passthrough": "true",
                    "comment": MSS_COMMENT,
                })
                return {"message": "MSS Clamping berhasil diterapkan"}
        else:
            # Disable
            if existing:
                await mt._async_req("DELETE", f"ip/firewall/mangle/{existing['.id']}")
                return {"message": "MSS Clamping berhasil dihapus"}
            return {"message": "MSS Clamping belum diterapkan"}

    except Exception as e:
        raise HTTPException(502, f"Gagal menerapkan MSS: {e}")


# ═══════════════════════════════════════════════════════════════════════════════
# 4. RAW FIREWALL (CPU SAVER)
# ═══════════════════════════════════════════════════════════════════════════════

RAW_RULES = [
    {
        "id": "drop-invalid",
        "label": "Drop Invalid Packets",
        "config": {
            "chain": "prerouting",
            "connection-state": "invalid",
            "action": "drop",
            "comment": "NOC-RAW-DropInvalid",
        }
    },
    {
        "id": "drop-dns-attack",
        "label": "Drop External DNS Attack",
        "config": {
            "chain": "prerouting",
            "protocol": "udp",
            "dst-port": "53",
            "in-interface-list": "WAN",
            "action": "drop",
            "comment": "NOC-RAW-DropDNS",
        },
        "fallback_config": {
            "chain": "prerouting",
            "protocol": "udp",
            "dst-port": "53",
            "connection-state": "new",
            "action": "drop",
            "comment": "NOC-RAW-DropDNS",
        }
    },
    {
        "id": "icmp-limiter",
        "label": "ICMP Flood Limiter",
        "config": {
            "chain": "prerouting",
            "protocol": "icmp",
            "limit": "50/5s,5:packet",
            "action": "accept",
            "comment": "NOC-RAW-ICMPLimit",
        }
    },
    {
        "id": "drop-port-scanner",
        "label": "Drop Port Scanner",
        "config": {
            "chain": "prerouting",
            "protocol": "tcp",
            "tcp-flags": "fin,psh,urg,!syn,!rst,!ack",
            "action": "drop",
            "comment": "NOC-RAW-DropPortScan",
        }
    },
    {
        "id": "drop-bogon",
        "label": "Drop Bogon Source",
        "config": {
            "chain": "prerouting",
            "src-address": "0.0.0.0/8",
            "action": "drop",
            "comment": "NOC-RAW-DropBogon",
        }
    },
]


@router.get("/raw-firewall/{device_id}")
async def get_raw_firewall_status(device_id: str, user=Depends(get_current_user)):
    """Baca status Raw Firewall rules beserta counters."""
    dev = await _get_device(device_id)
    mt = get_api_client(dev)

    try:
        rules = await mt._async_req("GET", "ip/firewall/raw")
        if not isinstance(rules, list):
            rules = []

        # Ambil CPU usage
        resource = await mt.get_system_resource()
        cpu_load = resource.get("cpu-load", 0) if isinstance(resource, dict) else 0

        # Map existing rules
        existing_map = {}
        for r in rules:
            comment = str(r.get("comment", ""))
            if comment.startswith("NOC-RAW-"):
                existing_map[comment] = r

        result = []
        total_dropped = 0
        for rule_def in RAW_RULES:
            comment = rule_def["config"]["comment"]
            existing = existing_map.get(comment)
            packets = int(existing.get("packets", 0)) if existing else 0
            bts = int(existing.get("bytes", 0)) if existing else 0
            total_dropped += packets
            result.append({
                "id": rule_def["id"],
                "label": rule_def["label"],
                "applied": existing is not None,
                "disabled": existing.get("disabled", "false") == "true" if existing else False,
                "rule_id": existing.get(".id", "") if existing else "",
                "packets_dropped": packets,
                "bytes_dropped": bts,
            })

        return {
            "device_id": device_id,
            "device_name": dev.get("name", ""),
            "cpu_load": cpu_load,
            "total_packets_dropped": total_dropped,
            "rules": result,
        }

    except Exception as e:
        raise HTTPException(502, f"Gagal membaca raw firewall: {e}")


class RawFirewallRequest(BaseModel):
    device_id: str
    enable_all: bool = True


@router.post("/raw-firewall/apply")
async def apply_raw_firewall(body: RawFirewallRequest, user=Depends(require_write)):
    """Apply atau hapus Raw Firewall rules."""
    dev = await _get_device(body.device_id)
    mt = get_api_client(dev)

    try:
        rules = await mt._async_req("GET", "ip/firewall/raw")
        existing_comments = set()
        if isinstance(rules, list):
            for r in rules:
                c = str(r.get("comment", ""))
                if c.startswith("NOC-RAW-"):
                    existing_comments.add(c)
                    if not body.enable_all:
                        # Delete rule
                        try:
                            await mt._async_req("DELETE", f"ip/firewall/raw/{r['.id']}")
                        except Exception:
                            pass

        if not body.enable_all:
            return {"message": "Semua NOC Raw Firewall rules telah dihapus"}

        added = 0
        skipped = 0
        for rule_def in RAW_RULES:
            comment = rule_def["config"]["comment"]
            if comment in existing_comments:
                skipped += 1
                continue
            try:
                await mt._async_req("PUT", "ip/firewall/raw", rule_def["config"])
                added += 1
            except Exception as e:
                # Coba fallback config (misal jika in-interface-list tidak ada)
                if rule_def.get("fallback_config"):
                    try:
                        await mt._async_req("PUT", "ip/firewall/raw", rule_def["fallback_config"])
                        added += 1
                    except Exception:
                        logger.warning(f"Gagal apply rule {comment}: {e}")
                else:
                    logger.warning(f"Gagal apply rule {comment}: {e}")

        return {
            "message": f"Raw Firewall berhasil diterapkan",
            "added": added,
            "skipped": skipped,
        }

    except Exception as e:
        raise HTTPException(502, f"Gagal menerapkan Raw Firewall: {e}")


# ═══════════════════════════════════════════════════════════════════════════════
# 5. LATENCY MONITOR (read from MongoDB — data diisi oleh background service)
# ═══════════════════════════════════════════════════════════════════════════════

@router.get("/latency/{device_id}")
async def get_latency_data(device_id: str, limit: int = 100, user=Depends(get_current_user)):
    """Ambil data latency timeseries dari MongoDB."""
    db = get_db()
    docs = await db.latency_metrics.find(
        {"device_id": device_id},
        {"_id": 0}
    ).sort("timestamp", -1).limit(limit).to_list(limit)

    # Ambil latest summary
    latest = docs[0] if docs else {}

    return {
        "device_id": device_id,
        "latest": {
            "avg_rtt": latest.get("avg_rtt", 0),
            "max_rtt": latest.get("max_rtt", 0),
            "min_rtt": latest.get("min_rtt", 0),
            "jitter": latest.get("jitter", 0),
            "packet_loss": latest.get("packet_loss", 0),
            "gateway": latest.get("gateway", ""),
            "timestamp": latest.get("timestamp", ""),
        },
        "history": list(reversed(docs)),  # chronological order
    }


@router.get("/latency")
async def get_all_latency(user=Depends(get_current_user)):
    """Ambil latency terbaru semua device."""
    db = get_db()
    pipeline = [
        {"$sort": {"timestamp": -1}},
        {"$group": {
            "_id": {"device_id": "$device_id", "gateway": "$gateway"},
            "avg_rtt": {"$first": "$avg_rtt"},
            "max_rtt": {"$first": "$max_rtt"},
            "jitter": {"$first": "$jitter"},
            "packet_loss": {"$first": "$packet_loss"},
            "device_name": {"$first": "$device_name"},
            "timestamp": {"$first": "$timestamp"},
        }},
    ]
    docs = await db.latency_metrics.aggregate(pipeline).to_list(200)

    results = []
    for d in docs:
        severity = "ok"
        rtt = d.get("avg_rtt", 0)
        loss = d.get("packet_loss", 0)
        if loss > 5 or rtt > 80:
            severity = "critical"
        elif loss > 1 or rtt > 30:
            severity = "warning"

        results.append({
            "device_id": d["_id"]["device_id"],
            "device_name": d.get("device_name", ""),
            "gateway": d["_id"]["gateway"],
            "avg_rtt": rtt,
            "max_rtt": d.get("max_rtt", 0),
            "jitter": d.get("jitter", 0),
            "packet_loss": loss,
            "severity": severity,
            "timestamp": d.get("timestamp", ""),
        })

    return {"devices": results}


# ═══════════════════════════════════════════════════════════════════════════════
# 6. INTERFACE HEALTH MONITOR (read from MongoDB)
# ═══════════════════════════════════════════════════════════════════════════════

@router.get("/interface-health/{device_id}")
async def get_interface_health(device_id: str, user=Depends(get_current_user)):
    """Ambil data interface health dari MongoDB."""
    db = get_db()
    doc = await db.system_settings.find_one(
        {"_id": f"iface_health_{device_id}"},
        {"_id": 0}
    )

    if not doc:
        return {
            "device_id": device_id,
            "interfaces": [],
            "sfp": [],
            "alerts": [],
            "updated_at": "",
        }

    return doc


@router.get("/interface-health")
async def get_all_interface_health(user=Depends(get_current_user)):
    """Ambil interface health semua device."""
    db = get_db()
    docs = await db.system_settings.find(
        {"_id": {"$regex": "^iface_health_"}},
        {"_id": 0}
    ).to_list(100)

    return {"devices": docs}


# ═══════════════════════════════════════════════════════════════════════════════
# 7. QOS GAMING, DNS & PING (LIGHTWEIGHT)
# ═══════════════════════════════════════════════════════════════════════════════

QOS_COMMENT = "NOC-QoS-Priority"
QOS_MANGLE_RULES = [
    {
        "chain": "prerouting",
        "protocol": "icmp",
        "action": "mark-connection",
        "new-connection-mark": "noc_qos_conn",
        "passthrough": "yes",
        "comment": QOS_COMMENT,
    },
    {
        "chain": "prerouting",
        "protocol": "udp",
        "dst-port": "53",
        "action": "mark-connection",
        "new-connection-mark": "noc_qos_conn",
        "passthrough": "yes",
        "comment": QOS_COMMENT,
    },
    {
        "chain": "prerouting",
        "protocol": "tcp",
        "dst-port": "53",
        "action": "mark-connection",
        "new-connection-mark": "noc_qos_conn",
        "passthrough": "yes",
        "comment": QOS_COMMENT,
    },
    {
        # Common Games (Mobile Legends, PUBG, FreeFire, dll)
        "chain": "prerouting",
        "protocol": "udp",
        "dst-port": "5000-17500",
        "action": "mark-connection",
        "new-connection-mark": "noc_qos_conn",
        "passthrough": "yes",
        "comment": QOS_COMMENT,
    },
    {
        # Mobile Legends specific
        "chain": "prerouting",
        "protocol": "udp",
        "dst-port": "30000-30300",
        "action": "mark-connection",
        "new-connection-mark": "noc_qos_conn",
        "passthrough": "yes",
        "comment": QOS_COMMENT,
    },
    {
        # Mark Packet
        "chain": "prerouting",
        "connection-mark": "noc_qos_conn",
        "action": "mark-packet",
        "new-packet-mark": "noc_qos_pkt",
        "passthrough": "no",
        "comment": QOS_COMMENT,
    }
]

QOS_SIMPLE_QUEUE = {
    "name": "NOC-QoS-Games-DNS-Ping",
    "target": "0.0.0.0/0",
    "packet-marks": "noc_qos_pkt",
    "priority": "1/1",
    "max-limit": "100M/100M",
    "comment": QOS_COMMENT,
}


@router.get("/qos-priority/{device_id}")
async def get_qos_priority_status(device_id: str, user=Depends(get_current_user)):
    """Cek status Mangle dan Simple Queue untuk QoS Priority."""
    dev = await _get_device(device_id)
    mt = get_api_client(dev)

    try:
        # Cek Mangle
        mangles = await mt._async_req("GET", "ip/firewall/mangle")
        applied_mangle = False
        mangle_count = 0
        if isinstance(mangles, list):
            for m in mangles:
                if QOS_COMMENT in str(m.get("comment", "")):
                    applied_mangle = True
                    mangle_count += 1

        # Cek Simple Queue
        queues = await mt._async_req("GET", "queue/simple")
        applied_queue = False
        queue_id = ""
        disabled = False
        if isinstance(queues, list):
            for q in queues:
                if QOS_COMMENT in str(q.get("comment", "")) or q.get("name") == QOS_SIMPLE_QUEUE["name"]:
                    applied_queue = True
                    queue_id = q.get(".id", "")
                    disabled = q.get("disabled", "false") == "true"
                    break

        return {
            "device_id": device_id,
            "device_name": dev.get("name", ""),
            "applied": applied_mangle and applied_queue,
            "mangle_count": mangle_count,
            "queue_applied": applied_queue,
            "queue_id": queue_id,
            "disabled": disabled,
        }

    except Exception as e:
        raise HTTPException(502, f"Gagal membaca status QoS Priority: {e}")


class QosPriorityRequest(BaseModel):
    device_id: str
    enable: bool = True


@router.post("/qos-priority/apply")
async def apply_qos_priority(body: QosPriorityRequest, user=Depends(require_write)):
    """Enable atau Disable QoS Priority (Mangle + Queue) di router."""
    dev = await _get_device(body.device_id)
    mt = get_api_client(dev)

    try:
        # Get existing rules
        mangles = await mt._async_req("GET", "ip/firewall/mangle")
        queues = await mt._async_req("GET", "queue/simple")
        
        existing_mangles = [m for m in (mangles if isinstance(mangles, list) else []) if QOS_COMMENT in str(m.get("comment", ""))]
        existing_queues = [q for q in (queues if isinstance(queues, list) else []) if QOS_COMMENT in str(q.get("comment", "")) or q.get("name") == QOS_SIMPLE_QUEUE["name"]]

        if body.enable:
            # 1. Apply Mangle
            if len(existing_mangles) < len(QOS_MANGLE_RULES):
                # Hapus yang lama dulu jika tidak lengkap
                for m in existing_mangles:
                    try:
                        await mt._async_req("DELETE", f"ip/firewall/mangle/{m['.id']}")
                    except Exception: pass
                # Tambah baru
                for r in QOS_MANGLE_RULES:
                    await mt._async_req("PUT", "ip/firewall/mangle", r)
            elif existing_mangles and existing_mangles[0].get("disabled", "false") == "true":
                # Enable jika disable
                for m in existing_mangles:
                    await mt._async_req("PATCH", f"ip/firewall/mangle/{m['.id']}", {"disabled": "false"})

            # 2. Apply Simple Queue
            if not existing_queues:
                # Tambah baru dan berusaha letakkan di paling atas jika bisa
                await mt._async_req("PUT", "queue/simple", QOS_SIMPLE_QUEUE)
            elif existing_queues[0].get("disabled", "false") == "true":
                await mt._async_req("PATCH", f"queue/simple/{existing_queues[0]['.id']}", {"disabled": "false"})

            return {"message": "QoS Priority (Gaming & Ping) berhasil diaktifkan. Pastikan posisi Queue berada di urutan paling atas (di atas PPPoE user)!"}
        
        else:
            # Disable / Remove
            for m in existing_mangles:
                await mt._async_req("DELETE", f"ip/firewall/mangle/{m['.id']}")
            for q in existing_queues:
                await mt._async_req("DELETE", f"queue/simple/{q['.id']}")

            return {"message": "QoS Priority berhasil dihapus"}

    except Exception as e:
        raise HTTPException(502, f"Gagal menerapkan QoS Priority: {e}")
