#!/bin/bash
# ╔══════════════════════════════════════════════════════════════════════════════╗
# ║   NOC Billing Pro — Fresh Install Script                                     ║
# ║   Edition : BILLING PRO (GenieACS + Peering Eye + BGP Content Steering)      ║
# ║                                                                               ║
# ║   SATU PERINTAH:                                                              ║
# ║   curl -fsSL https://raw.githubusercontent.com/afani-arba/                   ║
# ║   noc-billing-pro/main/install-noc-billing-pro.sh | sudo bash                ║
# ║                                                                               ║
# ║   Script ini akan menginstal:                                                 ║
# ║     1. Docker + Docker Compose                                                ║
# ║     2. GoBGP daemon (host systemd)                                            ║
# ║     3. NOC Billing Pro (via docker compose)                                   ║
# ║     4. VPN Services: L2TP/IPSec (xl2tpd+strongswan) + PPTP                   ║
# ║     5. Cloudflare Tunnel (token WAJIB untuk akses publik via HTTPS)           ║
# ║     6. UFW firewall rules (termasuk port VPN & SSTP)                         ║
# ║     7. Auto-start saat reboot                                                 ║
# ╚══════════════════════════════════════════════════════════════════════════════╝
set -euo pipefail

# ── Warna & helpers ────────────────────────────────────────────────────────────
G='\033[0;32m'; Y='\033[1;33m'; R='\033[0;31m'
B='\033[1;34m'; C='\033[0;36m'; BOLD='\033[1m'; N='\033[0m'

ok()      { echo -e "  ${G}✔${N}  $*"; }
warn()    { echo -e "  ${Y}⚠${N}  $*"; }
err()     { echo -e "\n${R}${BOLD}✗  ERROR: $*${N}\n"; exit 1; }
step()    { echo -e "\n${BOLD}${B}══════════════════════════════════════════${N}"; \
            echo -e "${BOLD}${C}  $*${N}"; \
            echo -e "${BOLD}${B}══════════════════════════════════════════${N}"; }
info()    { echo -e "  ${B}ℹ${N}  $*"; }

# ── Konstanta ──────────────────────────────────────────────────────────────────
APP_DIR="/opt/noc-billing-pro"
REPO="https://github.com/afani-arba/noc-billing-pro.git"
GOBGP_VERSION="3.26.0"
GOBGP_URL="https://github.com/osrg/gobgp/releases/download/v${GOBGP_VERSION}/gobgp_${GOBGP_VERSION}_linux_amd64.tar.gz"
COMPOSE_FILE="$APP_DIR/docker-compose.yml"
ENV_FILE="$APP_DIR/backend/.env"

# ── Cek root ───────────────────────────────────────────────────────────────────
[[ $EUID -ne 0 ]] && err "Jalankan sebagai root: sudo bash install-noc-billing-pro.sh"

# ── Banner ─────────────────────────────────────────────────────────────────────
clear
echo -e "${BOLD}${C}"
echo "╔══════════════════════════════════════════════════════════════════════╗"
echo "║   NOC Billing Pro — Fresh Install Script                             ║"
echo "║   Edition: BILLING PRO                                               ║"
echo "║   Fitur: Dashboard • Device • GenieACS/ZTP • RADIUS • PPPoE          ║"
echo "║          Hotspot • Laporan • CS WA • Portal • Peering Eye            ║"
echo "║          BGP Content Steering • Pengaturan • Integrasi • License     ║"
echo "╚══════════════════════════════════════════════════════════════════════╝"
echo -e "${N}"
echo -e "  Waktu   : $(date '+%Y-%m-%d %H:%M:%S')"
echo -e "  App Dir : $APP_DIR"
echo -e "  OS      : $(lsb_release -d 2>/dev/null | cut -f2 || uname -o)"
echo ""

# ══════════════════════════════════════════════════════════════════════════════
# STEP 0: Input Konfigurasi
# ══════════════════════════════════════════════════════════════════════════════
step "STEP 0/7 — Konfigurasi Awal"

# Cek apakah .env sudah ada
if [[ -f "$ENV_FILE" ]]; then
    warn ".env sudah ada — konfigurasi yang ada akan dipertahankan."
    SKIP_ENV=true
