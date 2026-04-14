import asyncio
import logging
import json
import os
import time
from typing import Dict, Any

from core.db import get_db

logger = logging.getLogger(__name__)

# ── Safe import pysnmp — backend tetap berjalan meski pysnmp tidak terinstall ──
# pysnmp-lextudio: drop-in replacement pysnmp yang kompatibel Python 3.11+
try:
    from pysnmp.hlapi.asyncio import (
        SnmpEngine, CommunityData, UdpTransportTarget,
        ContextData, ObjectType, ObjectIdentity,
        getCmd, nextCmd, walkCmd
    )
    SNMP_AVAILABLE = True
    logger.info("pysnmp tersedia — SNMP Hybrid Monitoring aktif")
except ImportError:
    SNMP_AVAILABLE = False
    # Stub classes agar kode di bawah tidak error saat pysnmp tidak ada
    SnmpEngine = CommunityData = UdpTransportTarget = None
    ContextData = ObjectType = ObjectIdentity = None
    getCmd = nextCmd = walkCmd = None
    logger.warning("pysnmp tidak terinstall — SNMP Poller dinonaktifkan. "
                   "Install dengan: pip install pysnmp-lextudio")

SNMP_POLL_INTERVAL = int(os.environ.get("SNMP_POLL_INTERVAL", 90))
SNMP_PORT = 161
SNMP_TIMEOUT = 2.0
SNMP_RETRIES = 1

# OIDs
OID_IF_NAME = ObjectType(ObjectIdentity('1.3.6.1.2.1.31.1.1.1.1')) if SNMP_AVAILABLE else None
# ifHCInOctets (.1.3.6.1.2.1.31.1.1.1.6)
OID_HC_IN = '1.3.6.1.2.1.31.1.1.1.6'
# ifHCOutOctets (.1.3.6.1.2.1.31.1.1.1.10)
OID_HC_OUT = '1.3.6.1.2.1.31.1.1.1.10'

# ── PENTING: MikroTik CPU OID mengembalikan nilai dalam PER-MILLE (0-1000) BUKAN PERSEN ──
# OID .14988.1.1.3.10.0 = mtxrHlCpuLoad — nilai 500 = 50% CPU load
# HARUS dibagi 10 untuk mendapatkan persentase yang benar!
OID_MTIK_CPU = '1.3.6.1.4.1.14988.1.1.3.10.0'

# OID CPU Standar (HOST-RESOURCES-MIB) untuk RouterOS v7+ yang kehilangan mtxrHlCpuLoad
# Akan di-query sampai 4 core. Jika multi-core, kita rata-ratakan.
OID_HR_CPU1 = '1.3.6.1.2.1.25.3.3.1.2.1'
OID_HR_CPU2 = '1.3.6.1.2.1.25.3.3.1.2.2'
OID_HR_CPU3 = '1.3.6.1.2.1.25.3.3.1.2.3'
OID_HR_CPU4 = '1.3.6.1.2.1.25.3.3.1.2.4'

# HOST-RESOURCES-MIB RAM (Index 65536 = Main Memory di RouterOS)
# hrStorageAllocationUnits: ukuran block (biasanya 1024 bytes)
# hrStorageSize: jumlah block TOTAL
# hrStorageUsed: jumlah block TERPAKAI
# RAM% = (hrStorageUsed / hrStorageSize) * 100  [units sudah sama, tidak perlu konversi]
OID_RAM_ALLOC = '1.3.6.1.2.1.25.2.3.1.4.65536'   # hrStorageAllocationUnits
OID_RAM_SIZE  = '1.3.6.1.2.1.25.2.3.1.5.65536'   # hrStorageSize (dalam allocation units)
OID_RAM_USED  = '1.3.6.1.2.1.25.2.3.1.6.65536'   # hrStorageUsed (dalam allocation units)

