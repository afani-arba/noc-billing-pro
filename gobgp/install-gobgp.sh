#!/bin/bash
# ══════════════════════════════════════════════════════════════════════
# install-gobgp.sh — Instalasi Otomatis GoBGP untuk NOC Billing Pro
# ══════════════════════════════════════════════════════════════════════
#
# Script ini akan:
#   1. Download & install GoBGP binary (gobgpd + gobgp CLI)
#   2. Install konfigurasi ke /etc/gobgpd/gobgpd.conf
#   3. Install systemd service gobgpd
#   4. Enable & start gobgpd
#   5. Buka port 179/tcp di firewall (ufw)
#   6. Verifikasi instalasi
#
# Cara pakai:
#   chmod +x install-gobgp.sh
#   sudo bash install-gobgp.sh
#
# Target: Ubuntu 22.04 LTS (AMD64)
# ══════════════════════════════════════════════════════════════════════

set -e

# ── Warna output ───────────────────────────────────────────────────────────────
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
BOLD='\033[1m'
NC='\033[0m'

log_info()    { echo -e "${BLUE}[INFO]${NC}  $1"; }
log_ok()      { echo -e "${GREEN}[OK]${NC}    $1"; }
log_warn()    { echo -e "${YELLOW}[WARN]${NC}  $1"; }
log_error()   { echo -e "${RED}[ERROR]${NC} $1"; }
log_section() { echo -e "\n${CYAN}${BOLD}══ $1 ══${NC}"; }

# ── Konfigurasi ────────────────────────────────────────────────────────────────
GOBGP_VERSION="3.26.0"   # Versi GoBGP — update jika perlu
GOBGP_URL="https://github.com/osrg/gobgp/releases/download/v${GOBGP_VERSION}/gobgp_${GOBGP_VERSION}_linux_amd64.tar.gz"
INSTALL_DIR="/usr/local/bin"
CONFIG_DIR="/etc/gobgpd"
LOG_FILE="/var/log/gobgpd.log"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# ── Cek root ───────────────────────────────────────────────────────────────────
if [[ $EUID -ne 0 ]]; then
    log_error "Script ini harus dijalankan sebagai root: sudo bash install-gobgp.sh"
    exit 1
fi

echo ""
echo -e "${BOLD}╔══════════════════════════════════════════════════════════╗${NC}"
echo -e "${BOLD}║   GoBGP Installer — NOC Billing Pro                     ║${NC}"
echo -e "${BOLD}║   BGP Content Steering (Peering Eye)                    ║${NC}"
echo -e "${BOLD}╚══════════════════════════════════════════════════════════╝${NC}"
echo ""

# ── STEP 1: Cek apakah GoBGP sudah ada ────────────────────────────────────────
log_section "STEP 1: Cek instalasi existing"

if command -v gobgpd &>/dev/null; then
    EXISTING_VER=$(gobgpd --version 2>/dev/null | grep -oP '[\d]+\.[\d]+\.[\d]+' | head -1 || echo "unknown")
    log_warn "GoBGP sudah terinstall (versi: ${EXISTING_VER})"
    read -p "  Lanjutkan dan overwrite? [y/N]: " CONFIRM
    if [[ ! "$CONFIRM" =~ ^[Yy]$ ]]; then
        log_info "Instalasi dibatalkan"
        exit 0
    fi
else
    log_ok "GoBGP belum terinstall — lanjutkan instalasi baru"
fi

# ── STEP 2: Download GoBGP ─────────────────────────────────────────────────────
log_section "STEP 2: Download GoBGP v${GOBGP_VERSION}"

TMP_DIR=$(mktemp -d)
ARCHIVE="${TMP_DIR}/gobgp.tar.gz"

log_info "Downloading dari GitHub releases..."
if wget -q --show-progress -O "${ARCHIVE}" "${GOBGP_URL}"; then
    log_ok "Download selesai"
else
    log_warn "wget gagal, mencoba curl..."
    if curl -L --progress-bar -o "${ARCHIVE}" "${GOBGP_URL}"; then
        log_ok "Download via curl selesai"
    else
        log_error "Gagal download GoBGP dari: ${GOBGP_URL}"
        log_error "Cek koneksi internet atau ganti GOBGP_VERSION di script ini"
        rm -rf "${TMP_DIR}"
        exit 1
    fi
fi

# ── STEP 3: Extract & Install binary ──────────────────────────────────────────
log_section "STEP 3: Install binary"

tar -xzf "${ARCHIVE}" -C "${TMP_DIR}"

if [[ -f "${TMP_DIR}/gobgpd" ]]; then
    install -m 755 "${TMP_DIR}/gobgpd" "${INSTALL_DIR}/gobgpd"
    log_ok "gobgpd → ${INSTALL_DIR}/gobgpd"
