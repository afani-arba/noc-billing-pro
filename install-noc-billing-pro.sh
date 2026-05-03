#!/bin/bash

# =============================================================================
#   Auto-Installer NOC Billing Pro - Debian 12/13 (Trixie) Compatible
# =============================================================================
# Memastikan PATH lengkap agar semua binary sistem ditemukan
export PATH=$PATH:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin

# Warna output
RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; CYAN='\033[0;36m'; NC='\033[0m'
ok()   { echo -e "${GREEN}[OK]${NC} $1"; }
warn() { echo -e "${YELLOW}[WARN]${NC} $1"; }
fail() { echo -e "${RED}[FAIL]${NC} $1"; }
info() { echo -e "${CYAN}>>>  $1${NC}"; }

echo ""
echo "========================================================="
echo "   Auto-Installer NOC Billing Pro (Debian 12/13)         "
echo "========================================================="
echo ""

# Pastikan dijalankan sebagai root
if [ "$EUID" -ne 0 ]; then
    fail "Jalankan script ini sebagai root (gunakan: sudo bash install.sh)"
    exit 1
fi

# ─────────────────────────────────────────────────────────────
# STEP 1: Update OS & Dependensi Dasar
# ─────────────────────────────────────────────────────────────
info "[1/7] Mengupdate sistem dan dependensi inti..."
apt-get update -qq && apt-get upgrade -y -qq
apt-get install -y -qq \
    git curl wget ufw nano \
    apt-transport-https ca-certificates \
    gnupg2 procps util-linux unzip \
    && ok "Dependensi dasar berhasil diinstall." \
    || warn "Beberapa paket dasar gagal, lanjut..."

# ─────────────────────────────────────────────────────────────
# STEP 2: Install VPN Clients & Network Tools
# ─────────────────────────────────────────────────────────────
info "[2/7] Menginstall VPN & Network Tools..."
# Install satu per satu agar 1 paket gagal tidak blokir yang lain
for PKG in ppp strongswan iproute2 iptables traceroute iputils-ping kmod xl2tpd sstp-client; do
    apt-get install -y -qq "$PKG" 2>/dev/null \
        && ok "  $PKG installed" \
        || warn "  $PKG tidak tersedia di repo Debian 13, dilewati."
done

# ─────────────────────────────────────────────────────────────
# STEP 3: Install Cloudflared
# ─────────────────────────────────────────────────────────────
info "[3/7] Menginstall Cloudflared..."
if ! command -v cloudflared &>/dev/null; then
    ARCH=$(dpkg --print-architecture)
    curl -fsSL "https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-${ARCH}.deb" -o /tmp/cloudflared.deb \
        && dpkg -i /tmp/cloudflared.deb \
        && rm -f /tmp/cloudflared.deb \
        && ok "Cloudflared berhasil diinstall." \
        || warn "Cloudflared gagal diinstall, lanjut..."
else
    ok "Cloudflared sudah terinstall. ($(cloudflared --version 2>&1 | head -1))"
fi

# ─────────────────────────────────────────────────────────────
# STEP 4: Install GoBGP
# ─────────────────────────────────────────────────────────────
info "[4/7] Menginstall GoBGP..."
if ! command -v gobgp &>/dev/null; then
    GOBGP_VER="2.33.0"
    wget -q "https://github.com/osrg/gobgp/releases/download/v${GOBGP_VER}/gobgp_${GOBGP_VER}_linux_amd64.tar.gz" -O /tmp/gobgp.tar.gz \
        && tar -xzf /tmp/gobgp.tar.gz -C /tmp \
        && mv /tmp/gobgp /usr/local/bin/ \
        && mv /tmp/gobgpd /usr/local/bin/ \
        && rm -f /tmp/gobgp.tar.gz \
        && ok "GoBGP v${GOBGP_VER} berhasil diinstall." \
        || warn "GoBGP gagal diinstall, lanjut..."
else
    ok "GoBGP sudah terinstall."
fi

