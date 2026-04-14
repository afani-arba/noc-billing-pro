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
# ║     4. UFW firewall rules                                                     ║
# ║     5. Auto-start saat reboot                                                 ║
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

    read -r -p "  Nama layanan ISP Anda [NOC Billing Pro]: " _NAME
    NOC_NAME="${_NAME:-NOC Billing Pro}"

    read -r -p "  Domain / URL akses (contoh: https://billing.domain.com) [http://$(hostname -I | awk '{print $1}'):8082]: " _URL
    APP_URL="${_URL:-http://$(hostname -I | awk '{print $1}'):8082}"

    read -r -p "  RADIUS Secret (untuk MikroTik hotspot) [ganti_radius_secret]: " _RSECRET
    RADIUS_SECRET="${_RSECRET:-ganti_radius_secret}"

    echo ""
    echo -e "  ${Y}${BOLD}Konfigurasi GoBGP (BGP Content Steering):${N}"
    read -r -p "  Local AS Number GoBGP [65000]: " _AS
    BGP_LOCAL_AS="${_AS:-65000}"

    read -r -p "  Router-ID GoBGP (IP VPS/loopback) [$(hostname -I | awk '{print $1}')]: " _RID
    BGP_ROUTER_ID="${_RID:-$(hostname -I | awk '{print $1}')}"

    read -r -p "  IP MikroTik BGP Peer 1 (kosongkan jika belum ada): " _PEER1
    BGP_PEER1_IP="${_PEER1:-}"

    read -r -p "  AS Number MikroTik Peer 1 [65001]: " _PEER1AS
    BGP_PEER1_AS="${_PEER1AS:-65001}"

    echo ""
    echo -e "  ${Y}${BOLD}GitHub Container Registry (GHCR):${N}"
    info "Diperlukan untuk pull image NOC Billing Pro dari ghcr.io"
    read -r -p "  GitHub Username [afani-arba]: " _GHUSER
    GHCR_USER="${_GHUSER:-afani-arba}"
    read -r -s -p "  GitHub Token (Personal Access Token / classic): " _GHTOKEN
    echo ""
    GHCR_TOKEN="$_GHTOKEN"
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
    > /dev/null 2>&1

ok "Paket sistem OK"

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

    # Tambah Docker GPG key & repo
    install -m 0755 -d /etc/apt/keyrings
    curl -fsSL https://download.docker.com/linux/ubuntu/gpg \
        | gpg --dearmor -o /etc/apt/keyrings/docker.gpg
    chmod a+r /etc/apt/keyrings/docker.gpg

    echo \
        "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] \
        https://download.docker.com/linux/ubuntu \
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
APP_EDITION=enterprise
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
docker compose up -d 2>&1 | grep -v "^#" || err "docker compose up gagal"
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

# ── UFW Firewall ───────────────────────────────────────────────────────────
if command -v ufw &>/dev/null && ufw status | grep -q "active"; then
    ufw allow 8082/tcp comment "NOC Billing Pro — Web Dashboard" 2>/dev/null
    ufw allow 8002/tcp comment "NOC Billing Pro — Backend API" 2>/dev/null
    ufw allow 179/tcp  comment "BGP (GoBGP — NOC Billing Pro)" 2>/dev/null
    ufw allow 1816/udp comment "RADIUS Auth — NOC Billing Pro" 2>/dev/null
    ufw allow 1817/udp comment "RADIUS Acct — NOC Billing Pro" 2>/dev/null
    ufw allow 5142/udp comment "Syslog UDP — NOC Billing Pro" 2>/dev/null
    ufw allow 7548/tcp comment "GenieACS CWMP — NOC Billing Pro" 2>/dev/null
    ufw allow 7568/tcp comment "GenieACS FS — NOC Billing Pro" 2>/dev/null
    ufw allow 3001/tcp comment "GenieACS UI — NOC Billing Pro" 2>/dev/null
    ok "UFW: semua port dibuka"
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
echo -e "${BOLD}${C}║${N}    1816  RADIUS Auth     | 1817  RADIUS Acct                          ${BOLD}${C}║${N}"
echo -e "${BOLD}${C}║${N}    179   BGP (GoBGP)     | 7548  GenieACS CWMP                        ${BOLD}${C}║${N}"
echo -e "${BOLD}${C}║${N}    3001  GenieACS UI     | 5142  Syslog UDP                           ${BOLD}${C}║${N}"
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
