#!/usr/bin/env bash
# Install NOC Billing Pro SSTP Agent di Ubuntu LXC Host
# Jalankan sekali saja: sudo bash install_sstp_agent.sh

set -e
echo "=== NOC Billing Pro SSTP Agent Installer ==="

# 1. Install dependencies
echo "[1/4] Installing sstp-client and pppd..."
apt-get update -q
apt-get install -y sstp-client ppp

# 2. Deploy agent
echo "[2/4] Deploying agent..."
mkdir -p /opt/sstp-agent
cp sstp_agent.py /opt/sstp-agent/sstp_agent.py
chmod 755 /opt/sstp-agent/sstp_agent.py

# 3. Install systemd service
echo "[3/4] Installing systemd service..."
cp sstp-agent.service /etc/systemd/system/sstp-agent.service
systemctl daemon-reload
systemctl enable sstp-agent
systemctl restart sstp-agent

# 4. Verify
echo "[4/4] Verifying..."
sleep 2
systemctl is-active sstp-agent && echo "✅ SSTP Agent running!" || echo "❌ Failed to start"
curl -s http://127.0.0.1:8001/health && echo

echo ""
echo "=== Install Selesai ==="
echo "Test: curl http://127.0.0.1:8001/status"
echo "Log:  journalctl -u sstp-agent -f"