# ─────────────────────────────────────────────────────────────
# STEP 5: Install Zapret DPI Bypass
# ─────────────────────────────────────────────────────────────
info "[5/7] Menginstall Zapret DPI Bypass..."
if [ ! -d "/opt/zapret" ]; then
    git clone --depth=1 https://github.com/bol-van/zapret.git /opt/zapret 2>&1 \
        && ok "Zapret repository berhasil di-clone." \
        || { warn "Zapret gagal di-clone, lanjut..."; }

    if [ -d "/opt/zapret" ]; then
        # Setup files for hostlist
        touch /opt/zapret/hostlist.txt
        touch /opt/zapret/hostlist-auto.txt
        chmod 666 /opt/zapret/hostlist.txt /opt/zapret/hostlist-auto.txt

        # Buat config default untuk ISP Indonesia
        cat > /opt/zapret/config <<'ZAPRETEOF'
# MODE: nfqws, tpws, tpws-socks, filter, custom
MODE=nfqws
DISABLE_IPV4=0
DISABLE_IPV6=1
FWTYPE=iptables

# WAJIB: NFQWS_ENABLE=1 agar daemon aktif
NFQWS_ENABLE=1
NFQWS_PORTS_TCP=80,443
NFQWS_PORTS_UDP=443

# DPI Bypass Strategy: Universal (Semua ISP)
NFQWS_OPT="--dpi-desync=disorder2 --dpi-desync-split-pos=2 --dpi-desync-ttl=4"

# UDP / QUIC Bypass (YouTube, Cloudflare, dll via UDP port 443)
NFQWS_OPT_EXTRA="--dpi-desync=fake --dpi-desync-any-protocol --dpi-desync-cutoff=d3"

MODE_FILTER=none
# HOSTLIST=/opt/zapret/hostlist.txt
ZAPRETEOF

        cd /opt/zapret
        if [ -f "install_bin.sh" ]; then
            chmod +x install_bin.sh
        fi

        if [ -f "init.d/systemd/zapret.service" ]; then
            cp init.d/systemd/zapret.service /etc/systemd/system/
        fi
        
        # Generate init script
        bash /opt/zapret/install_bin.sh 2>&1 >/dev/null

        # Fix Asymmetric Routing & Intercept Rules Permanently
        info "Konfigurasi Firewall & Routing untuk Zapret..."
        export DEBIAN_FRONTEND=noninteractive
        apt-get install -y iptables-persistent >/dev/null 2>&1
        
        # 1. Allow FORWARD traffic (UFW by default drops it)
        iptables -I FORWARD 1 -j ACCEPT
        
        # 2. Fix Asymmetric Routing using MASQUERADE
        # We find the default internet interface (usually ens18 or eth0)
        DEF_IFACE=$(ip route | grep default | awk '{print $5}' | head -n1)
        if [ ! -z "$DEF_IFACE" ]; then
            iptables -t nat -I POSTROUTING 1 -o $DEF_IFACE -j MASQUERADE
            
            # 3. Intercept HTTP/HTTPS leaving the server for Zapret
            iptables -t mangle -I POSTROUTING 1 -o $DEF_IFACE -p tcp -m multiport --dports 80,443 -j NFQUEUE --queue-num 200 --queue-bypass
            iptables -t mangle -I POSTROUTING 2 -o $DEF_IFACE -p udp --dport 443 -j NFQUEUE --queue-num 200 --queue-bypass
        fi

        # Save rules permanently
        netfilter-persistent save >/dev/null 2>&1
        systemctl enable zapret >/dev/null 2>&1
        systemctl restart zapret >/dev/null 2>&1
        ok "Zapret terinstall dan Firewall di-patch."
    fi
else
    ok "Zapret sudah terinstall di /opt/zapret."
fi

# ─────────────────────────────────────────────────────────────
# STEP 6: Install Docker & Docker Compose
# ─────────────────────────────────────────────────────────────
info "[6/7] Menginstall Docker & Docker Compose..."
if ! command -v docker &>/dev/null; then
    curl -fsSL https://get.docker.com -o /tmp/get-docker.sh
    sh /tmp/get-docker.sh
    systemctl enable docker
    systemctl start docker
    apt-get install -y -qq docker-compose-plugin
    rm -f /tmp/get-docker.sh
    ok "Docker berhasil diinstall. ($(docker --version))"
else
    ok "Docker sudah terinstall. ($(docker --version))"
fi

# ─────────────────────────────────────────────────────────────
# STEP 7: Clone Repository & Deploy NOC Billing Pro
# ─────────────────────────────────────────────────────────────
info "[7/7] Setup NOC Billing Pro..."

