"""
apply_radius_fix.py — Skrip Sapu Bersih RADIUS NOC Billing Pro
═══════════════════════════════════════════════════════════════════════════════
Jalankan SEKALI untuk memperbaiki semua router MikroTik yang terdaftar:

1. Hapus SEMUA entri RADIUS lama (yang duplikat/kotor)
2. Pasang 1 entri RADIUS baru: service=hotspot,ppp + timeout=3s
3. Aktifkan CoA incoming listener di port 3799
4. Aktifkan PPP AAA use-radius + interim-update=5 menit

Cara pakai (dari dalam container backend):

    docker exec -it noc-billing-backend python apply_radius_fix.py

Atau dari luar container:

    docker exec noc-billing-backend python /app/apply_radius_fix.py

═══════════════════════════════════════════════════════════════════════════════
"""

import asyncio
import logging
import os
import sys

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger("apply_radius_fix")


async def main():
    # ── Koneksi ke MongoDB ─────────────────────────────────────────────────────
    from motor.motor_asyncio import AsyncIOMotorClient

    mongo_url = os.getenv("MONGO_URL", "mongodb://mongodb:27017")
    db_name   = os.getenv("MONGO_DB", "noc_billing")
    client    = AsyncIOMotorClient(mongo_url)
    db        = client[db_name]

    logger.info(f"Terhubung ke MongoDB: {mongo_url}/{db_name}")

    # ── Ambil IP server (RADIUS server IP yang perlu didaftarkan di MikroTik) ──
    radius_host = os.getenv("RADIUS_HOST", "")
    if not radius_host:
        # Coba deteksi dari hotspot_settings
        hs = await db.hotspot_settings.find_one({})
        radius_host = (hs or {}).get("radius_host", "") if hs else ""
    if not radius_host:
        logger.error("RADIUS_HOST tidak ditemukan! Set via env: RADIUS_HOST=<IP_server>")
        return

    logger.info(f"RADIUS Server IP (Billing): {radius_host}")

    # ── Ambil semua device ─────────────────────────────────────────────────────
    devices = await db.devices.find({}).to_list(1000)
    logger.info(f"Ditemukan {len(devices)} device")

    # ── Import mikrotik_api (tambahkan path /app jika perlu) ──────────────────
    sys.path.insert(0, "/app")
    from mikrotik_api import get_api_client

    results = []

    for device in devices:
        name   = device.get("name", device.get("ip_address", "unknown"))
        ip     = device.get("ip_address", "")
        secret = device.get("radius_secret") or device.get("hotspot_secret", "testing123")

        logger.info(f"\n{'='*60}")
        logger.info(f"🔧 Proses: {name} ({ip})")
        logger.info(f"   Secret: {'*' * len(secret)}")

        if not ip:
            logger.warning(f"   ⚠️  Lewati: IP kosong")
            results.append({"device": name, "status": "skip", "reason": "IP kosong"})
            continue

        try:
            mt = get_api_client(device)

            # Test koneksi dulu
            test = await mt.test_connection()
            if not test.get("success"):
                logger.warning(f"   ❌ Koneksi gagal: {test.get('error')}")
                results.append({"device": name, "status": "fail", "reason": test.get("error")})
                continue

            logger.info(f"   ✅ Koneksi OK: {test.get('identity', name)}")

            # Langkah 1: Cek RADIUS lama sebelum purge
            existing = await mt.list_radius_clients()
            logger.info(f"   📋 RADIUS entries sekarang: {len(existing)}")
            for r in existing:
                logger.info(f"      - addr={r.get('address')} svc={r.get('service')} timeout={r.get('timeout', 'N/A')}")

            # Langkah 2: Purge + reset RADIUS
            logger.info(f"   🔄 Purge + reset RADIUS...")
            purge = await mt.purge_and_reset_radius(radius_host, secret)
            for step in purge.get("steps", []):
                logger.info(f"   {step}")

            # Langkah 3: Aktifkan CoA incoming
            logger.info(f"   🔄 Aktifkan CoA incoming port 3799...")
            coa = await mt.enable_radius_incoming()
            logger.info(f"   {'✅' if coa.get('success') else '⚠️'} CoA: {coa.get('msg') or coa.get('error')}")

            # Langkah 4: Aktifkan PPP AAA use-radius + interim-update
            logger.info(f"   🔄 Set PPP AAA use-radius + interim-update=5min...")
            try:
                pppoe_profile = device.get("pppoe_profile", "pppoe-billing")
                result = await mt.setup_hotspot_radius(
                    radius_ip    = radius_host,
                    secret       = secret,
                    pppoe_profile= pppoe_profile,
                )
                for step in result.get("steps", []):
                    logger.info(f"   {step}")
            except Exception as e:
                logger.warning(f"   ⚠️  setup_hotspot_radius error (non-fatal): {e}")

            # Verifikasi akhir
            after = await mt.list_radius_clients()
            check = await mt.check_radius_enabled()
            logger.info(f"\n   📊 Verifikasi akhir:")
            logger.info(f"   - RADIUS entries: {len(after)} (harusnya = 1)")
            for r in after:
                logger.info(f"     addr={r.get('address')} svc={r.get('service')} timeout={r.get('timeout','?')}")
            logger.info(f"   - CoA incoming aktif: {check.get('coa_incoming_active', '?')}")
            logger.info(f"   - Hotspot use-radius: {check.get('radius_enabled', '?')}")

            status = "ok" if len(after) == 1 else "partial"
            results.append({
                "device":       name,
                "status":       status,
                "radius_count": len(after),
                "coa_active":   check.get("coa_incoming_active"),
            })

        except Exception as e:
            logger.error(f"   ❌ Error pada {name}: {e}")
            results.append({"device": name, "status": "error", "reason": str(e)})

    # ── Ringkasan ──────────────────────────────────────────────────────────────
    logger.info(f"\n{'='*60}")
    logger.info("📋 RINGKASAN HASIL:")
    ok     = [r for r in results if r["status"] == "ok"]
    fail   = [r for r in results if r["status"] in ("fail", "error")]
    skip   = [r for r in results if r["status"] == "skip"]
    logger.info(f"   ✅ Berhasil : {len(ok)}")
    logger.info(f"   ❌ Gagal    : {len(fail)}")
    logger.info(f"   ⏭  Lewati   : {len(skip)}")
    for r in results:
        icon = "✅" if r["status"] == "ok" else ("❌" if r["status"] in ("fail","error") else "⏭")
        logger.info(f"   {icon} {r['device']}: {r['status']}")

    logger.info("\nSelesai. Semua router telah dikonfigurasi ulang.")
    client.close()


if __name__ == "__main__":
    asyncio.run(main())