# Global cache for ifIndex mapping: { device_id: { if_name: ifIndex } }
_iface_cache: Dict[str, Dict[str, int]] = {}
# Global cache for previous counter: { device_id: { ifIndex: { 'in': val, 'out': val, 'ts': time } } }
_counter_cache: Dict[str, Dict[int, Dict[str, Any]]] = {}


async def _fetch_iface_map(snmp_engine: SnmpEngine, ip: str, community: str) -> Dict[str, int]:
    """Mengambil pemetaan ifName -> ifIndex via SNMP."""
    if_map = {}
    
    try:
        iterator = walkCmd(
            snmp_engine,
            CommunityData(community, mpModel=1),  # v2c
            UdpTransportTarget((ip, SNMP_PORT), timeout=SNMP_TIMEOUT, retries=SNMP_RETRIES),
            ContextData(),
            OID_IF_NAME,
            lexicographicMode=False
        )
        
        async for errorIndication, errorStatus, errorIndex, varBinds in iterator:
            if errorIndication or errorStatus:
                break
            for varBind in varBinds:
                oid, val = varBind
                # OID is 1.3.6.1.2.1.31.1.1.1.1.<ifIndex>
                ifindex = int(str(oid).split('.')[-1])
                ifname = str(val)
                if_map[ifname] = ifindex
    except Exception as e:
        logger.debug(f"[SNMP] Gagal fetch iface map for {ip}: {e}")
        
    return if_map

