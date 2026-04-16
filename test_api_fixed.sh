#!/bin/bash
# Test with correct token field name
echo "=== Login ==="
RESP=$(curl -s -X POST http://localhost:8002/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username":"admin","password":"TestPwd2024!"}')
echo "$RESP" | python3 -c "import sys,json; d=json.load(sys.stdin); print('Keys:', list(d.keys()))"

# Extract using 'token' key (not 'access_token')
TVAL=$(echo "$RESP" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('token','') or d.get('access_token',''))")
echo "Token length: ${#TVAL}"

echo ""
echo "=== Test bandwidth-history ==="
RES=$(curl -s "http://localhost:8002/api/dashboard/bandwidth-history?device_id=9df0a9d8-176a-4427-b54c-27ae66cc05a3&range=1h" \
  -H "Authorization: Bearer $TVAL")
echo "$RES" | python3 -c "
import sys, json
raw = sys.stdin.read()
try:
    data = json.loads(raw)
    if isinstance(data, list):
        print('Total points:', len(data))
        nonzero = [d for d in data if isinstance(d,dict) and (d.get('download',0)>0 or d.get('upload',0)>0)]
        print('Non-zero points:', len(nonzero))
        if nonzero:
            print('Last 2 non-zero:')
            for p in nonzero[-2:]:
                print(' ', p)
        elif data:
            print('All zero. First point:', data[0])
    else:
        print('Type:', type(data))
        print('Value:', str(data)[:400])
except Exception as e:
    print('Error:', e, '| RAW:', raw[:400])
"

echo ""
echo "=== Test dashboard/stats ==="
curl -s "http://localhost:8002/api/dashboard/stats?device_id=9df0a9d8-176a-4427-b54c-27ae66cc05a3" \
  -H "Authorization: Bearer $TVAL" | python3 -c "
import sys, json
raw = sys.stdin.read()
try:
    d = json.loads(raw)
    print('total_bandwidth:', d.get('total_bandwidth'))
    td = d.get('traffic_data', [])
    print('traffic_data count:', len(td))
    nonzero = [x for x in td if x.get('download',0)>0]
    print('traffic_data non-zero:', len(nonzero))
    if nonzero:
        print('Last non-zero:', nonzero[-1])
except Exception as e:
    print('Error:', e, '| RAW:', raw[:400])
"

echo ""
echo "=== Restore original password ==="
docker exec noc-billing-pro-backend python3 -c "
from core.auth import pwd_context
from pymongo import MongoClient
client = MongoClient('mongodb://mongodb:27017/nocbillingpro')
db = client.nocbillingpro
result = db.admin_users.update_one({'username': 'admin'}, {'\$set': {'password': pwd_context.hash('admin123')}})
print('Password restored, modified:', result.modified_count)
"
