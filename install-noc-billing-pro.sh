#!/bin/bash
set -e

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
echo ">>> [6/6] Kredensial untuk Clone Repository Private..."
read -p "Masukkan GitHub Username Anda: " GITHUB_USER
read -s -p "Masukkan GitHub Personal Access Token (PAT): " GITHUB_TOKEN
echo ""

cd /opt
if [ -d "noc-billing-pro" ]; then
    echo "Directory noc-billing-pro sudah ada. Mengambil pembaruan terbaru..."
    cd noc-billing-pro
    git pull origin main
else
    git clone https://${GITHUB_USER}:${GITHUB_TOKEN}@github.com/afani-arba/noc-billing-pro.git
    cd noc-billing-pro
fi

echo ">>> Mengkonfigurasi file .env..."
IP_VPS=$(curl -s ifconfig.me || echo "127.0.0.1")
JWT_SECRET=$(cat /dev/urandom | tr -dc 'a-zA-Z0-9' | fold -w 32 | head -n 1)

if [ ! -f ".env" ]; then
cat > .env <<EOF
# Auto-generated .env configuration
MONGO_URI=mongodb://noc-mongodb:27017/nocbillingpro
GENIEACS_MONGODB_CONNECTION_URL=mongodb://noc-mongodb:27017/genieacs
GENIEACS_CWMP_ACCESS_URL=http://${IP_VPS}:7547
SYSLOG_PORT=5142
PEERING_FLUSH=60
JWT_SECRET=${JWT_SECRET}
EOF
    echo "File .env berhasil dibuat."
else
    echo "File .env sudah ada. Melewati pembuatan .env..."
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
