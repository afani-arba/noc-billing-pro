#!/bin/bash
echo "=== Copying fixed devices.py to container ==="
docker cp /tmp/devices_patched.py noc-billing-pro-backend:/app/routers/devices.py

echo ""
echo "=== Verify null fill ==="
docker exec noc-billing-pro-backend grep -A6 "Slot kosong" /app/routers/devices.py

echo ""
echo "=== Sending SIGHUP to reload (graceful) ==="
docker restart noc-billing-pro-backend

echo "Waiting 8s for startup..."
sleep 8

echo ""
echo "=== Health check ==="
curl -sf http://localhost:8002/api/system/health && echo "Backend OK" || echo "Backend FAIL"
