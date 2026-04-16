#!/bin/bash
echo "=== IP PPP1 ==="
ip a show ppp1
echo ""
echo "=== IP XL2TPD CONF ==="
grep -E 'local ip|ip range' /etc/xl2tpd/xl2tpd.conf
cat /etc/ppp/options.l2tp.server
echo ""
echo "=== ROUTING ==="
ip route | grep ppp
echo ""
echo "=== IPTABLES NAT ==="
iptables -t nat -L -n -v | grep 5142
echo ""
echo "=== IPTABLES FILTER ==="
iptables -L -n -v | grep 5142
echo ""
echo "=== TCPDUMP PPP1 ==="
timeout 20 tcpdump -i ppp1 udp port 5142 -n -A
