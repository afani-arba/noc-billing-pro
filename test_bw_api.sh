#!/bin/bash
echo "=== Test API /dashboard/bandwidth-history ==="

# Get token untuk auth
TOKEN=$(curl -s -X POST http://localhost:8002/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username":"admin","password":"admin123"}' | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('access_token',''))")

echo "Token: ${TOKEN:0:40}..."

# Test bandwidth-history untuk device specific
DEVICE_ID="9df0a9d8-176a-4427-b54c-27ae66cc05a3"
echo ""
echo "=== Device: R. Dure-Sipin (1h) ==="
curl -s "http://localhost:8002/api/dashboard/bandwidth-history?device_id=${DEVICE_ID}&range=1h" \
  -H "Authorization: Bearer $TOKEN" | python3 -c "
import sys, json
data = json.load(sys.stdin)
print('Total points:', len(data))
non_zero = [d for d in data if d.get('download',0)>0 or d.get('upload',0)>0]
print('Non-zero points:', len(non_zero))
if non_zero:
    print('First non-zero sample:', json.dumps(non_zero[0]))
    print('Last non-zero sample:', json.dumps(non_zero[-1]))
elif len(data) > 0:
    print('First point (all zero):', json.dumps(data[0]))
    print('Last point (all zero):', json.dumps(data[-1]))
else:
    print('EMPTY RESPONSE')
"

echo ""
echo "=== All devices (no device_id, 1h) ==="
curl -s "http://localhost:8002/api/dashboard/bandwidth-history?range=1h" \
  -H "Authorization: Bearer $TOKEN" | python3 -c "
import sys, json
data = json.load(sys.stdin)
print('Total points:', len(data))
non_zero = [d for d in data if d.get('download',0)>0 or d.get('upload',0)>0]
print('Non-zero points:', len(non_zero))
if non_zero:
    print('Sample:', json.dumps(non_zero[:2]))
"

echo ""
echo "=== Dashboard stats (download + upload live) ==="
curl -s "http://localhost:8002/api/dashboard/stats?device_id=${DEVICE_ID}" \
  -H "Authorization: Bearer $TOKEN" | python3 -c "
import sys, json
data = json.load(sys.stdin)
print('total_bandwidth:', data.get('total_bandwidth'))
td = data.get('traffic_data', [])
print('traffic_data points:', len(td))
non_zero = [d for d in td if d.get('download',0)>0]
print('Non-zero traffic_data:', len(non_zero))
if non_zero:
    print('Last 3:', json.dumps(non_zero[-3:]))
"