async def poll_device_bandwidth(snmp_engine: SnmpEngine, device: dict, db):
    did = device["id"]
    ip  = device.get("ip_address", "").split(":")[0]

    # Baca community dari device DB, fallback ke noc-sentinel lalu public
    db_community = (device.get("snmp_community") or "").strip()
    communities_to_try = []
    if db_community:
        communities_to_try.append(db_community)
    if "noc-sentinel" not in communities_to_try:
        communities_to_try.append("noc-sentinel")
    if "public" not in communities_to_try:
        communities_to_try.append("public")

    # Cari community yang berhasil fetch iface map
    community = None
    if did not in _iface_cache or not _iface_cache[did]:
        for c in communities_to_try:
            if_map = await _fetch_iface_map(snmp_engine, ip, c)
            if if_map:
                community = c
                _iface_cache[did] = if_map
                # Simpan community yang berhasil ke DB (sekali saja)
                if c != db_community:
                    await db.devices.update_one(
                        {"id": did},
                        {"$set": {"snmp_community": c}}
                    )
                break
        if not community:
            logger.debug(f"[SNMP] Semua community gagal untuk {ip}")
            return
    else:
        # Gunakan community yang sudah terbukti berhasil
        community = db_community or communities_to_try[0]

    if_map = _iface_cache[did]
    target_ifaces = set()
    
    # Ambil ISP dan OUT interfaces yang mau ditampilkan grafiknya
    isp_ifaces = device.get("isp_interfaces", [])
    out_ifaces = device.get("out_interfaces", [])
    
    for ifname in (isp_ifaces + out_ifaces):
        if ifname in if_map:
            target_ifaces.add((ifname, if_map[ifname]))
            
    if not target_ifaces:
        # Jika tidak ada spesifik, kita track bridge atau sfp atau ether yang aktif
        for ifname, ifidx in if_map.items():
            if not any(ifname.lower().startswith(x) for x in ["<", "pppoe", "l2tp", "sstp", "ovpn", "lo"]):
                target_ifaces.add((ifname, ifidx))

    # 2. Polling ifHCInOctets & ifHCOutOctets untuk target ifaces
    # Build ordered list dengan mapping eksplisit oid → (ifidx, direction)
    oid_request_list = []    # list of (oid_str, ifidx, direction)
    oids_to_fetch = []
    for _, ifidx in target_ifaces:
        oid_in  = f"{OID_HC_IN}.{ifidx}"
        oid_out = f"{OID_HC_OUT}.{ifidx}"
        oids_to_fetch.append(ObjectType(ObjectIdentity(oid_in)))
        oids_to_fetch.append(ObjectType(ObjectIdentity(oid_out)))
        oid_request_list.append((oid_in,  ifidx, "in"))
        oid_request_list.append((oid_out, ifidx, "out"))

    if not oids_to_fetch:
        return

    # Add extra OIDs for CPU and RAM for single-shot GET
    # Order HARUS tetap: cpu_mt, cpu_hr1-4, ram_alloc, ram_size, ram_used (index-based parsing)
    oid_cpu       = OID_MTIK_CPU
    oid_cpu_hr1   = OID_HR_CPU1
    oid_cpu_hr2   = OID_HR_CPU2
    oid_cpu_hr3   = OID_HR_CPU3
    oid_cpu_hr4   = OID_HR_CPU4
    oid_ram_alloc = OID_RAM_ALLOC
    oid_ram_size  = OID_RAM_SIZE
    oid_ram_used  = OID_RAM_USED
    
    oids_to_fetch.append(ObjectType(ObjectIdentity(oid_cpu)))
    oids_to_fetch.append(ObjectType(ObjectIdentity(oid_cpu_hr1)))
    oids_to_fetch.append(ObjectType(ObjectIdentity(oid_cpu_hr2)))
    oids_to_fetch.append(ObjectType(ObjectIdentity(oid_cpu_hr3)))
    oids_to_fetch.append(ObjectType(ObjectIdentity(oid_cpu_hr4)))
    oids_to_fetch.append(ObjectType(ObjectIdentity(oid_ram_alloc)))
    oids_to_fetch.append(ObjectType(ObjectIdentity(oid_ram_size)))
    oids_to_fetch.append(ObjectType(ObjectIdentity(oid_ram_used)))

    # Fetch device details early untuk memeriksa isp_interfaces (Fix Graphic Inversion)
    dev_doc = await db.devices.find_one(
        {"id": did},
        {"_id": 0, "isp_interfaces": 1, "out_interfaces": 1, "ping_avg": 1, "ping_jitter": 1, "cpu_load": 1}
    )
    isp_ifaces = []
    if dev_doc:
        isp_ifaces = dev_doc.get("isp_interfaces", [])

    try:
        iterator = getCmd(
            snmp_engine,
            CommunityData(community, mpModel=1),
            UdpTransportTarget((ip, SNMP_PORT), timeout=SNMP_TIMEOUT, retries=SNMP_RETRIES),
            ContextData(),
            *oids_to_fetch
        )

        errorIndication, errorStatus, errorIndex, varBinds = await iterator
        if errorIndication or errorStatus:
            logger.debug(f"[SNMP] getCmd error for {ip}: {errorIndication or errorStatus}")
            return

        now = time.time()
        if did not in _counter_cache:
            _counter_cache[did] = {}

        bw_data    = {}
        idx_results = {}
        for name, ifidx in target_ifaces:
            idx_results[ifidx] = {"name": name, "in": 0, "out": 0}

        cpu_mt_raw = 0   # raw value dari MikroTik SNMP (per-mille)
        cpu_hr_raw = []  # tampung list core load dari OID standar (ROS 7+)
        ram_alloc = 0  # hrStorageAllocationUnits
        ram_sz   = 0   # hrStorageSize
        ram_us   = 0   # hrStorageUsed

        # ── Index-based parsing ─────────
        n_iface_oids = len(oid_request_list)
        for i, (oid_obj, val) in enumerate(varBinds):
            if i < n_iface_oids:
                # Bagian interface
                _, ifidx, direction = oid_request_list[i]
                if ifidx in idx_results:
                    try:
                        raw = int(val)
                        if raw >= 0:
                            idx_results[ifidx][direction] = raw
                    except Exception:
                        pass
            else:
                # Bagian OID Tambahan (8 OID khusus)
                # 0=cpu_mt, 1=hr1, 2=hr2, 3=hr3, 4=hr4, 5=ram_alloc, 6=ram_sz, 7=ram_us
                extra_idx = i - n_iface_oids
                try:
                    raw = int(val)
                    if extra_idx == 0:
                        cpu_mt_raw = raw
                    elif 1 <= extra_idx <= 4:
                        cpu_hr_raw.append(raw)
                    elif extra_idx == 5:
                        ram_alloc = raw
                    elif extra_idx == 6:
                        ram_sz    = raw
                    elif extra_idx == 7:
                        ram_us    = raw
                except Exception:
                    pass

        # ── CPU NORMALIZATION (Fix CPU Hilang di ROS 7+) ──
        cpu_val = 0
        cpu_hr_raw = [c for c in cpu_hr_raw if c >= 0]
        
        # OID Mikrotik (.10.0) menghasilkan per-mille
        if cpu_mt_raw > 100:
            cpu_val = cpu_mt_raw // 10
        elif cpu_mt_raw > 0:
            cpu_val = cpu_mt_raw
        elif len(cpu_hr_raw) > 0:
            # Jika CPU Mikrotik gagal/hilang (0), fallback ke OID Standar MIB-II
            # Rata-ratakan beban dari seluruh core yang berhasil di-query
            cpu_val = sum(cpu_hr_raw) // len(cpu_hr_raw)
            
        cpu_val = min(cpu_val, 100)


        for ifidx, res in idx_results.items():
            old_data = _counter_cache[did].get(ifidx)
            _counter_cache[did][ifidx] = {
                "in":  res["in"],
                "out": res["out"],
                "ts":  now
            }

            if old_data:
                elapsed  = max(now - old_data["ts"], 1.0)
                diff_in  = max(res["in"]  - old_data["in"],  0)
                diff_out = max(res["out"] - old_data["out"], 0)

                # PENTING: Fix Bug Grafik Terbalik (Dynamically mapping RX/TX)
                # Secara Default, Winbox "rx" (SNMP IN) = Traffic MASUK ke interface router
                # Winbox "tx" (SNMP OUT) = Traffic KELUAR dari interface router
                rx_val = int((diff_in  * 8) / elapsed)
                tx_val = int((diff_out * 8) / elapsed)

                if rx_val > 40_000_000_000: rx_val = 0
                if tx_val > 40_000_000_000: tx_val = 0

                is_isp = res["name"] in isp_ifaces
                if is_isp:
                    # PERSPEKTIF WAN/INTERNET
                    # Download Pelanggan = Paketan turun dari Inet MASUK (RX) ke interface WAN
                    # Upload Pelanggan   = Paketan dari Pelanggan KELUAR (TX) via WAN ke Inet
                    dl_bps = rx_val
                    ul_bps = tx_val
                else:
                    # PERSPEKTIF LAN/CLIENT / BRIDGE
                    # Download Pelanggan = Router MENGIRIM / KELUAR (TX) paketan Inet ke arah Client
                    # Upload Pelanggan   = Client MENGIRIM / MASUK (RX) paketan ke port Router
                    dl_bps = tx_val
                    ul_bps = rx_val

                bw_data[res["name"]] = {
                    "download_bps": dl_bps,
                    "upload_bps":   ul_bps,
                    "rx_bps":       rx_val,    # Nilai murni Winbox RX
                    "tx_bps":       tx_val,    # Nilai murni Winbox TX
                    "status":       "up",
                    "source":       "snmp"
                }

        if bw_data:
            from datetime import datetime, timezone
            now_iso = datetime.now(timezone.utc).isoformat()

            # ── FIX BUG RAM PERSENTASE ──────────────────────────────────────
            # hrStorageSize dan hrStorageUsed keduanya dalam allocation units yang SAMA.
            # RAM% = (ram_used_units / ram_total_units) * 100
            # TIDAK perlu menggunakan allocation unit size — pembagian langsung sudah correct.
            # Contoh: ram_sz=524288, ram_us=262144 → 262144/524288*100 = 50%
            ram_pct = 0
            if ram_sz > 0:
                pct_raw = (ram_us * 100) // ram_sz  # integer division untuk efisiensi
                ram_pct = min(int(pct_raw), 100)     # clamp 0-100%, tidak boleh > 100

            # ── BUG 1 FIX: Ambil ping_ms & jitter_ms dari device document ──────────
            # polling.py menyimpan ping_avg & ping_jitter ke device document.
            # SNMP poller harus ikut sertakan ke traffic_history agar stat cards
            # di dashboard bisa menampilkan data ping/jitter yang valid.
            dev_doc_fallback = dev_doc or {}
            isp_ifaces_list = dev_doc_fallback.get("isp_interfaces") or []
            out_ifaces_list = dev_doc_fallback.get("out_interfaces")  or []
            # Baca nilai ping/jitter terakhir yang disimpan oleh polling.py
            ping_ms   = float(dev_doc_fallback.get("ping_avg",    0) or 0)
            jitter_ms = float(dev_doc_fallback.get("ping_jitter", 0) or 0)
            # Jika CPU = 0, fallback lagi ke rest API call terakhir (ROS 7 fail-safe ekstrim)
            if cpu_val == 0:
                cpu_val = min(int(dev_doc_fallback.get("cpu_load", 0) or 0), 100)

            # isp_bandwidth: hanya interface yang terdeteksi sebagai WAN/ISP
            isp_bandwidth = {k: v for k, v in bw_data.items() if k in isp_ifaces_list} if isp_ifaces_list else {}
            out_bandwidth = {k: v for k, v in bw_data.items() if k in out_ifaces_list} if out_ifaces_list else {}

            # Jika isp_interfaces belum dikonfigurasi, auto-pick interface dengan traffic tertinggi
            if not isp_bandwidth and bw_data:
                VIRTUAL_PREFIXES = (
                    "bridge", "vlan", "lo", "loopback", "ovpn", "pppoe-", "pptp",
                    "l2tp", "eoip", "gre", "sstp", "VPN", "veth", "docker", "sit", "tun", "tap",
                )
                phys = {
                    k: v for k, v in bw_data.items()
                    if not any(k.lower().startswith(p) for p in VIRTUAL_PREFIXES)
                }
                if phys:
                    best_k = max(phys, key=lambda k: phys[k].get("download_bps", 0) + phys[k].get("upload_bps", 0))
                    isp_bandwidth = {best_k: phys[best_k]}

            history_doc = {
                "device_id":       did,
                "timestamp":       now_iso,
                "bandwidth":       bw_data,
                "isp_bandwidth":   isp_bandwidth,
                "out_bandwidth":   out_bandwidth,
                "cpu":             cpu_val,
                "memory_percent":  ram_pct,
                # BUG 1 FIX: sertakan ping_ms & jitter_ms ke traffic_history
                "ping_ms":         ping_ms,
                "jitter_ms":       jitter_ms,
                "poll_source":     "snmp"
            }

            # Update last_traffic in devices collection
            await db.devices.update_one(
                {"id": did},
                {"$set": {
                    "cpu_load":      cpu_val,
                    "memory_usage":  ram_pct,
                    "last_traffic": {
                        "timestamp":      now_iso,
                        "bandwidth":      bw_data,
                        "isp_bandwidth":  isp_bandwidth,
                        "out_bandwidth":  out_bandwidth,
                        "cpu":            cpu_val,
                        "memory_percent": ram_pct,
                        # BUG 1 FIX: sertakan juga ke last_traffic
                        "ping_ms":        ping_ms,
                        "jitter_ms":      jitter_ms,
                        "poll_source":    "snmp"
                    }
                }}
            )

            # Save history for dashboard graphics
            await db.traffic_history.insert_one(history_doc)


    except Exception as e:
        logger.debug(f"[SNMP] Polling error for {ip}: {e}")


