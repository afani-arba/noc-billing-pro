$plink = "C:\Program Files\PuTTY\plink.exe"
$pscp  = "C:\Program Files\PuTTY\pscp.exe"
$srv   = "10.125.125.238"
$user  = "noc"
$pass  = "123123"

function SSH([string]$cmd) {
    echo y | & $plink -ssh "$user@$srv" -pw $pass -batch $cmd 2>&1
}

Write-Host "=== Building frontend - npm install + npx vite build ===" -ForegroundColor Cyan
Write-Host "Running npm install and build in node:20-alpine..." -ForegroundColor Yellow

# Use npx vite build instead of npm run build so PATH doesn't matter
SSH "docker run --rm -v /opt/noc-billing-pro/frontend:/app -w /app node:20-alpine sh -c 'npm install --silent 2>&1 | tail -3 && npx vite build 2>&1 | tail -10 && echo BUILD_COMPLETE' 2>&1"

Write-Host "`n=== Check dist ===" -ForegroundColor Cyan
SSH "ls /opt/noc-billing-pro/frontend/dist/ 2>&1 | head -8"

Write-Host "`n=== Inject into Nginx container ===" -ForegroundColor Cyan
SSH "docker cp /opt/noc-billing-pro/frontend/dist/. noc-billing-pro-frontend:/usr/share/nginx/html/ && echo INJECTED"
SSH "docker exec noc-billing-pro-frontend nginx -s reload && echo NGINX_RELOADED"

Write-Host "`n=== Final check: BgpSteeringPage asset ===" -ForegroundColor Cyan
SSH "docker exec noc-billing-pro-frontend ls /usr/share/nginx/html/assets/ | grep Bgp"

Write-Host "`n=== DONE ===" -ForegroundColor Green
Write-Host "Please hard refresh browser: Ctrl+Shift+F5" -ForegroundColor Yellow
