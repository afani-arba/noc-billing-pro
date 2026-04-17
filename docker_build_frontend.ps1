$plink = "C:\Program Files\PuTTY\plink.exe"
$pscp  = "C:\Program Files\PuTTY\pscp.exe"
$srv   = "10.125.125.238"
$user  = "noc"
$pass  = "123123"

function SSH([string]$cmd) {
    echo y | & $plink -ssh "$user@$srv" -pw $pass -batch $cmd 2>&1
}

Write-Host "=== [1] Fix git ownership on server as root via docker ===" -ForegroundColor Cyan
# Use docker to fix git permissions since user 'noc' can't write to root-owned files
SSH "docker run --rm -v /opt/noc-billing-pro:/repo alpine/git -C /repo config --global --add safe.directory /repo 2>&1 || true"
SSH "docker run --rm -v /opt/noc-billing-pro:/repo alpine/git config --global --add safe.directory /repo && git -C /repo fetch origin main && git -C /repo reset --hard origin/main 2>&1 || echo 'git fix attempted'"

Write-Host "`n=== [2] Pull latest code using docker run ===" -ForegroundColor Cyan
SSH "docker run --rm -v /opt/noc-billing-pro:/repo -w /repo --entrypoint sh alpine/git -c 'git config --global --add safe.directory /repo && git fetch origin main && git reset --hard origin/main && echo PULLED_OK' 2>&1"

Write-Host "`n=== [3] Build frontend in Docker node container ===" -ForegroundColor Cyan
Write-Host "Building frontend in Docker (may take 3-5 minutes)..." -ForegroundColor Yellow
SSH "docker run --rm -v /opt/noc-billing-pro/frontend:/app -w /app node:20-alpine sh -c 'rm -rf build && npm install --silent && npm run build 2>&1 | tail -20 && echo BUILD_OK' 2>&1"

Write-Host "`n=== [4] Check build result ===" -ForegroundColor Cyan
SSH "ls /opt/noc-billing-pro/frontend/build/ 2>&1 | head -10"

Write-Host "`n=== [5] Inject built assets into running Nginx container ===" -ForegroundColor Cyan
SSH "docker cp /opt/noc-billing-pro/frontend/build/. noc-billing-pro-frontend:/usr/share/nginx/html/ && echo 'INJECT_OK'"
SSH "docker exec noc-billing-pro-frontend nginx -s reload && echo 'NGINX_RELOAD_OK'"

Write-Host "`n=== [6] Inject backend Python changes into backend container ===" -ForegroundColor Cyan
Write-Host "Injecting updated backend files (auth, routers)..." -ForegroundColor Yellow
SSH "docker cp /opt/noc-billing-pro/backend/core/auth.py noc-billing-pro-backend:/app/core/auth.py && echo 'auth OK'"
SSH "docker cp /opt/noc-billing-pro/backend/routers/admin.py noc-billing-pro-backend:/app/routers/admin.py && echo 'admin OK'"
SSH "docker cp /opt/noc-billing-pro/backend/routers/billing.py noc-billing-pro-backend:/app/routers/billing.py && echo 'billing OK'"
SSH "docker cp /opt/noc-billing-pro/backend/routers/customers.py noc-billing-pro-backend:/app/routers/customers.py && echo 'customers OK'"
SSH "docker cp /opt/noc-billing-pro/backend/routers/hotspot.py noc-billing-pro-backend:/app/routers/hotspot.py && echo 'hotspot OK'"
SSH "docker cp /opt/noc-billing-pro/backend/routers/pppoe_monitoring.py noc-billing-pro-backend:/app/routers/pppoe_monitoring.py && echo 'pppoe OK'"
SSH "docker cp /opt/noc-billing-pro/backend/routers/genieacs.py noc-billing-pro-backend:/app/routers/genieacs.py && echo 'genieacs OK'"
SSH "docker restart noc-billing-pro-backend && echo 'BACKEND_RESTARTED'"

Write-Host "`n=== [7] Final verification ===" -ForegroundColor Cyan
SSH "docker exec noc-billing-pro-frontend ls /usr/share/nginx/html/"
Start-Sleep -Seconds 5
SSH "docker exec noc-billing-pro-backend python3 -c 'from core.auth import VALID_ROLES; print(\"Roles:\", VALID_ROLES)'"

Write-Host "`n=== DONE ===" -ForegroundColor Green
