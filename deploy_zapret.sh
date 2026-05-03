#!/bin/bash
set -e
echo "1. Replacing ZapretPage.jsx"
cp /tmp/ZapretPage.jsx /opt/noc-billing-pro/frontend/src/pages/ZapretPage.jsx

echo "2. Building frontend via Docker Node"
cd /opt/noc-billing-pro/frontend
docker run --rm -v /opt/noc-billing-pro/frontend:/app -w /app node:20-alpine sh -c "npm install && npm run build"

echo "3. Deploying to Nginx"
docker cp /opt/noc-billing-pro/frontend/build/. noc-billing-pro-frontend:/usr/share/nginx/html/

echo "4. Reloading Nginx"
docker exec noc-billing-pro-frontend nginx -s reload

echo "DEPLOY_OK"
