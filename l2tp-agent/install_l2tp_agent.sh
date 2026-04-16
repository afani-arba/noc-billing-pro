#!/usr/bin/env bash
# Install NOC Billing Pro L2TP Agent di Ubuntu Host
# Jalankan: sudo bash install_l2tp_agent.sh

set -e
echo "=== NOC Billing Pro L2TP Agent Installer ==="

# 1. Install dependencies
echo "[1/4] Installing xl2tpd and ppp..."
apt-get update -q
apt-get install -y xl2tpd ppp

# 2. Deploy agent
echo "[2/4] Deploying agent..."
mkdir -p /opt/l2tp-agent
cp l2tp_agent.py /opt/l2tp-agent/l2tp_agent.py
chmod 755 /opt/l2tp-agent/l2tp_agent.py

# 3. Install systemd service
echo "[3/4] Installing systemd service..."
cp l2tp-agent.service /etc/systemd/system/l2tp-agent.service
systemctl daemon-reload
systemctl enable l2tp-agent
systemctl restart l2tp-agent

# 4. Verify
echo "[4/4] Verifying..."
sleep 2
systemctl is-active l2tp-agent && echo "✅ L2TP Agent running on port 8002!" || echo "❌ Failed to start"
curl -s http://127.0.0.1:8002/health && echo

echo ""
echo "=== Install Selesai ==="
echo "Test: curl http://127.0.0.1:8002/status"
echo "Log:  journalctl -u l2tp-agent -f"
