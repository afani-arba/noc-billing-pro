# ══════════════════════════════════════════════════════════════════════
# mikrotik-bgp-setup.rsc — Konfigurasi BGP Peer di MikroTik
# Untuk digunakan dengan NOC Billing Pro — BGP Content Steering
# ══════════════════════════════════════════════════════════════════════
#
# CARA PAKAI:
#   1. Ganti SEMUA placeholder (VPS_IP, MY_ASN, dll) dengan nilai Anda
#   2. Upload file ini ke MikroTik via Files > Upload
#   3. Jalankan via Terminal: /import mikrotik-bgp-setup.rsc
#
# ATAU copy-paste baris per baris ke Winbox Terminal / SSH
#
# ══════════════════════════════════════════════════════════════════════
# PLACEHOLDER — WAJIB DIGANTI:
#   VPS_BGP_IP    = IP VPS tempat GoBGP berjalan (bukan IP container)
#   MIKROTIK_IP   = IP MikroTik yang dipakai sebagai BGP source
#   VPS_AS        = AS Number GoBGP (default: 65000, sesuai gobgpd.conf)
#   MIKROTIK_AS   = AS Number MikroTik (pilih bebas, misal: 65001)
# ══════════════════════════════════════════════════════════════════════

# ── 1. Aktifkan BGP Instance ──────────────────────────────────────────────────
/routing bgp instance
set default as=65001 router-id=MIKROTIK_IP

# ── 2. Tambah BGP Peer ke GoBGP (VPS) ────────────────────────────────────────
# MikroTik ROS v6
/routing bgp peer
add name=noc-billing-pro \
    remote-address=VPS_BGP_IP \
    remote-as=65000 \
    instance=default \
    multihop=yes \
    ttl=10 \
    update-source=MIKROTIK_IP \
    comment="NOC Billing Pro — BGP Content Steering"

# ── Untuk MikroTik ROS v7 (gunakan blok ini sebagai gantinya): ───────────────
# /routing bgp template
# set default as=65001
# /routing bgp connection
# add name=noc-billing-pro \
#     local.role=ebgp \
#     local.address=MIKROTIK_IP \
#     remote.address=VPS_BGP_IP/32 \
#     remote.as=65000 \
#     multihop=yes \
#     hold-time=180 \
#     connect=yes \
#     comment="NOC Billing Pro — BGP Content Steering"

# ── 3. Pastikan BGP routes diterima di routing table ─────────────────────────
# MikroTik akan menerima prefix yang diinject oleh NOC Billing Pro
# dan memasukkannya ke routing table secara otomatis.
# Tidak perlu filter tambahan — GoBGP sudah filter community per-peer.

# ── 4. Verifikasi (jalankan di terminal MikroTik setelah setup) ──────────────
# /routing bgp peer print               → status peer
# /routing bgp peer monitor [find]      → monitor BGP session live
# /ip route print where bgp             → lihat prefix yang diterima dari GoBGP
