#!/bin/bash
set -e

echo "=== [1] Deploy Backend: zapret.py ==="
cp /tmp/zapret.py /opt/noc-billing-pro/backend/routers/zapret.py
docker cp /opt/noc-billing-pro/backend/routers/zapret.py noc-billing-pro-backend:/app/routers/zapret.py
echo "zapret.py injected to backend container"

echo ""
echo "=== [2] Restart Backend Container ==="
docker restart noc-billing-pro-backend
echo "Waiting for backend to come up..."
sleep 5

echo ""
echo "=== [3] Verify backend is running ==="
docker exec noc-billing-pro-backend python3 -m py_compile /app/routers/zapret.py && echo "zapret.py: syntax OK"

echo ""
echo "=== [4] Deploy Frontend: ZapretPage.jsx ==="
cp /tmp/ZapretPage.jsx /opt/noc-billing-pro/frontend/src/pages/ZapretPage.jsx
docker run --rm -v /opt/noc-billing-pro/frontend:/app -w /app node:20-alpine sh -c "npm run build"

echo ""
echo "=== [5] Inject frontend build to Nginx ==="
docker cp /opt/noc-billing-pro/frontend/build/. noc-billing-pro-frontend:/usr/share/nginx/html/
docker exec noc-billing-pro-frontend nginx -s reload

echo ""
echo "=== DEPLOY COMPLETE ==="
