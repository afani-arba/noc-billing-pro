#!/bin/bash
sed -i "s/FWTYPE=nftables/FWTYPE=iptables/g" /opt/zapret/config
systemctl restart zapret
/sbin/iptables-save | grep zapret
