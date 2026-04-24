#!/bin/bash
PORT=8002
TOKEN=$(curl -s -X POST http://localhost:$PORT/api/auth/login \
  -H 'Content-Type: application/json' \
  --data-raw '{"username":"admin","password":"admin123"}' | \
  python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('access_token','NO_TOKEN'))")

echo "Token: ${TOKEN:0:30}..."
echo "=== Endpoint Verification ==="

curl -s -o /dev/null -w "GET /hotspot-analytics     : HTTP %{http_code}\n" \
  http://localhost:$PORT/api/hotspot-analytics \
  -H "Authorization: Bearer $TOKEN"

curl -s -o /dev/null -w "GET /hotspot-vouchers/export: HTTP %{http_code}\n" \
  "http://localhost:$PORT/api/hotspot-vouchers/export" \
  -H "Authorization: Bearer $TOKEN"

echo ""
echo "=== Backend Logs (errors only) ==="
docker logs noc-billing-pro-backend --tail 5 2>&1 | grep -i "error\|ERROR" || echo "No errors"
echo "=== Done ==="
