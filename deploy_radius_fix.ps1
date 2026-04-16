$plink = "C:\Program Files\PuTTY\plink.exe"
$srv = "10.125.125.238"; $user = "noc"; $pass = "123123"
function SSH([string]$cmd) { echo y | & $plink -ssh "$user@$srv" -pw $pass -batch $cmd 2>&1 }

Write-Host "=== 1. Git pull code from GitHub ===" -ForegroundColor Cyan
SSH "docker run --rm -v /opt/noc-billing-pro:/ws bitnami/git:latest sh -c 'cd /ws && git config --global --add safe.directory /ws && git fetch origin main && git reset --hard origin/main && echo PULLED_OK'"

Write-Host "`n=== 2. Hotswap Python files ===" -ForegroundColor Cyan
SSH "docker exec noc-billing-pro-backend sh -c 'cp -r /app-host/backend/* /app/ && chown -R root:root /app'"

Write-Host "`n=== 3. Restart Backend ===" -ForegroundColor Cyan
SSH "docker restart noc-billing-pro-backend"

Write-Host "`n=== 4. Build Frontend ===" -ForegroundColor Cyan
SSH "docker run --rm -v /opt/noc-billing-pro/frontend:/app -w /app node:20-alpine sh -c 'npm install --silent && npx vite build && echo BUILD_OK'"

Write-Host "`n=== 5. Inject to Nginx ===" -ForegroundColor Cyan
SSH "docker cp /opt/noc-billing-pro/frontend/build/. noc-billing-pro-frontend:/usr/share/nginx/html/ && echo INJECTED"
SSH "docker exec noc-billing-pro-frontend nginx -s reload && echo NGINX_RELOADED"

Write-Host "`n=== FULL DEPLOY COMPLETE ===" -ForegroundColor Green
