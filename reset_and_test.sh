#!/bin/bash
# Reset admin password to known value and then test API
echo "=== Resetting admin password ==="
docker exec noc-billing-pro-backend python3 -c "
from core.auth import pwd_context
from pymongo import MongoClient
import os
client = MongoClient('mongodb://mongodb:27017/nocbillingpro')
db = client.nocbillingpro
new_hash = pwd_context.hash('TestPwd2024!')
result = db.admin_users.update_one({'username': 'admin'}, {'\$set': {'password': new_hash}})
print('Modified:', result.modified_count)
"

echo ""
echo "=== Test login with new password ==="
TOKEN=$(curl -s -X POST http://localhost:8002/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username":"admin","password":"TestPwd2024!"}')
echo "$TOKEN"

# Extract token  
TVAL=$(echo "$TOKEN" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('access_token','NO'))")
echo "Token length: ${#TVAL}"

echo ""
echo "=== Testing bandwidth-history API ==="
curl -s "http://localhost:8002/api/dashboard/bandwidth-history?device_id=9df0a9d8-176a-4427-b54c-27ae66cc05a3&range=1h" \
  -H "Authorization: Bearer $TVAL" | python3 -c "
import sys, json
raw = sys.stdin.read()
try:
    data = json.loads(raw)
    if isinstance(data, list):
        print('Points:', len(data))
        nonzero = [d for d in data if isinstance(d,dict) and (d.get('download',0)>0 or d.get('upload',0)>0)]
        print('Non-zero:', len(nonzero))
        if nonzero:
            print('Sample non-zero:', json.dumps(nonzero[-2:], indent=2))
        elif data:
            print('All zero sample:', json.dumps(data[-2:], indent=2))
    else:
        print('Not a list! RAW:', raw[:500])
except Exception as e:
    print('Parse error:', e)
    print('RAW:', raw[:500])
"