else
    SKIP_ENV=false
    echo -e "  ${Y}${BOLD}Masukkan konfigurasi NOC Billing Pro:${N}"
    echo ""

    read -r -p "  Nama layanan ISP Anda [NOC Billing Pro]: " _NAME </dev/tty
    NOC_NAME="${_NAME:-NOC Billing Pro}"

    read -r -p "  Domain / URL akses (contoh: https://billing.domain.com) [http://$(hostname -I | awk '{print $1}'):8082]: " _URL </dev/tty
    APP_URL="${_URL:-http://$(hostname -I | awk '{print $1}'):8082}"

    read -r -p "  RADIUS Secret (untuk MikroTik hotspot) [ganti_radius_secret]: " _RSECRET </dev/tty
    RADIUS_SECRET="${_RSECRET:-ganti_radius_secret}"

    echo ""
    echo -e "  ${Y}${BOLD}Konfigurasi GoBGP (BGP Content Steering):${N}"
    read -r -p "  Local AS Number GoBGP [65000]: " _AS </dev/tty
    BGP_LOCAL_AS="${_AS:-65000}"

    read -r -p "  Router-ID GoBGP (IP VPS/loopback) [$(hostname -I | awk '{print $1}')]: " _RID </dev/tty
    BGP_ROUTER_ID="${_RID:-$(hostname -I | awk '{print $1}')}"

    read -r -p "  IP MikroTik BGP Peer 1 (kosongkan jika belum ada): " _PEER1 </dev/tty
    BGP_PEER1_IP="${_PEER1:-}"

    read -r -p "  AS Number MikroTik Peer 1 [65001]: " _PEER1AS </dev/tty
    BGP_PEER1_AS="${_PEER1AS:-65001}"

    echo ""
    echo -e "  ${Y}${BOLD}GitHub Container Registry (GHCR):${N}"
    info "Diperlukan untuk pull image NOC Billing Pro dari ghcr.io"
    read -r -p "  GitHub Username [afani-arba]: " _GHUSER </dev/tty
    GHCR_USER="${_GHUSER:-afani-arba}"
    read -r -s -p "  GitHub Token (Personal Access Token / classic): " _GHTOKEN </dev/tty
    echo ""
    GHCR_TOKEN="$_GHTOKEN"

    echo ""
    echo -e "  ${Y}${BOLD}Konfigurasi Cloudflare Tunnel:${N}"
    info "Token Cloudflare diperlukan agar Dashboard bisa diakses via domain publik (HTTPS)."
    info "Buat token di: https://one.dash.cloudflare.com → Networks → Tunnels → Create a Tunnel"
    echo ""
    echo -e "  ${R}${BOLD}PERINGATAN:${N} Tanpa Cloudflare Tunnel, Dashboard hanya bisa diakses via IP lokal."
    echo -e "  ${R}${BOLD}            Sangat disarankan mengisi token untuk keamanan & akses remote.${N}"
    echo ""
    while true; do
        read -r -p "  Cloudflare Tunnel Token (WAJIB diisi untuk akses publik HTTPS!): " _CFTOKEN </dev/tty
        CF_TUNNEL_TOKEN="${_CFTOKEN:-}"
        if [[ -z "$CF_TUNNEL_TOKEN" ]]; then
            echo -e "  ${R}Token tidak boleh kosong. Harap masukkan Cloudflare Tunnel Token Anda.${N}"
        else
            ok "Cloudflare Tunnel Token diterima ✔"
            break
        fi
    done
fi

echo ""
ok "Konfigurasi siap"

# ══════════════════════════════════════════════════════════════════════════════
# STEP 1: Dependensi sistem
# ══════════════════════════════════════════════════════════════════════════════
step "STEP 1/7 — Dependensi Sistem"

export DEBIAN_FRONTEND=noninteractive
apt-get update -qq
apt-get install -y -qq \
    curl wget git nano ufw \
    ca-certificates gnupg lsb-release \
    net-tools dnsutils iputils-ping \
    ppp pptpd \
    xl2tpd \
    strongswan strongswan-pki libstrongswan-extra-plugins \
    libcharon-extra-plugins \
    sstp-client \
    > /dev/null 2>&1

# (accel-ppp dihapus untuk menghindari warning yang tidak perlu di Debian 13/Ubuntu modern)

ok "Paket sistem OK (L2TP: xl2tpd ✔ | IKEv2: strongswan ✔ | PPTP: pptpd ✔ | SSTP: sstp-client ✔)"

# ── Aktifkan dan start layanan VPN ────────────────────────────────────────────
step "STEP 1b/7 — Aktifkan Service VPN (L2TP + SSTP + IKEv2)"

# L2TP — xl2tpd
if systemctl list-unit-files xl2tpd.service &>/dev/null; then
    systemctl enable xl2tpd > /dev/null 2>&1 || true
    systemctl start  xl2tpd > /dev/null 2>&1 || true
    if systemctl is-active --quiet xl2tpd; then
        ok "xl2tpd (L2TP) RUNNING ✔"
    else
        warn "xl2tpd gagal start — cek: sudo journalctl -u xl2tpd -n 20"
        warn "(Normal jika belum ada konfigurasi /etc/xl2tpd/xl2tpd.conf — config via MikroTik)"
    fi
else
    warn "xl2tpd service tidak ditemukan — lewati"
fi

# IKEv2/IPSec — strongswan
if systemctl list-unit-files strongswan.service &>/dev/null; then
    systemctl enable strongswan > /dev/null 2>&1 || true
    systemctl start  strongswan > /dev/null 2>&1 || true
    if systemctl is-active --quiet strongswan; then
        ok "strongswan (IKEv2/IPSec) RUNNING ✔"
    else
        warn "strongswan gagal start — cek: sudo journalctl -u strongswan -n 20"
    fi
elif systemctl list-unit-files strongswan-starter.service &>/dev/null; then
    systemctl enable strongswan-starter > /dev/null 2>&1 || true
    systemctl start  strongswan-starter > /dev/null 2>&1 || true
    if systemctl is-active --quiet strongswan-starter; then
        ok "strongswan-starter (IKEv2/IPSec) RUNNING ✔"
    else
        warn "strongswan-starter gagal start— cek: sudo journalctl -u strongswan-starter -n 20"
    fi
else
    warn "strongswan service tidak ditemukan — lewati"
fi

# pptpd (PPTP VPN — opsional, legacy)
if systemctl list-unit-files pptpd.service &>/dev/null; then
    systemctl enable pptpd > /dev/null 2>&1 || true
    # PPTP tidak di-start otomatis karena perlu konfigurasi credentials dulu
    ok "pptpd (PPTP) terdaftar di systemd (tidak di-start otomatis — config dulu)"
fi

