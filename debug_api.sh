#!/bin/bash
echo "=== Test raw API response ==="

# Get token
TOKEN=$(curl -s -X POST http://localhost:8002/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username":"admin","password":"admin123"}' | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('access_token','NO_TOKEN'))")

echo "Auth token obtained: ${#TOKEN} chars"

echo ""
echo "=== RAW bandwidth-history response ==="
curl -v "http://localhost:8002/api/dashboard/bandwidth-history?device_id=9df0a9d8-176a-4427-b54c-27ae66cc05a3&range=1h" \
  -H "Authorization: Bearer $TOKEN" 2>&1 | tail -30

echo ""
echo "=== RAW dashboard/stats response ==="
curl -s "http://localhost:8002/api/dashboard/stats?device_id=9df0a9d8-176a-4427-b54c-27ae66cc05a3" \
  -H "Authorization: Bearer $TOKEN" 2>&1 | python3 -c "
import sys, json
raw = sys.stdin.read()
print('RAW (first 1000):', raw[:1000])
"
