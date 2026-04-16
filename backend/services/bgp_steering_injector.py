"""
BGP Steering Injector Service — NOC Sentinel v3
================================================
Background daemon yang:
1. Saat startup, langsung inject semua active policy (tidak tunggu 30 menit)
2. Listen ke event_queue untuk trigger inject on-demand saat toggle
3. Setiap 30 menit refresh prefix (ASN / DNS)
4. Inject prefix ke GoBGP di HOST Ubuntu via nsenter
5. Update counter di MongoDB agar UI "Prefix Aktif" menyala
"""
import asyncio
import logging
import socket
import re
import httpx
from datetime import datetime, timezone, timedelta
from typing import List, Optional, Set

from core.db import get_db

logger = logging.getLogger("bgp_steering_injector")

# Queue untuk trigger on-demand inject dari toggle endpoint
_inject_trigger: asyncio.Queue = asyncio.Queue()


def trigger_inject():
    """Dipanggil oleh toggle endpoint agar inject langsung berjalan tanpa tunggu 30 menit."""
    try:
        _inject_trigger.put_nowait("refresh")
    except asyncio.QueueFull:
        pass


async def resolve_domain_to_ips(domain: str) -> List[str]:
    """Resolve A record untuk domain menjadi list IP Address secara asinkron."""
    loop = asyncio.get_running_loop()
    try:
        clean_domain = domain.replace("\\.", ".")
        _hostname, _aliases, ipaddrlist = await loop.run_in_executor(
            None, socket.gethostbyname_ex, clean_domain
        )
        return ipaddrlist
    except Exception:
        return []


async def fetch_asn_prefixes(asn: int) -> List[str]:
    """Tarik daftar prefix IPv4 dari BGPView (fallback ke RIPEstat)."""
    headers = {"User-Agent": "NOC-Sentinel/3.0 BGP-Injector (+https://github.com/afani-arba)"}
    prefixes: List[str] = []

    # — Percobaan 1: BGPView ─────────────────────────────────────────
    try:
        async with httpx.AsyncClient(timeout=15.0, headers=headers) as client:
            resp = await client.get(f"https://api.bgpview.io/asn/{asn}/prefixes")
            if resp.status_code == 200:
                data = resp.json().get("data", {})
                ipv4 = data.get("ipv4_prefixes", [])
                prefixes = [p["prefix"] for p in ipv4 if p.get("prefix")]
                if prefixes:
                    logger.info(f"[ASN {asn}] BGPView: {len(prefixes)} prefix ditemukan")
                    return prefixes
            else:
                logger.warning(f"[ASN {asn}] BGPView HTTP {resp.status_code}")
    except Exception as e:
        logger.warning(f"[ASN {asn}] BGPView gagal: {e} — Beralih ke RIPEstat")

    # — Percobaan 2: RIPEstat ────────────────────────────────────────
    try:
        async with httpx.AsyncClient(timeout=20.0, headers=headers) as client:
            resp = await client.get(
                f"https://stat.ripe.net/data/announced-prefixes/data.json?resource={asn}"
            )
            if resp.status_code == 200:
                data = resp.json().get("data", {})
                anns = data.get("prefixes", [])
                prefixes = [p["prefix"] for p in anns if p.get("prefix")]
                if prefixes:
                    logger.info(f"[ASN {asn}] RIPEstat: {len(prefixes)} prefix ditemukan")
                    return prefixes
            else:
                logger.error(f"[ASN {asn}] RIPEstat HTTP {resp.status_code}")
    except Exception as e:
        logger.error(f"[ASN {asn}] RIPEstat gagal: {e}")

    return prefixes


async def fetch_domain_prefixes(regex_pattern: str) -> List[str]:
    """Ekstrak domain dari Regex Pattern lalu DNS-resolve ke daftar /32 prefix."""
    if not regex_pattern:
        return []
    clean = regex_pattern.replace("\\.", ".")
    # Ambil domain yang kredibel: minimal 1 titik, huruf/angka/dash saja
    domains = list(set(re.findall(r'[a-zA-Z0-9-]+\.[a-zA-Z0-9.-]+', clean)))
    # Buang yang terlalu pendek atau hanya angka
    domains = [d for d in domains if len(d) > 4 and not d.replace(".", "").isdigit()]
    if not domains:
        return []
    logger.info(f"DNS resolve {len(domains)} domain dari regex...")
    tasks = [resolve_domain_to_ips(d) for d in domains]
    results = await asyncio.gather(*tasks, return_exceptions=True)
    ips: Set[str] = set()
    for r in results:
        if isinstance(r, list):
            ips.update(r)
    return [f"{ip}/32" for ip in ips]


