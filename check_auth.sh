#!/bin/bash
echo "=== Admin users ==="
docker exec noc-billing-pro-mongodb mongosh nocbillingpro --quiet --eval \
  'db.admin_users.find({},{username:1,role:1,is_active:1}).forEach(u=>print(u.username, "|", u.role, "|", u.is_active))'

echo ""
echo "=== Test login ==="
curl -s -X POST http://localhost:8002/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username":"admin","password":"admin123"}'

echo ""
echo "=== Test login 2 ==="
curl -s -X POST http://localhost:8002/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username":"admin","password":"Admin123"}'