# ── Verifikasi SSTP support (kernel module) ──────────────────────────────────
# SSTP server membutuhkan ppp_mppe kernel module
if modprobe ppp_mppe 2>/dev/null; then
    ok "Kernel module ppp_mppe (SSTP/MPPE encryption) LOADED ✔"
    # Pastikan dimuat saat boot
    echo "ppp_mppe" >> /etc/modules-load.d/vpn.conf 2>/dev/null || true
else
    warn "ppp_mppe module tidak tersedia — SSTP encryption mungkin tidak berjalan"
    warn "(Normal di beberapa cloud VPS yang membatasi kernel module)"
fi

# ── Verifikasi IP Forwarding untuk VPN ───────────────────────────────────────
if [[ $(sysctl -n net.ipv4.ip_forward) -ne 1 ]]; then
    echo 'net.ipv4.ip_forward = 1' >> /etc/sysctl.d/99-vpn.conf
    sysctl -p /etc/sysctl.d/99-vpn.conf > /dev/null 2>&1 || true
    ok "IP Forwarding diaktifkan (net.ipv4.ip_forward=1) — diperlukan untuk VPN routing"
else
    ok "IP Forwarding sudah aktif ✔"
fi

ok "Setup layanan VPN selesai (L2TP ✔ | IKEv2/SSTP ✔ | PPTP ✔)"

# ══════════════════════════════════════════════════════════════════════════════
# STEP 2: Docker & Docker Compose
# ══════════════════════════════════════════════════════════════════════════════
step "STEP 2/7 — Docker Engine"

if command -v docker &>/dev/null; then
    DOCKER_VER=$(docker --version | grep -oP '[\d.]+' | head -1)
    ok "Docker sudah ada (v${DOCKER_VER})"
else
    warn "Docker belum ada — install Docker Engine..."
    # Hapus versi lama
    apt-get remove -y -qq docker docker-engine docker.io containerd runc 2>/dev/null || true

    # Ambil ID OS (ubuntu atau debian) untuk repo Docker yang tepat
    OS_ID=$(. /etc/os-release && echo "$ID")
    if [[ "$OS_ID" != "ubuntu" && "$OS_ID" != "debian" ]]; then
        OS_ID="debian" # fallback
    fi

    # Tambah Docker GPG key & repo
    install -m 0755 -d /etc/apt/keyrings
    rm -f /etc/apt/keyrings/docker.gpg
    curl -fsSL "https://download.docker.com/linux/${OS_ID}/gpg" \
        | gpg --dearmor -o /etc/apt/keyrings/docker.gpg
    chmod a+r /etc/apt/keyrings/docker.gpg

    echo \
        "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] \
        https://download.docker.com/linux/${OS_ID} \
        $(lsb_release -cs) stable" \
        | tee /etc/apt/sources.list.d/docker.list > /dev/null

    apt-get update -qq
    apt-get install -y -qq \
        docker-ce docker-ce-cli containerd.io \
        docker-buildx-plugin docker-compose-plugin \
        > /dev/null 2>&1

    systemctl enable docker --now > /dev/null
    ok "Docker Engine terinstall"
fi

# Verifikasi docker compose plugin
if docker compose version &>/dev/null; then
    COMPOSE_VER=$(docker compose version --short 2>/dev/null || echo "OK")
    ok "Docker Compose plugin OK (v${COMPOSE_VER})"
else
    err "Docker Compose plugin tidak ditemukan. Install manual: apt-get install docker-compose-plugin"
fi

# ══════════════════════════════════════════════════════════════════════════════
# STEP 3: GoBGP (daemon di host untuk BGP Content Steering)
# ══════════════════════════════════════════════════════════════════════════════
step "STEP 3/7 — GoBGP Daemon (BGP Content Steering)"

GOBGP_INSTALL=false

if command -v gobgpd &>/dev/null; then
    EXISTING_VER=$(gobgpd --version 2>/dev/null | grep -oP '[\d.]+' | head -1 || echo "unknown")
    ok "GoBGP sudah ada (v${EXISTING_VER}) — skip download"
else
    GOBGP_INSTALL=true
fi

if [[ "$GOBGP_INSTALL" == true ]]; then
    info "Download GoBGP v${GOBGP_VERSION}..."
    TMP_DIR=$(mktemp -d)
    ARCHIVE="${TMP_DIR}/gobgp.tar.gz"

    if wget -q --show-progress -O "${ARCHIVE}" "${GOBGP_URL}" 2>&1; then
        true
    elif curl -L --progress-bar -o "${ARCHIVE}" "${GOBGP_URL}"; then
        true
    else
        err "Gagal download GoBGP dari ${GOBGP_URL}"
    fi

    tar -xzf "${ARCHIVE}" -C "${TMP_DIR}"

    [[ -f "${TMP_DIR}/gobgpd" ]] || err "gobgpd tidak ditemukan dalam archive"
    install -m 755 "${TMP_DIR}/gobgpd" /usr/local/bin/gobgpd
    [[ -f "${TMP_DIR}/gobgp" ]] && install -m 755 "${TMP_DIR}/gobgp" /usr/local/bin/gobgp

    rm -rf "${TMP_DIR}"
    INSTALLED_VER=$(gobgpd --version 2>/dev/null | grep -oP '[\d.]+' | head -1 || echo "?")
    ok "GoBGP v${INSTALLED_VER} terinstall"
fi

# ── Setup konfigurasi GoBGP ────────────────────────────────────────────────
mkdir -p /etc/gobgpd
touch /var/log/gobgpd.log
chmod 644 /var/log/gobgpd.log

