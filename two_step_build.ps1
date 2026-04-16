$plink = "C:\Program Files\PuTTY\plink.exe"
$pscp  = "C:\Program Files\PuTTY\pscp.exe"
$srv   = "10.125.125.238"
$user  = "noc"
$pass  = "123123"

function SSH([string]$cmd) {
    echo y | & $plink -ssh "$user@$srv" -pw $pass -batch $cmd 2>&1
}

Write-Host "=== Step 1: Git pull as root via docker bitnami/git ===" -ForegroundColor Cyan
SSH "docker run --rm -v /opt/noc-billing-pro:/ws bitnami/git:latest sh -c 'cd /ws && git config --global --add safe.directory /ws && git fetch origin main && git reset --hard origin/main && echo PULLED_OK' 2>&1"

Write-Host "`n=== Step 2: Verify BgpSteeringPage.jsx updated ===" -ForegroundColor Cyan
$check = SSH "grep -c 'summaryRaw' /opt/noc-billing-pro/frontend/src/pages/BgpSteeringPage.jsx 2>&1"
Write-Host "summaryRaw occurrences: $check"

Write-Host "`n=== Step 3: Build with node:20-alpine (no git needed now) ===" -ForegroundColor Cyan
Write-Host "Building..." -ForegroundColor Yellow
SSH "docker run --rm -v /opt/noc-billing-pro/frontend:/app -w /app node:20-alpine sh -c 'npm ci --silent 2>&1 | tail -3 && npm run build 2>&1 | tail -8 && echo BUILD_OK' 2>&1"

Write-Host "`n=== Step 4: Check dist ===" -ForegroundColor Cyan
SSH "ls /opt/noc-billing-pro/frontend/dist/ 2>&1 | head -5"

Write-Host "`n=== Step 5: Inject and reload Nginx ===" -ForegroundColor Cyan
SSH "docker cp /opt/noc-billing-pro/frontend/dist/. noc-billing-pro-frontend:/usr/share/nginx/html/ 2>&1 && echo INJECTED"
SSH "docker exec noc-billing-pro-frontend nginx -s reload 2>&1 && echo NGINX_RELOADED"

Write-Host "`n=== Step 6: Final check ===" -ForegroundColor Cyan
SSH "docker exec noc-billing-pro-frontend ls /usr/share/nginx/html/assets/ | grep Bgp"
Write-Host "`n=== COMPLETED ===" -ForegroundColor Green
