#!/bin/bash
if ! grep -q "INIT_APPLY_FW=1" /opt/zapret/config; then
    echo "INIT_APPLY_FW=1" >> /opt/zapret/config
fi
systemctl restart zapret
/sbin/iptables-save | grep NFQUEUE