else
    log_error "gobgpd binary tidak ditemukan di archive!"
    rm -rf "${TMP_DIR}"
    exit 1
fi

if [[ -f "${TMP_DIR}/gobgp" ]]; then
    install -m 755 "${TMP_DIR}/gobgp" "${INSTALL_DIR}/gobgp"
    log_ok "gobgp CLI → ${INSTALL_DIR}/gobgp"
fi

rm -rf "${TMP_DIR}"

# Verifikasi binary
INSTALLED_VER=$(gobgpd --version 2>/dev/null | grep -oP '[\d]+\.[\d]+\.[\d]+' | head -1 || echo "?")
log_ok "GoBGP terinstall — versi: ${INSTALLED_VER}"

# ── STEP 4: Setup direktori & konfigurasi ─────────────────────────────────────
log_section "STEP 4: Konfigurasi GoBGP"

mkdir -p "${CONFIG_DIR}"

# Salin config dari folder gobgp/ (script berada di sana)
if [[ -f "${SCRIPT_DIR}/gobgpd.conf" ]]; then
    if [[ -f "${CONFIG_DIR}/gobgpd.conf" ]]; then
        log_warn "Config sudah ada → backup ke gobgpd.conf.bak"
        cp "${CONFIG_DIR}/gobgpd.conf" "${CONFIG_DIR}/gobgpd.conf.bak"
    fi
    cp "${SCRIPT_DIR}/gobgpd.conf" "${CONFIG_DIR}/gobgpd.conf"
    log_ok "Config disalin: ${CONFIG_DIR}/gobgpd.conf"
else
    log_warn "File gobgpd.conf tidak ditemukan di ${SCRIPT_DIR}"
    log_warn "Membuat config minimal..."
    cat > "${CONFIG_DIR}/gobgpd.conf" << 'EOF'
# Konfigurasi minimal — EDIT SESUAI TOPOLOGI ANDA
# Lihat gobgpd.conf di folder gobgp/ untuk contoh lengkap
[global.config]
  as = 65000
  router-id = "10.254.254.254"
  listen-addresses = ["0.0.0.0"]
  listen-port = 179
EOF
    log_ok "Config minimal dibuat: ${CONFIG_DIR}/gobgpd.conf"
fi

# Buat symlink agar mudah diedit
if [[ -d "/opt/noc-billing-pro/gobgp" ]]; then
    ln -sf "/opt/noc-billing-pro/gobgp/gobgpd.conf" "${CONFIG_DIR}/gobgpd.conf"
    log_ok "Symlink dibuat: ${CONFIG_DIR}/gobgpd.conf → /opt/noc-billing-pro/gobgp/gobgpd.conf"
fi

# Setup log file
touch "${LOG_FILE}"
chmod 644 "${LOG_FILE}"
log_ok "Log file: ${LOG_FILE}"

# ── STEP 5: Install systemd service ───────────────────────────────────────────
log_section "STEP 5: Install systemd service"

if [[ -f "${SCRIPT_DIR}/gobgpd.service" ]]; then
    cp "${SCRIPT_DIR}/gobgpd.service" "/etc/systemd/system/gobgpd.service"
    log_ok "Service file disalin: /etc/systemd/system/gobgpd.service"
else
    # Buat service file inline
    cat > "/etc/systemd/system/gobgpd.service" << EOF
[Unit]
Description=GoBGP Daemon — NOC Billing Pro BGP Content Steering
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=root
ExecStart=/usr/local/bin/gobgpd -f ${CONFIG_DIR}/gobgpd.conf --api-hosts 0.0.0.0:50051 --log-level info
ExecReload=/bin/kill -HUP \$MAINPID
KillMode=process
Restart=always
RestartSec=5
StandardOutput=append:${LOG_FILE}
StandardError=append:${LOG_FILE}
LimitNOFILE=65536

[Install]
WantedBy=multi-user.target
EOF
    log_ok "Service file dibuat dari template"
fi

systemctl daemon-reload
systemctl enable gobgpd
log_ok "gobgpd diset auto-start saat reboot"

# ── STEP 6: Buka port firewall ─────────────────────────────────────────────────
log_section "STEP 6: Konfigurasi Firewall"

if command -v ufw &>/dev/null; then
    UFW_STATUS=$(ufw status | head -1)
    if echo "${UFW_STATUS}" | grep -q "active"; then
        ufw allow 179/tcp comment "BGP (GoBGP — NOC Billing Pro)" 2>/dev/null && \
            log_ok "UFW: port 179/tcp dibuka (BGP)" || \
            log_warn "Gagal buka port UFW — cek manual: ufw allow 179/tcp"
    else
        log_warn "UFW tidak aktif — skipping firewall rule"
    fi