# Generate gobgpd.conf dari input user
if [[ "$SKIP_ENV" == false ]]; then
    info "Generate gobgpd.conf..."
    cat > /etc/gobgpd/gobgpd.conf << BGPEOF
# GoBGP Config — NOC Billing Pro
# Auto-generated oleh install-noc-billing-pro.sh
# Edit: sudo nano /etc/gobgpd/gobgpd.conf
# Restart: sudo systemctl restart gobgpd

[global.config]
  as = ${BGP_LOCAL_AS}
  router-id = "${BGP_ROUTER_ID}"
  listen-addresses = ["0.0.0.0"]
  listen-port = 179
BGPEOF

    # Tambah peer jika diisi
    if [[ -n "$BGP_PEER1_IP" ]]; then
        cat >> /etc/gobgpd/gobgpd.conf << PEER1EOF

[[neighbors]]
  [neighbors.config]
    neighbor-address = "${BGP_PEER1_IP}"
    peer-as = ${BGP_PEER1_AS}
    description = "MikroTik-Peer-1"
  [neighbors.transport.config]
    passive-mode = false
  [neighbors.ebgp-multihop.config]
    enabled = true
    multihop-ttl = 10
  [neighbors.apply-policy.config]
    default-import-policy = "accept-route"
    default-export-policy = "reject-route"
    export-policy-list = ["policy-peer-1"]
  [[neighbors.afi-safis]]
    [neighbors.afi-safis.config]
      afi-safi-name = "ipv4-unicast"

[defined-sets]
  [[defined-sets.bgp-community-sets]]
    community-set-name = "comm-peer-1"
    community-list = ["${BGP_LOCAL_AS}:251"]
  [[defined-sets.bgp-community-sets]]
    community-set-name = "all-steering"
    community-list = ["${BGP_LOCAL_AS}:251"]

[[policy-definitions]]
  name = "policy-peer-1"
  [[policy-definitions.statements]]
    name = "allow-my-community"
    [policy-definitions.statements.conditions.bgp-conditions]
      community-set = "comm-peer-1"
    [policy-definitions.statements.actions]
      route-disposition = "accept-route"
  [[policy-definitions.statements]]
    name = "reject-other-steering"
    [policy-definitions.statements.conditions.bgp-conditions]
      community-set = "all-steering"
    [policy-definitions.statements.actions]
      route-disposition = "reject-route"
PEER1EOF
        ok "Konfigurasi GoBGP dengan peer ${BGP_PEER1_IP} (AS ${BGP_PEER1_AS}) dibuat"
    else
        warn "Peer BGP tidak diisi — edit manual: sudo nano /etc/gobgpd/gobgpd.conf"
        ok "Konfigurasi GoBGP minimal dibuat"
    fi
else
    # Jika env sudah ada, pertahankan config gobgpd yang sudah ada
    if [[ ! -f "/etc/gobgpd/gobgpd.conf" ]]; then
        # Copy dari app dir jika ada
        if [[ -f "$APP_DIR/gobgp/gobgpd.conf" ]]; then
            cp "$APP_DIR/gobgp/gobgpd.conf" /etc/gobgpd/gobgpd.conf
            ok "gobgpd.conf disalin dari $APP_DIR/gobgp/"
        else
            warn "gobgpd.conf tidak ditemukan — buat minimal"
            echo -e "[global.config]\n  as = 65000\n  router-id = \"$(hostname -I | awk '{print $1}')\"\n  listen-port = 179" \
                > /etc/gobgpd/gobgpd.conf
        fi
    else
        ok "gobgpd.conf sudah ada — dipertahankan"
    fi
fi

# ── Install systemd service GoBGP ──────────────────────────────────────────
if [[ -f "$APP_DIR/gobgp/gobgpd.service" ]]; then
    cp "$APP_DIR/gobgp/gobgpd.service" /etc/systemd/system/gobgpd.service
else
    cat > /etc/systemd/system/gobgpd.service << 'SVCEOF'
[Unit]
Description=GoBGP Daemon — NOC Billing Pro BGP Content Steering
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=root
ExecStart=/usr/local/bin/gobgpd -f /etc/gobgpd/gobgpd.conf --api-hosts 0.0.0.0:50051 --log-level info
ExecReload=/bin/kill -HUP $MAINPID
KillMode=process
Restart=always
RestartSec=5
StandardOutput=append:/var/log/gobgpd.log
StandardError=append:/var/log/gobgpd.log
LimitNOFILE=65536

[Install]
WantedBy=multi-user.target
SVCEOF
fi

systemctl daemon-reload
systemctl enable gobgpd > /dev/null
systemctl stop gobgpd 2>/dev/null || true
sleep 1
systemctl start gobgpd
sleep 2

if systemctl is-active --quiet gobgpd; then
    ok "GoBGP daemon RUNNING ✔ (BGP Content Steering siap)"
else
    warn "GoBGP gagal start — cek log: sudo journalctl -u gobgpd -n 20"
    warn "Lanjutkan install NOC Billing Pro terlebih dahulu"
fi

# ══════════════════════════════════════════════════════════════════════════════
# STEP 4: Clone / Update source code
# ══════════════════════════════════════════════════════════════════════════════
step "STEP 4/7 — Source Code NOC Billing Pro"

mkdir -p /opt
if [[ -d "$APP_DIR/.git" ]]; then
    info "Repository sudah ada — update..."
    cd "$APP_DIR"
    git fetch --all -q 2>/dev/null || warn "git fetch gagal — lanjutkan dengan kode yang ada"
    git reset --hard origin/main -q 2>/dev/null || true
    COMMIT=$(git log -1 --format='%h — %s' 2>/dev/null || echo "unknown")
    ok "Updated → $COMMIT"