async def snmp_polling_loop():
    """Background Daemon Loop untuk polling SNMP (Setiap 5 detik)."""
    if not SNMP_AVAILABLE:
        logger.warning("[SNMP] Daemon tidak dimulai: pysnmp tidak terinstall.")
        return
    logger.info(f"[SNMP] Daemon started (interval {SNMP_POLL_INTERVAL} detik)")
    snmp_engine = SnmpEngine()
    
    while True:
        start_time = time.time()
        try:
            db = get_db()
            
            # Cari perangkat online — fetch juga snmp_community dari DB
            devices = await db.devices.find(
                {"status": "online"},
                {"_id": 0, "id": 1, "ip_address": 1,
                 "isp_interfaces": 1, "out_interfaces": 1, "snmp_community": 1}
            ).to_list(None)
            
            if devices:
                # Concurrent poll over all online routers with progressive jitter (staggered)
                # Maksimal 15 perangkat dikerjakan serentak agar tidak membuat burst traffic switch
                sem = asyncio.Semaphore(15)
                async def polled_with_jitter(idx, d):
                    await asyncio.sleep(idx * 0.5) # Jeda setengah detik antar perangkat
                    async with sem:
                        return await poll_device_bandwidth(snmp_engine, d, db)

                tasks = [polled_with_jitter(i, d) for i, d in enumerate(devices)]
                await asyncio.gather(*tasks, return_exceptions=True)
                
        except Exception as e:
            logger.error(f"[SNMP] Kesalahan kritis di loop: {e}")
            
        try:
            cfg = await db.system_settings.find_one({"_id": "snmp_config"})
            dynamic_interval = cfg.get("interval", SNMP_POLL_INTERVAL) if cfg else SNMP_POLL_INTERVAL
        except Exception:
            dynamic_interval = SNMP_POLL_INTERVAL

        elapsed = time.time() - start_time
        sleep_time = max(dynamic_interval - elapsed, 1.0)
        await asyncio.sleep(sleep_time)