cd /opt
if [ -d "noc-billing-pro" ]; then
    info "  Directory noc-billing-pro sudah ada, pull terbaru..."
    cd noc-billing-pro && git pull origin main
else
    git clone https://github.com/afani-arba/noc-billing-pro.git
    cd noc-billing-pro
fi

# Generate .env
info "  Mengkonfigurasi file .env Backend..."
IP_VPS=$(curl -s --max-time 5 ifconfig.me 2>/dev/null || hostname -I | awk '{print $1}')
JWT_SECRET=$(cat /dev/urandom | tr -dc 'a-zA-Z0-9' | fold -w 32 | head -n 1)

if [ ! -f "backend/.env" ]; then
    if [ -f "backend/.env.example" ]; then
        cp backend/.env.example backend/.env
        sed -i "s/GANTI_DENGAN_SECRET_KEY_64_KARAKTER_RANDOM/${JWT_SECRET}/g" backend/.env
        ok "  backend/.env berhasil dibuat dari template."
    else
        cat > backend/.env <<ENVEOF
MONGO_URI=mongodb://mongodb:27017/nocbillingpro
SECRET_KEY=${JWT_SECRET}
APP_EDITION=billing_pro
ENABLE_SYSLOG=true
ENABLE_POLLING=true
ENABLE_GENIEACS_SYNC=true
GENIEACS_URL=http://genieacs-nbi:7557
GENIEACS_USERNAME=admin
GENIEACS_PASSWORD=admin
ENVEOF
        ok "  backend/.env berhasil dibuat manual."
    fi
else
    warn "  backend/.env sudah ada, dilewati."
fi

# Konfigurasi UFW Firewall
info "  Mengkonfigurasi Firewall (UFW)..."
/usr/sbin/ufw allow ssh
/usr/sbin/ufw allow 80/tcp
/usr/sbin/ufw allow 443/tcp
/usr/sbin/ufw allow 8000/tcp
/usr/sbin/ufw allow 8002/tcp
/usr/sbin/ufw allow 7547/tcp
/usr/sbin/ufw allow 5142/udp
echo "y" | /usr/sbin/ufw enable
ok "  Firewall dikonfigurasi."

# GenieACS CSS
info "  Menyiapkan file konfigurasi GenieACS..."
if [ ! -s "genieacs/app-custom.css" ]; then
    if [ -f "genieacs/app-original.css" ]; then
        cp genieacs/app-original.css genieacs/app-custom.css
    else
        mkdir -p genieacs && touch genieacs/app-custom.css
    fi
    ok "  genieacs/app-custom.css siap (disalin dari template)."
else
    ok "  genieacs/app-custom.css sudah ada dan memiliki isian."
fi

# Build & Run
info "  Membangun dan menjalankan Docker containers..."
docker compose up --build -d && ok "  Docker containers berjalan." || fail "  Docker compose gagal!"

info "  Mengimpor konfigurasi dan UI template ke GenieACS..."
if [ -f "genieacs/import_genieacs.sh" ]; then
    bash genieacs/import_genieacs.sh || warn "  Gagal mengimpor konfigurasi GenieACS."
else
    warn "  Script import_genieacs.sh tidak ditemukan."
fi

# ─────────────────────────────────────────────────────────────
# SELESAI
# ─────────────────────────────────────────────────────────────
echo ""
echo "========================================================="
echo -e " ${GREEN}INSTALASI SELESAI! 🎉${NC}"
echo "========================================================="
echo " Semua komponen yang berhasil diinstall:"
command -v cloudflared &>/dev/null && echo "  ✅ Cloudflared Tunnel" || echo "  ⚠️  Cloudflared (skip)"
command -v gobgp        &>/dev/null && echo "  ✅ GoBGP Router"       || echo "  ⚠️  GoBGP (skip)"
[ -d /opt/zapret ]                  && echo "  ✅ Zapret DPI Bypass"  || echo "  ⚠️  Zapret (skip)"
command -v docker       &>/dev/null && echo "  ✅ Docker"             || echo "  ❌ Docker (GAGAL)"
echo "---------------------------------------------------------"
echo "  Akses Dashboard  : http://${IP_VPS}"
echo "  URL TR-069 ONT   : http://${IP_VPS}:7547"
echo "========================================================="
echo ""