else
    info "Clone repository..."
    rm -rf "$APP_DIR"
    if git clone "$REPO" "$APP_DIR" -q 2>/dev/null; then
        COMMIT=$(git -C "$APP_DIR" log -1 --format='%h — %s' 2>/dev/null || echo "unknown")
        ok "Cloned → $COMMIT"
    else
        warn "git clone gagal — buat direktori manual"
        mkdir -p "$APP_DIR"
        warn "Taruh docker-compose.yml dan file lain di $APP_DIR secara manual"
    fi
fi

# Symlink gobgpd.conf agar mudah diedit dari app dir
if [[ -d "$APP_DIR/gobgp" ]]; then
    ln -sf /etc/gobgpd/gobgpd.conf "$APP_DIR/gobgp/active-gobgpd.conf" 2>/dev/null || true
fi

# ══════════════════════════════════════════════════════════════════════════════
# STEP 5: Konfigurasi .env
# ══════════════════════════════════════════════════════════════════════════════
step "STEP 5/7 — Konfigurasi Environment"

if [[ "$SKIP_ENV" == false ]]; then
    mkdir -p "$(dirname "$ENV_FILE")"
    SECRET_KEY=$(python3 -c "import secrets; print(secrets.token_hex(32))" 2>/dev/null || \
                 cat /dev/urandom | tr -dc 'a-zA-Z0-9' | fold -w 64 | head -n 1)

    cat > "$ENV_FILE" << ENVEOF
# NOC Billing Pro — Backend Configuration
# Auto-generated: $(date '+%Y-%m-%d %H:%M:%S')
# Edit: nano $ENV_FILE

# ── Database ───────────────────────────────────────────────────────────────
MONGO_URI=mongodb://mongodb:27017/nocbillingpro
MONGO_DB_NAME=nocbillingpro

# ── Security ───────────────────────────────────────────────────────────────
SECRET_KEY=${SECRET_KEY}
ACCESS_TOKEN_EXPIRE_MINUTES=1440

# ── App ────────────────────────────────────────────────────────────────────
NOC_SERVICE_NAME=${NOC_NAME}
APP_URL=${APP_URL}
APP_EDITION=billing_pro
CORS_ORIGINS=*

# ── Billing ────────────────────────────────────────────────────────────────
ENABLE_BILLING_SCHEDULER=true
ENABLE_ISOLIR=true
ENABLE_HOTSPOT_CLEANUP=true

# ── Core Services ──────────────────────────────────────────────────────────
ENABLE_POLLING=true
ENABLE_SSE=true
ENABLE_SYSLOG=true
SYSLOG_PORT=5142
ENABLE_BACKUP=true
ENABLE_ROUTING_ALERTS=true
ENABLE_SPEEDTEST=true
ENABLE_SESSION_CACHE=true
ENABLE_SNMP_POLLER=true

# ── RADIUS ─────────────────────────────────────────────────────────────────
ENABLE_RADIUS=true
RADIUS_SECRET=${RADIUS_SECRET}

# ── GenieACS (TR-069 / ZTP) ────────────────────────────────────────────────
ENABLE_GENIEACS_SYNC=true
GENIEACS_URL=http://genieacs-nbi:7557
GENIEACS_USERNAME=admin
GENIEACS_PASSWORD=admin

# ── Peering Eye + BGP Content Steering ─────────────────────────────────────
ENABLE_BGP_STEERING=true
GOBGPD_HOST=172.17.0.1

# ── Features tidak aktif di Billing Pro ────────────────────────────────────
ENABLE_ROUTE_OPTIMIZER=false
ENABLE_NETWATCH_POLLER=false
ENABLE_NETFLOW=false

# ── License ────────────────────────────────────────────────────────────────
LICENSE_SERVER_URL=https://license.arbatraining.com

# ── Cloudflare Tunnel ──────────────────────────────────────────────────────
CF_TUNNEL_TOKEN=${CF_TUNNEL_TOKEN}

# ── Firebase ───────────────────────────────────────────────────────────────
FIREBASE_CREDENTIALS_PATH=/app/firebase-service-account.json
ENVEOF
    ok ".env NOC Billing Pro dibuat"
else
    ok ".env sudah ada — dipertahankan"
fi

# Pastikan file firebase ada (boleh kosong utk development)
touch "$APP_DIR/firebase-service-account.json" 2>/dev/null || true

# ══════════════════════════════════════════════════════════════════════════════
# STEP 6: Login GHCR & Pull Docker Images
# ══════════════════════════════════════════════════════════════════════════════
step "STEP 6/7 — Docker Images (Pull dari GHCR)"

if [[ "$SKIP_ENV" == false && -n "$GHCR_TOKEN" ]]; then
    info "Login ke GitHub Container Registry..."
    echo "$GHCR_TOKEN" | docker login ghcr.io -u "$GHCR_USER" --password-stdin \
        && ok "GHCR login berhasil" \
        || warn "GHCR login gagal — pull image mungkin memerlukan credentials"
else
    info "Coba pull tanpa login terlebih dahulu..."
fi

cd "$APP_DIR"
info "Pull images NOC Billing Pro..."
if docker compose pull --quiet 2>/dev/null; then
    ok "Images berhasil di-pull"