async def start_snmp_poller():
    if not SNMP_AVAILABLE:
        logger.warning("SNMP Poller tidak jalan: pysnmp tidak terinstall.")
        return
    await snmp_polling_loop()

async def get_device_snmp_info(host: str, community: str, timeout: int = 5) -> dict:
    """Mengambil informasi perangkat menggunakan pysnmp untuk test-snmp api."""
    if not SNMP_AVAILABLE:
        return {"snmp_reachable": False, "error": "pysnmp tidak terinstall"}
    snmp_engine = SnmpEngine()
    
    oids = [
        ObjectType(ObjectIdentity('1.3.6.1.2.1.1.1.0')),  # sysDescr
        ObjectType(ObjectIdentity('1.3.6.1.2.1.1.3.0')),  # sysUpTime
        ObjectType(ObjectIdentity('1.3.6.1.2.1.1.5.0'))   # sysName
    ]
    
    try:
        iterator = getCmd(
            snmp_engine,
            CommunityData(community, mpModel=1),
            UdpTransportTarget((host, SNMP_PORT), timeout=timeout, retries=1),
            ContextData(),
            *oids
        )
        errorIndication, errorStatus, errorIndex, varBinds = await iterator
        
        if errorIndication or errorStatus:
            return {"snmp_reachable": False}
            
        info = {"snmp_reachable": True}
        for oid, val in varBinds:
            oid_str = str(oid)
            if '1.3.6.1.2.1.1.1.0' in oid_str:
                info["sys_descr"] = str(val)
                if "RouterOS" in str(val):
                    parts = str(val).split()
                    if parts and parts[-1][0].isdigit():
                        info["ros_version"] = parts[-1]
            elif '1.3.6.1.2.1.1.3.0' in oid_str:
                try: info["uptime_s"] = int(val) // 100
                except: info["uptime_s"] = 0
            elif '1.3.6.1.2.1.1.5.0' in oid_str:
                info["sys_name"] = str(val)
                
        if_map = await _fetch_iface_map(snmp_engine, host, community)
        info["interface_count"] = len(if_map)
        return info
    except Exception as e:
        logger.debug(f"[SNMP] get info failed for {host}: {e}")
        return {"snmp_reachable": False}