else
    log_warn "UFW tidak ditemukan"
    # Coba iptables sebagai fallback
    if command -v iptables &>/dev/null; then
        iptables -C INPUT -p tcp --dport 179 -j ACCEPT 2>/dev/null || \
            iptables -A INPUT -p tcp --dport 179 -j ACCEPT && \
            log_ok "iptables: port 179/tcp dibuka"
    fi
fi

# ── STEP 7: Start gobgpd ────────────────────────────────────────────────────────
log_section "STEP 7: Jalankan GoBGP"

# Stop terlebih dahulu jika sudah berjalan
systemctl stop gobgpd 2>/dev/null || true

# Validasi config sebelum start
log_info "Memvalidasi konfigurasi..."
if gobgpd -f "${CONFIG_DIR}/gobgpd.conf" --dry-run 2>/dev/null; then
    log_ok "Konfigurasi valid"
else
    log_warn "Dry-run tidak tersedia di versi ini — lanjutkan start"
fi

systemctl start gobgpd
sleep 2

if systemctl is-active --quiet gobgpd; then
    log_ok "gobgpd BERJALAN dengan sukses!"
else
    log_error "gobgpd gagal start! Cek log:"
    log_error "  sudo journalctl -u gobgpd -n 20 --no-pager"
    log_error "  sudo cat ${LOG_FILE}"
    exit 1
fi

# ── STEP 8: Verifikasi ─────────────────────────────────────────────────────────
log_section "STEP 8: Verifikasi Instalasi"

echo ""
echo -e "  ${BOLD}Binary:${NC}"
echo -e "    gobgpd : $(which gobgpd) [v${INSTALLED_VER}]"
echo -e "    gobgp  : $(which gobgp 2>/dev/null || echo 'tidak ditemukan')"
echo ""
echo -e "  ${BOLD}Service:${NC}"
echo -e "    Status : $(systemctl is-active gobgpd)"
echo -e "    Enable : $(systemctl is-enabled gobgpd)"
echo ""
echo -e "  ${BOLD}Config:${NC}"
echo -e "    Path   : ${CONFIG_DIR}/gobgpd.conf"
echo ""
echo -e "  ${BOLD}Log:${NC}"
echo -e "    Path   : ${LOG_FILE}"
echo ""

# Cek koneksi gobgp CLI
log_info "Cek gobgp global info..."
if gobgp global 2>/dev/null; then
    log_ok "gobgp CLI bisa terhubung ke daemon"
else
    log_warn "gobgp CLI belum bisa terhubung — mungkin perlu beberapa detik"
fi

# ── SELESAI ─────────────────────────────────────────────────────────────────────
echo ""
echo -e "${GREEN}${BOLD}╔══════════════════════════════════════════════════════════╗${NC}"
echo -e "${GREEN}${BOLD}║  ✅  GoBGP berhasil diinstall & aktif!                  ║${NC}"
echo -e "${GREEN}${BOLD}╠══════════════════════════════════════════════════════════╣${NC}"
echo -e "${GREEN}${BOLD}║  ${NC}Langkah selanjutnya:                                     ${GREEN}${BOLD}║${NC}"
echo -e "${GREEN}${BOLD}║  ${NC}1. Edit config sesuai topologi Anda:                      ${GREEN}${BOLD}║${NC}"
echo -e "${GREEN}${BOLD}║  ${NC}   sudo nano /etc/gobgpd/gobgpd.conf                      ${GREEN}${BOLD}║${NC}"
echo -e "${GREEN}${BOLD}║  ${NC}2. Restart setelah edit config:                           ${GREEN}${BOLD}║${NC}"
echo -e "${GREEN}${BOLD}║  ${NC}   sudo systemctl restart gobgpd                          ${GREEN}${BOLD}║${NC}"
echo -e "${GREEN}${BOLD}║  ${NC}3. Konfigurasi BGP peer di MikroTik:                      ${GREEN}${BOLD}║${NC}"
echo -e "${GREEN}${BOLD}║  ${NC}   /routing bgp peer add name=noc-billing-pro              ${GREEN}${BOLD}║${NC}"
echo -e "${GREEN}${BOLD}║  ${NC}     remote-address=IP-VPS remote-as=65000                 ${GREEN}${BOLD}║${NC}"
echo -e "${GREEN}${BOLD}║  ${NC}     ttl=10 multihop=yes                                   ${GREEN}${BOLD}║${NC}"
echo -e "${GREEN}${BOLD}║  ${NC}4. Jalankan NOC Billing Pro:                              ${GREEN}${BOLD}║${NC}"
echo -e "${GREEN}${BOLD}║  ${NC}   cd /opt/noc-billing-pro && docker compose up -d         ${GREEN}${BOLD}║${NC}"
echo -e "${GREEN}${BOLD}║  ${NC}5. Monitor GoBGP via dashboard Peering Eye                ${GREEN}${BOLD}║${NC}"
echo -e "${GREEN}${BOLD}╚══════════════════════════════════════════════════════════╝${NC}"
echo ""