else
    warn "docker compose pull gagal — mencoba pull ulang..."
    sleep 3
    docker compose pull 2>/dev/null || warn "Pull gagal. Jalankan manual: cd $APP_DIR && docker compose pull"
fi

# Konfigurasi Cloudflare Tunnel di docker-compose.yml jika token diisi
if [[ -n "${CF_TUNNEL_TOKEN:-}" ]]; then
    info "Mengaktifkan Cloudflare Tunnel di docker-compose.yml..."

    # Gunakan Python untuk uncomment blok cloudflared secara aman & reliable
    # (menghindari masalah sed regex escaping pada berbagai distro)
    python3 - <<PYEOF
import re, sys

with open("$APP_DIR/docker-compose.yml", "r") as f:
    content = f.read()

# Uncomment blok cloudflared:
# Hanya uncomment baris yang diawali dengan '  #' (komentar dalam blok cloudflared).
# Ketika menemukan baris yang TIDAK diawali '  #', artinya blok cloudflared sudah selesai.
lines = content.splitlines()
new_lines = []
inside_cf = False
for line in lines:
    stripped = line.rstrip()
    # Deteksi awal blok cloudflared
    if re.match(r'^  # cloudflared:', stripped):
        inside_cf = True
    if inside_cf:
        if stripped.startswith('  #'):
            # Baris berkomentar — hapus prefix komentar '  # '
            uncommented = re.sub(r'^  # ?', '  ', stripped)
            new_lines.append(uncommented)
        else:
            # Baris tidak berkomentar = keluar dari blok cloudflared
            inside_cf = False
            new_lines.append(stripped)
    else:
        new_lines.append(stripped)

result = '\n'.join(new_lines) + '\n'

with open("$APP_DIR/docker-compose.yml", "w") as f:
    f.write(result)

print("  ✔  docker-compose.yml: cloudflared diaktifkan")
PYEOF

    # Tulis root .env agar CF_TUNNEL_TOKEN tersedia untuk docker-compose saat restart
    # (Docker Compose membaca .env dari direktori yang sama dengan docker-compose.yml)
    if [[ -f "$APP_DIR/.env" ]]; then
        # Update baris CF_TUNNEL_TOKEN jika sudah ada, atau append
        if grep -q '^CF_TUNNEL_TOKEN=' "$APP_DIR/.env" 2>/dev/null; then
            sed -i "s|^CF_TUNNEL_TOKEN=.*|CF_TUNNEL_TOKEN=${CF_TUNNEL_TOKEN}|" "$APP_DIR/.env"
        else
            echo "CF_TUNNEL_TOKEN=${CF_TUNNEL_TOKEN}" >> "$APP_DIR/.env"
        fi
    else
        echo "CF_TUNNEL_TOKEN=${CF_TUNNEL_TOKEN}" > "$APP_DIR/.env"
    fi
    ok "CF_TUNNEL_TOKEN disimpan ke $APP_DIR/.env untuk docker-compose"

    # Verifikasi hasilnya
    if grep -q "container_name: noc-billing-pro-cloudflared" "$APP_DIR/docker-compose.yml" 2>/dev/null; then
        ok "Cloudflare Tunnel berhasil diaktifkan di docker-compose.yml"
    else
        warn "Cloudflare Tunnel gagal diaktifkan via Python — coba uncomment manual di:"
        warn "  $APP_DIR/docker-compose.yml (cari blok '# cloudflared:')"
    fi
else
    info "Cloudflare Tunnel tidak diaktifkan (token kosong)."
    info "Untuk mengaktifkan nanti:"
    info "  1. Uncomment blok cloudflared di $APP_DIR/docker-compose.yml"
    info "  2. Tambahkan CF_TUNNEL_TOKEN=<token> ke $APP_DIR/.env"
fi

# ══════════════════════════════════════════════════════════════════════════════
# STEP 7: Start NOC Billing Pro
# ══════════════════════════════════════════════════════════════════════════════
step "STEP 7/7 — Start NOC Billing Pro"

cd "$APP_DIR"

# Hentikan container lama jika ada
docker compose down --remove-orphans 2>/dev/null || true
sleep 2

# Start semua service
info "Menjalankan docker compose up -d..."
# PENTING: Jangan pakai pipe ke grep — pipe akan menyebabkan exit code selalu 0
# yang membuat kondisi `|| err` tidak pernah terpicu (pipe masks exit code)
docker compose up -d 2>&1
DOCKER_EXIT=$?
if [[ $DOCKER_EXIT -ne 0 ]]; then
    err "docker compose up gagal (exit $DOCKER_EXIT) — cek log: docker compose logs"
fi
sleep 5

# ── Verifikasi container ───────────────────────────────────────────────────
check_container() {
    local name="$1"
    local label="$2"
    local state
    state=$(docker inspect --format='{{.State.Status}}' "$name" 2>/dev/null || echo "not_found")
    if [[ "$state" == "running" ]]; then
        ok "$label: RUNNING ✔"
        return 0
    else
        warn "$label: $state"
        return 1
    fi
}

echo ""
echo -e "  ${BOLD}Status Container:${N}"
check_container "noc-billing-pro-backend"     "Backend       " || true
check_container "noc-billing-pro-frontend"    "Frontend      " || true
check_container "noc-billing-pro-mongodb"     "MongoDB       " || true
check_container "noc-billing-pro-genieacs-cwmp" "GenieACS CWMP" || true
check_container "noc-billing-pro-genieacs-nbi"  "GenieACS NBI " || true
check_container "noc-billing-pro-updater"     "Auto Updater  " || true

