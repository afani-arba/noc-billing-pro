#!/bin/bash
echo "=== Final Verification: Bandwidth History ==="

# Login
RESP=$(curl -s -X POST http://localhost:8002/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username":"admin","password":"TestPwd2024!"}')
TVAL=$(echo "$RESP" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('token','') or d.get('access_token',''))")
echo "Auth: ${#TVAL} chars"

echo ""
echo "=== 1h bandwidth-history (device R.Dure-Sipin) ==="
curl -s "http://localhost:8002/api/dashboard/bandwidth-history?device_id=9df0a9d8-176a-4427-b54c-27ae66cc05a3&range=1h" \
  -H "Authorization: Bearer $TVAL" | python3 -c "
import sys, json
data = json.loads(sys.stdin.read())
print('Total points:', len(data))
nz = [d for d in data if d.get('download',0)>0 or d.get('upload',0)>0]
print('Non-zero:', len(nz))
z = [d for d in data if d.get('download',0)==0 and d.get('upload',0)==0]
print('Zero (blank):', len(z))
if nz:
    print('Latest 3 non-zero:')
    for p in nz[-3:]:
        print(f'  {p[\"time\"]} | DL:{p[\"download\"]}Mbps | UL:{p[\"upload\"]}Mbps | ping:{p.get(\"ping\",0)}ms')
"

echo ""
echo "=== 24h bandwidth-history (device R.Dure-Sipin) ==="
curl -s "http://localhost:8002/api/dashboard/bandwidth-history?device_id=9df0a9d8-176a-4427-b54c-27ae66cc05a3&range=24h" \
  -H "Authorization: Bearer $TVAL" | python3 -c "
import sys, json
data = json.loads(sys.stdin.read())
print('Total points:', len(data))
nz = [d for d in data if d.get('download',0)>0 or d.get('upload',0)>0]
print('Non-zero:', len(nz))
if nz:
    print('Latest sample:', nz[-1])
"

echo ""
echo "=== 1h all-devices ==="
curl -s "http://localhost:8002/api/dashboard/bandwidth-history?range=1h" \
  -H "Authorization: Bearer $TVAL" | python3 -c "
import sys, json
data = json.loads(sys.stdin.read())
nz = [d for d in data if d.get('download',0)>0 or d.get('upload',0)>0]
print('Total:', len(data), '| Non-zero:', len(nz))
if nz: print('Latest:', nz[-1])
"

echo ""
echo "=== Restore password to admin123 ==="
docker exec noc-billing-pro-backend python3 -c "
from core.auth import pwd_context
from pymongo import MongoClient
db = MongoClient('mongodb://mongodb:27017/nocbillingpro').nocbillingpro
r = db.admin_users.update_one({'username': 'admin'}, {'\$set': {'password': pwd_context.hash('admin123')}})
print('Password restored:', r.modified_count)
"