async def inject_to_gobgp(prefix: str, nexthop: str, community: Optional[str] = None) -> bool:
    """
    Inject satu prefix ke GoBGP di HOST Ubuntu via nsenter.

    Community dipakai sebagai TAG per-peer:
      Format: <LOCAL_AS>:<last_octet_peer>
      Contoh: 65000:252 → hanya untuk peer 10.254.254.252 (Aripin)
               65000:251 → hanya untuk peer 10.254.254.251 (Niki)

    GoBGP menggunakan community-based export policy di config-nya untuk
    memfilter prefix ke masing-masing peer.
    """
    cmd = [
        "nsenter", "-t", "1", "-m", "-u", "-i", "-n", "-p", "--",
        "/usr/local/bin/gobgp", "global", "rib", "add",
        prefix, "nexthop", nexthop
    ]
    if community:
        cmd.extend(["community", community])

    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=5.0)
        if proc.returncode != 0:
            stderr_msg = stderr.decode().strip()
            if stderr_msg:
                logger.debug(f"gobgp add {prefix}: {stderr_msg}")
        return proc.returncode == 0
    except asyncio.TimeoutError:
        logger.warning(f"Timeout injecting {prefix}")
        return False
    except FileNotFoundError:
        logger.error("nsenter tidak ditemukan! Pastikan container berjalan dengan pid: host dan privileged: true")
        return False
    except Exception as e:
        logger.error(f"inject_to_gobgp error: {e}")
        return False


async def _run_gobgp_cmd(args: list) -> tuple[bool, str]:
    """Helper menjalankan gobgp CLI via nsenter, return (success, output)."""
    cmd = ["nsenter", "-t", "1", "-m", "-u", "-i", "-n", "-p", "--",
           "/usr/local/bin/gobgp"] + args
    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=10.0)
        output = (stdout + stderr).decode().strip()
        return proc.returncode == 0, output
    except Exception as e:
        return False, str(e)


async def ensure_gobgp_community_policy(peers: list[dict], local_as: int = 65000) -> bool:
    """
    Pastikan GoBGP memiliki export policy per-peer berbasis community.
    Dipanggil saat sync peers agar filter otomatis terpasang.

    Untuk setiap peer dengan neighbor_ip, buat:
      - community-set  tag-for-<last_octet>  = ["<local_as>:<last_octet>"]
      - policy         peer-<last_octet>-export yang accept community tsb
      - assign policy ke neighbor

    Catatan: GoBGP v3 hanya mendukung per-peer policy di route-server mode.
    Cara ini menggunakan gobgp CLI untuk tambah policy definition secara
    dinamis, tidak butuh service restart.
    """
    success = True
    for peer in peers:
        ip = peer.get("neighbor_ip", "")
        if not ip:
            continue
        last_octet = ip.split(".")[-1]
        community_val = f"{local_as}:{last_octet}"
        community_set_name = f"tag-for-{last_octet}"
        policy_name = f"peer-{last_octet}-export"

        # 1. Buat community-set
        ok, out = await _run_gobgp_cmd([
            "defined-set", "add", "community", community_set_name, community_val
        ])
        if not ok and "already exists" not in out.lower():
            logger.warning(f"[policy] Gagal buat community-set {community_set_name}: {out}")

        # 2. Buat policy definition
        ok, out = await _run_gobgp_cmd([
            "policy", "add", policy_name,
            "--community", community_set_name
        ])
        if not ok and "already exists" not in out.lower():
            logger.debug(f"[policy] Policy {policy_name}: {out}")

        logger.info(
            f"[policy] Peer {ip}: community={community_val}, policy={policy_name} "
            f"(filter dikonfigurasi via GoBGP config file)"
        )

    return success


