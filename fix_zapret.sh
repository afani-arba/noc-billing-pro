#!/bin/bash
# Fix zapret config
cat > /opt/zapret/config << 'EOF'
# ===================================================================
# ZAPRET CONFIGURATION FOR INDONESIAN BROADBAND ISPs
# ===================================================================

# MODE: nfqws, tpws, tpws-socks, filter, custom
MODE=nfqws
DISABLE_IPV4=0
DISABLE_IPV6=1
FWTYPE=iptables

# NFQWS settings - WAJIB ada NFQWS_ENABLE=1 agar daemon jalan
NFQWS_ENABLE=1
NFQWS_PORTS_TCP=80,443
NFQWS_PORTS_UDP=443

# DPI Bypass strategy - Universal untuk semua ISP Indonesia
NFQWS_OPT="--dpi-desync=disorder2 --dpi-desync-split-pos=2 --dpi-desync-ttl=4"

# Filter mode: none = bypass all traffic (tanpa host filter)
MODE_FILTER=none
EOF
echo "Config written:"
cat /opt/zapret/config

# Fix systemd service - tambahkan PATH environment
cat > /etc/systemd/system/zapret.service << 'EOF'
[Unit]
Description=Zapret DPI Bypass
After=network-online.target
Wants=network-online.target

[Service]
Type=forking
Restart=no
TimeoutSec=60sec
IgnoreSIGPIPE=no
KillMode=none
GuessMainPID=no
RemainAfterExit=yes
Environment="PATH=/usr/sbin:/sbin:/usr/bin:/bin"
ExecStart=/opt/zapret/init.d/sysv/zapret start
ExecStop=/opt/zapret/init.d/sysv/zapret stop

[Install]
WantedBy=multi-user.target
EOF
echo "Service file written"

# Reload dan start
systemctl daemon-reload
systemctl stop zapret 2>/dev/null || true
sleep 1
systemctl start zapret
sleep 2
systemctl status zapret --no-pager
echo "---"
pgrep -la nfqws 2>&1 || echo "nfqws not running"
pgrep -la tpws 2>&1 || echo "tpws not running"