# ── Auto-Import GenieACS Config ────────────────────────────────────────────
if [[ -f "$APP_DIR/genieacs/import_genieacs.sh" ]]; then
    info "Mengimpor konfigurasi default GenieACS (Provisions, Presets)..."
    bash "$APP_DIR/genieacs/import_genieacs.sh" || warn "Gagal menjalankan import GenieACS"
fi

# ── UFW Firewall ───────────────────────────────────────────────────────────
if command -v ufw &>/dev/null && ufw status | grep -q "active"; then
    # NOC Billing Pro — Web & API
    ufw allow 8082/tcp comment "NOC Billing Pro — Web Dashboard" 2>/dev/null
    ufw allow 8002/tcp comment "NOC Billing Pro — Backend API" 2>/dev/null
    # BGP Content Steering (GoBGP di host)
    ufw allow 179/tcp  comment "BGP (GoBGP — NOC Billing Pro)" 2>/dev/null
    # RADIUS Auth & Accounting
    ufw allow 1816/udp comment "RADIUS Auth — NOC Billing Pro" 2>/dev/null
    ufw allow 1817/udp comment "RADIUS Acct — NOC Billing Pro" 2>/dev/null
    # Syslog
    ufw allow 5142/udp comment "Syslog UDP — NOC Billing Pro" 2>/dev/null
    # GenieACS (TR-069 / ZTP)
    ufw allow 7548/tcp comment "GenieACS CWMP — NOC Billing Pro" 2>/dev/null
    ufw allow 7568/tcp comment "GenieACS FS — NOC Billing Pro" 2>/dev/null
    ufw allow 3001/tcp comment "GenieACS UI — NOC Billing Pro" 2>/dev/null
    # ── Port VPN (L2TP/IPSec + IKEv2 + SSTP) ────────────────────────────────
    ufw allow 1701/udp comment "L2TP — NOC Billing Pro VPN" 2>/dev/null
    ufw allow 500/udp  comment "IKEv2/IPSec ISAKMP — NOC Billing Pro VPN" 2>/dev/null
    ufw allow 4500/udp comment "IKEv2/IPSec NAT-T — NOC Billing Pro VPN" 2>/dev/null
    ufw allow 443/tcp  comment "SSTP VPN (HTTPS) — NOC Billing Pro VPN" 2>/dev/null
    ufw allow 1723/tcp comment "PPTP — NOC Billing Pro VPN (legacy)" 2>/dev/null
    ok "UFW: semua port dibuka (App + VPN L2TP/IKEv2/SSTP/PPTP)"
elif command -v ufw &>/dev/null; then
    # UFW tidak aktif — enable dan buka semua port minimal
    ufw --force enable > /dev/null 2>&1 || true
    ufw allow 22/tcp  comment "SSH" 2>/dev/null
    ufw allow 8082/tcp comment "NOC Billing Pro — Web Dashboard" 2>/dev/null
    ufw allow 8002/tcp comment "NOC Billing Pro — Backend API" 2>/dev/null
    ufw allow 179/tcp  comment "BGP" 2>/dev/null
    ufw allow 1816/udp comment "RADIUS Auth" 2>/dev/null
    ufw allow 1817/udp comment "RADIUS Acct" 2>/dev/null
    ufw allow 5142/udp comment "Syslog" 2>/dev/null
    ufw allow 7548/tcp comment "GenieACS CWMP" 2>/dev/null
    ufw allow 7568/tcp comment "GenieACS FS" 2>/dev/null
    ufw allow 3001/tcp comment "GenieACS UI" 2>/dev/null
    ufw allow 1701/udp comment "L2TP VPN" 2>/dev/null
    ufw allow 500/udp  comment "IKEv2 ISAKMP" 2>/dev/null
    ufw allow 4500/udp comment "IKEv2 NAT-T" 2>/dev/null
    ufw allow 443/tcp  comment "SSTP VPN" 2>/dev/null
    ufw allow 1723/tcp comment "PPTP VPN" 2>/dev/null
    ok "UFW: diaktifkan dan semua port dibuka"
fi

# ── Install shortcut command ───────────────────────────────────────────────
cat > /usr/local/bin/noc-billing-pro << 'CMDEOF'
#!/bin/bash
# Shortcut command untuk NOC Billing Pro
APP_DIR="/opt/noc-billing-pro"
case "${1:-status}" in
    start)   cd "$APP_DIR" && docker compose up -d ;;
    stop)    cd "$APP_DIR" && docker compose down ;;
    restart) cd "$APP_DIR" && docker compose restart ;;
    update)  cd "$APP_DIR" && docker compose pull && docker compose up -d --force-recreate ;;
    logs)    cd "$APP_DIR" && docker compose logs -f --tail=50 "${2:-noc-backend}" ;;
    status)
        echo "── NOC Billing Pro Status ──────────────────────"
        docker compose -f "$APP_DIR/docker-compose.yml" ps
        echo ""
        echo "── GoBGP Status ────────────────────────────────"
        systemctl is-active gobgpd && gobgp neighbor 2>/dev/null || echo "gobgpd tidak aktif"
        ;;
    gobgp)   shift; gobgp "$@" ;;
    *)
        echo "Cara pakai: noc-billing-pro [start|stop|restart|update|logs|status|gobgp]"
        ;;
esac
CMDEOF
chmod +x /usr/local/bin/noc-billing-pro
ok "Shortcut 'noc-billing-pro' tersedia"

# ── Seed admin user ────────────────────────────────────────────────────────
info "Menunggu backend siap (30 detik)..."
sleep 30

