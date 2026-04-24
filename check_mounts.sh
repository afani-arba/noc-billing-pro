#!/bin/bash
echo "=== Backend Mounts ==="
sudo docker inspect noc-billing-pro-backend 2>&1 | python3 -c "
import sys, json
d = json.load(sys.stdin)
mounts = d[0].get('Mounts', [])
for m in mounts:
    print(m.get('Source',''), '->', m.get('Destination',''))
"

echo ""
echo "=== hotspot.py location in container ==="
sudo docker exec noc-billing-pro-backend find / -name hotspot.py 2>/dev/null | grep -v proc

echo ""
echo "=== Lines in container hotspot.py ==="
sudo docker exec noc-billing-pro-backend wc -l /app/routers/hotspot.py 2>/dev/null || \
  sudo docker exec noc-billing-pro-backend find / -name hotspot.py -exec wc -l {} \; 2>/dev/null | head -3