async def run_inject_cycle():
    """Satu siklus inject: baca semua active policy → fetch prefix → inject ke GoBGP → update DB."""
    db = get_db()

    # Ambil catalog ASN (diinline agar tidak circular import)
    CATALOG_ASN = {
        "YouTube": 15169, "Google": 15169,
        "Netflix": 2906,
        "TikTok": 396986,
        "Facebook": 32934, "Instagram": 32934, "WhatsApp": 32934,
        "Telegram": 62041,
        "Cloudflare": 13335,
        "Shopee": 45102, "Mobile Legends": 45102,
        "Tokopedia": 10208,
        "Steam": 32590,
        "Akamai": 20940,
        "AWS": 16509,
        "Zoom": 3356,
        "Indihome/Telkom": 7713,
        "Biznet": 17451,
    }

    # Ambil semua active policy
    policies = await db.bgp_steering_policies.find({"enabled": True}, {"_id": 0}).to_list(100)
    if not policies:
        logger.info("Tidak ada BGP Steering policy yang aktif.")
        return

    # Ambil platform regex dari DB (untuk Judol/Dewasa/Custom)
    platform_docs = await db.peering_platforms.find({}, {"_id": 0}).to_list(100)
    regex_map = {d.get("name", ""): d.get("regex_pattern", "") for d in platform_docs}

    for policy in policies:
        pid = policy.get("id", "")
        platform_name = policy.get("platform_name", "")
        gateway_ip = policy.get("gateway_ip", "")
        target_peer = policy.get("target_peer", "").strip()
        custom_prefixes = policy.get("custom_prefixes", [])

        # ── Community Tagging Logic ──
        # Format: LOCAL_AS:LastOctet (misal 10.254.254.252 -> 65000:252)
        community = None
        if target_peer:
            addr_parts = target_peer.split(".")
            if len(addr_parts) == 4:
                # Try to get LOCAL_AS from DB settings
                local_as = 65000 # Default fallback
                try:
                    bgp_settings = await db.settings.find_one({"key": "bgp_config"})
                    if bgp_settings and bgp_settings.get("local_as"):
                        local_as = int(bgp_settings["local_as"])
                except Exception:
                    pass
                community = f"{local_as}:{addr_parts[-1]}"

        if not gateway_ip:
            logger.warning(f"[{platform_name}] Gateway IP kosong, skip.")
            continue

        all_prefixes: Set[str] = set(custom_prefixes)

        # Scenario 1: Platform ber-ASN resmi
        asn = CATALOG_ASN.get(platform_name, 0)
        if asn > 0:
            asn_prefs = await fetch_asn_prefixes(asn)
            all_prefixes.update(asn_prefs)

        # Scenario 2: Domain-based (Judol/Dewasa/Custom)
        elif platform_name in regex_map and regex_map[platform_name]:
            domain_prefs = await fetch_domain_prefixes(regex_map[platform_name])
            all_prefixes.update(domain_prefs)

        # Scenario 3: Live DNS dari Peering Eye (Otomatis menyedot trafik titipan seperti GGC/FNA)
        time_limit = (datetime.now(timezone.utc) - timedelta(hours=12)).isoformat()
        cursor = db.peering_eye_stats.find(
            {"platform": platform_name, "timestamp": {"$gte": time_limit}},
            {"_id": 0, "top_domains": 1}
        )
        peering_domains = set()
        async for doc in cursor:
            td = doc.get("top_domains", {})
            if isinstance(td, dict):
                peering_domains.update(td.keys())
                
        if peering_domains:
            logger.info(f"[{platform_name}] Memproses {len(peering_domains)} Live Domain dari Peering Eye...")
            domain_list = list(peering_domains)
            batch_size = 50
            for i in range(0, len(domain_list), batch_size):
                chunk = domain_list[i:i+batch_size]
                tasks = [resolve_domain_to_ips(d) for d in chunk]
                # resolve_domain_to_ips mengembalikan List[str], jadi results adalah List[List[str]]
                results = await asyncio.gather(*tasks, return_exceptions=True)
                for r in results:
                    if isinstance(r, list):
                        all_prefixes.update([f"{ip}/32" for ip in r])
                await asyncio.sleep(0.05)  # Beri nafas ke local UDP resolver

        total = len(all_prefixes)
        if total == 0:
            logger.warning(f"[{platform_name}] 0 prefix ditemukan, skip inject.")
            continue

        logger.info(f"[{platform_name}] Injecting {total} prefix ke GoBGP nexthop={gateway_ip}...")

        # Inject ke GoBGP dalam batch
        success = 0
        BATCH = 50
        prefs_list = list(all_prefixes)
        for i in range(0, len(prefs_list), BATCH):
            chunk = prefs_list[i:i+BATCH]
            results = await asyncio.gather(*[inject_to_gobgp(p, gateway_ip, community) for p in chunk])
            success += sum(results)
            await asyncio.sleep(0.2)  # Nafas kecil antar batch

        logger.info(f"[{platform_name}] Selesai: {success}/{total} prefix berhasil diinjeksi.")

        # Update MongoDB status agar UI prefix-count menyala
        now_iso = datetime.now(timezone.utc).isoformat()
        await db.bgp_steering_status.delete_many({"policy_id": pid})

        # Insert status docs dalam batch
        CHUNK = 500
        status_docs = [
            {"policy_id": pid, "prefix": p, "nexthop": gateway_ip, "injected_at": now_iso}
            for p in all_prefixes
        ]
        for i in range(0, len(status_docs), CHUNK):
            await db.bgp_steering_status.insert_many(status_docs[i:i+CHUNK])

        # Update policy counter
        await db.bgp_steering_policies.update_one(
            {"id": pid},
            {"$set": {"injected_prefix_count": success, "last_inject_at": now_iso}}
        )

    logger.info("Siklus inject selesai.")


async def bgp_injector_loop():
    """Main loop BGP Injector: inject saat startup, on-demand trigger, dan setiap 30 menit."""
    logger.info("BGP Steering Injector Service dimulai.")

    # Inject LANGSUNG saat startup (tidak tunggu)
    await asyncio.sleep(5)  # Tunggu sebentar agar DB connection stabil
    try:
        await run_inject_cycle()
    except Exception as e:
        logger.error(f"Startup inject error: {e}")

    REFRESH_INTERVAL = 1800  # 30 menit

    while True:
        try:
            # Tunggu trigger on-demand ATAU timeout 30 menit
            try:
                await asyncio.wait_for(_inject_trigger.get(), timeout=REFRESH_INTERVAL)
                logger.info("BGP Injector: triggered on-demand, menjalankan inject cycle...")
            except asyncio.TimeoutError:
                logger.info("BGP Injector: 30 menit berlalu, refresh prefix...")

            await run_inject_cycle()

        except Exception as e:
            logger.error(f"BGP Injector loop error: {e}")
            await asyncio.sleep(60)