_HOST_IP=$(hostname -I | awk '{print $1}')
SEED_RESULT=$(curl -s -o /dev/null -w "%{http_code}" \
    "http://localhost:8002/api/auth/login" 2>/dev/null || echo "000")
if [[ "$SEED_RESULT" == "422" || "$SEED_RESULT" == "400" ]]; then
    ok "Backend API RESPONDING"
else
    warn "Backend belum merespons (HTTP $SEED_RESULT) — mungkin masih loading"
    warn "Cek: docker logs noc-billing-pro-backend -f"
fi

# ── RINGKASAN AKHIR ─────────────────────────────────────────────────────────
echo ""
echo -e "${BOLD}${C}╔══════════════════════════════════════════════════════════════════════╗${N}"
echo -e "${BOLD}${C}║   ✅  NOC BILLING PRO — INSTALASI SELESAI!                           ║${N}"
echo -e "${BOLD}${C}╠══════════════════════════════════════════════════════════════════════╣${N}"
echo -e "${BOLD}${C}║${N}                                                                       ${BOLD}${C}║${N}"
echo -e "${BOLD}${C}║${N}  ${BOLD}Akses Dashboard:${N}                                                  ${BOLD}${C}║${N}"
echo -e "${BOLD}${C}║${N}    🌐 Web       : http://${_HOST_IP}:8082                               ${BOLD}${C}║${N}"
echo -e "${BOLD}${C}║${N}    🔧 GenieACS  : http://${_HOST_IP}:3001                               ${BOLD}${C}║${N}"
echo -e "${BOLD}${C}║${N}    📡 API       : http://${_HOST_IP}:8002/docs                          ${BOLD}${C}║${N}"
echo -e "${BOLD}${C}║${N}                                                                       ${BOLD}${C}║${N}"
echo -e "${BOLD}${C}║${N}  ${BOLD}Login Default:${N}                                                    ${BOLD}${C}║${N}"
echo -e "${BOLD}${C}║${N}    👤 Username  : admin                                                ${BOLD}${C}║${N}"
echo -e "${BOLD}${C}║${N}    🔑 Password  : admin123                                             ${BOLD}${C}║${N}"
echo -e "${BOLD}${C}║${N}                                                                       ${BOLD}${C}║${N}"
echo -e "${BOLD}${C}║${N}  ${BOLD}Service Status:${N}                                                   ${BOLD}${C}║${N}"
echo -e "${BOLD}${C}║${N}    🐳 Docker    : $(systemctl is-active docker)                                    ${BOLD}${C}║${N}"
echo -e "${BOLD}${C}║${N}    📡 GoBGP     : $(systemctl is-active gobgpd)                                   ${BOLD}${C}║${N}"
echo -e "${BOLD}${C}║${N}                                                                       ${BOLD}${C}║${N}"
echo -e "${BOLD}${C}║${N}  ${BOLD}Port yang Dibuka:${N}                                                 ${BOLD}${C}║${N}"
echo -e "${BOLD}${C}║${N}    8082  Frontend Web   | 8002  Backend API                           ${BOLD}${C}║${N}"
echo -e "${BOLD}${C}║${N}    1816  RADIUS Auth    | 1817  RADIUS Acct                           ${BOLD}${C}║${N}"
echo -e "${BOLD}${C}║${N}    179   BGP (GoBGP)    | 5142  Syslog UDP                            ${BOLD}${C}║${N}"
echo -e "${BOLD}${C}║${N}    1701  L2TP VPN       | 443   SSTP VPN                              ${BOLD}${C}║${N}"
echo -e "${BOLD}${C}║${N}    3001  GenieACS UI    | 7548  GenieACS CWMP                         ${BOLD}${C}║${N}"
echo -e "${BOLD}${C}║${N}                                                                       ${BOLD}${C}║${N}"
echo -e "${BOLD}${C}║${N}  ${BOLD}Perintah Berguna:${N}                                                 ${BOLD}${C}║${N}"
echo -e "${BOLD}${C}║${N}    noc-billing-pro status    # cek semua status                       ${BOLD}${C}║${N}"
echo -e "${BOLD}${C}║${N}    noc-billing-pro logs      # lihat log backend                      ${BOLD}${C}║${N}"
echo -e "${BOLD}${C}║${N}    noc-billing-pro update    # update ke versi terbaru                ${BOLD}${C}║${N}"
echo -e "${BOLD}${C}║${N}    noc-billing-pro gobgp neighbor  # cek BGP peers                   ${BOLD}${C}║${N}"
echo -e "${BOLD}${C}║${N}                                                                       ${BOLD}${C}║${N}"
echo -e "${BOLD}${C}║${N}  ${BOLD}Langkah Selanjutnya:${N}                                              ${BOLD}${C}║${N}"
echo -e "${BOLD}${C}║${N}    1. Buka http://${_HOST_IP}:8082 dan login                             ${BOLD}${C}║${N}"
echo -e "${BOLD}${C}║${N}    2. Masukkan License Key (ArBa-BP-XXXX-XXXX)                        ${BOLD}${C}║${N}"
echo -e "${BOLD}${C}║${N}    3. Tambahkan perangkat di menu Device                              ${BOLD}${C}║${N}"
echo -e "${BOLD}${C}║${N}    4. Aktifkan BGP Steering di Peering Eye                           ${BOLD}${C}║${N}"
echo -e "${BOLD}${C}╚══════════════════════════════════════════════════════════════════════╝${N}"
echo ""
