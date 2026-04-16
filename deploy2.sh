#!/bin/bash
echo "=== Deploy devices.py to container ==="
docker cp /tmp/devices_patched.py noc-billing-pro-backend:/app/routers/devices.py

echo "=== Verify forward-fill ==="
docker exec noc-billing-pro-backend grep -c "forward-fill" /app/routers/devices.py

echo "=== Restart backend ==="
docker restart noc-billing-pro-backend
sleep 8

echo "=== Health check ==="
curl -sf http://localhost:8002/api/system/health
echo ""
echo "Backend deploy DONE"
