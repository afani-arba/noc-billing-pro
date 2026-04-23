#!/bin/bash
set -e

# Memastikan PATH memuat direktori sbin agar dpkg/apt berjalan lancar di Debian
export PATH=$PATH:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin

echo "========================================================="
echo "   Auto-Installer Ultimate NOC Billing Pro (Debian 12)   "
echo "========================================================="
echo ""

# Pastikan script dijalankan sebagai root
if [ "$EUID" -ne 0 ]; then 
  echo "Tolong jalankan script ini sebagai root (gunakan sudo)"
  exit 1
fi

# 1. Update OS & Install Dependensi Dasar
echo ">>> [1/6] Mengupdate sistem dan dependensi inti..."
apt-get update && apt-get upgrade -y
apt-get install -y git curl wget ufw nano apt-transport-https ca-certificates software-properties-common gnupg2 procps util-linux

# 2. Install VPN Clients (SSTP, L2TP, IPsec) & Network Tools
echo ">>> [2/6] Menginstall VPN Clients (SSTP, L2TP/IPsec) dan Network Tools..."
apt-get install -y sstp-client ppp xl2tpd strongswan iproute2 iptables kmod traceroute iputils-ping

# 3. Install Cloudflared (Cloudflare Tunnel)
echo ">>> [3/6] Menginstall Cloudflared..."
if ! command -v cloudflared &> /dev/null; then
    curl -L --output cloudflared.deb https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64.deb
    dpkg -i cloudflared.deb
    rm cloudflared.deb
else
    echo "Cloudflared sudah terinstall."
fi

# 4. Install GoBGP
echo ">>> [4/6] Menginstall GoBGP..."
if ! command -v gobgp &> /dev/null; then
    wget -q https://github.com/osrg/gobgp/releases/download/v3.26.0/gobgp_3.26.0_linux_amd64.tar.gz
    tar -xzf gobgp_3.26.0_linux_amd64.tar.gz
    mv gobgp /usr/local/bin/
    mv gobgpd /usr/local/bin/
    rm -f gobgp_3.26.0_linux_amd64.tar.gz
else
    echo "GoBGP sudah terinstall."
fi

# 5. Install Docker & Docker Compose
echo ">>> [5/6] Menginstall Docker & Docker Compose..."
if ! command -v docker &> /dev/null; then
    curl -fsSL https://get.docker.com -o get-docker.sh
    sh get-docker.sh
    systemctl enable docker
    systemctl start docker
    apt-get install -y docker-compose-plugin
    rm -f get-docker.sh
else
    echo "Docker sudah terinstall."
fi

# 6. Setup Repository & Deploy NOC Billing Pro
echo ">>> [6/6] Melakukan Clone Repository..."

cd /opt
if [ -d "noc-billing-pro" ]; then
    echo "Directory noc-billing-pro sudah ada. Mengambil pembaruan terbaru..."
    cd noc-billing-pro
    git pull origin main
else
    git clone https://github.com/afani-arba/noc-billing-pro.git
    cd noc-billing-pro
fi

echo ">>> Mengkonfigurasi file .env Backend..."
IP_VPS=$(curl -s ifconfig.me || echo "127.0.0.1")
JWT_SECRET=$(cat /dev/urandom | tr -dc 'a-zA-Z0-9' | fold -w 32 | head -n 1)

if [ ! -f "backend/.env" ]; then
    if [ -f "backend/.env.example" ]; then
        cp backend/.env.example backend/.env
        sed -i "s/GANTI_DENGAN_SECRET_KEY_64_KARAKTER_RANDOM/${JWT_SECRET}/g" backend/.env
        echo "File backend/.env berhasil di-generate dari template."
    else
        # Fallback jika .env.example tidak ada
        cat > backend/.env <<EOF
MONGO_URI=mongodb://mongodb:27017/nocbillingpro
SECRET_KEY=${JWT_SECRET}
APP_EDITION=billing_pro
ENABLE_SYSLOG=true
ENABLE_POLLING=true
ENABLE_GENIEACS_SYNC=true
GENIEACS_URL=http://genieacs-nbi:7557
GENIEACS_USERNAME=admin
GENIEACS_PASSWORD=admin
EOF
        echo "File backend/.env berhasil dibuat manual."
    fi
else
    echo "File backend/.env sudah ada. Melewati pembuatan .env..."
fi

echo ">>> Mengkonfigurasi Firewall (UFW)..."
ufw allow ssh
ufw allow 80/tcp
ufw allow 443/tcp
ufw allow 8000/tcp
ufw allow 8002/tcp
ufw allow 7547/tcp
ufw allow 5142/udp
echo "y" | ufw enable

echo ">>> Membangun dan menjalankan NOC Billing Pro (Backend, Frontend, GenieACS)..."
docker compose up --build -d

echo "========================================================="
echo " INSTALASI SELESAI! 🎉"
echo "========================================================="
echo "Semua dependensi Host telah terinstall:"
echo "- SSTP & L2TP/IPsec Clients"
echo "- Cloudflared Tunnel"
echo "- GoBGP (v3.26.0)"
echo "- Docker & NOC Billing Pro Containerized Services"
echo "---------------------------------------------------------"
echo "Akses Dashboard  : http://${IP_VPS}"
echo "URL TR-069 ONT   : http://${IP_VPS}:7547"
echo "========================================================="
