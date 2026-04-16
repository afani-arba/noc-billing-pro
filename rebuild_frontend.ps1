$plink = "C:\Program Files\PuTTY\plink.exe"
$pscp  = "C:\Program Files\PuTTY\pscp.exe"
$srv   = "10.125.125.238"
$user  = "noc"
$pass  = "123123"

function SSH([string]$cmd) {
    echo y | & $plink -ssh "$user@$srv" -pw $pass -batch $cmd 2>&1
}

Write-Host "=== [1] Upload fixed BgpSteeringPage.jsx to server ===" -ForegroundColor Cyan
& $pscp -pw $pass -batch "e:\noc-billing-pro\frontend\src\pages\BgpSteeringPage.jsx" "${user}@${srv}:/tmp/BgpSteeringPage.jsx" 2>&1

Write-Host "`n=== [2] Copy into frontend container source ===" -ForegroundColor Cyan
SSH "docker cp /tmp/BgpSteeringPage.jsx noc-billing-pro-frontend:/usr/share/nginx/html/ 2>&1 || echo 'Checking frontend container structure...'"
SSH "docker exec noc-billing-pro-frontend ls /usr/share/nginx/html/ | head -10 2>&1"

Write-Host "`n=== [3] Check if frontend builds inside container or is pre-built ===" -ForegroundColor Cyan
SSH "docker exec noc-billing-pro-frontend ls /app/ 2>&1 || echo 'No /app - Nginx static'"
SSH "docker exec noc-billing-pro-frontend ls /usr/share/nginx/html/ | grep -E 'index|assets' 2>&1"

Write-Host "`n=== [4] Build frontend inside a new container with the fix ===" -ForegroundColor Cyan
Write-Host "Copying fixed source file into the right build location on server..." -ForegroundColor Yellow
SSH "cp /tmp/BgpSteeringPage.jsx /opt/noc-billing-pro/frontend/src/pages/BgpSteeringPage.jsx 2>&1 && echo 'Copied to source'"

Write-Host "`n=== [5] Run frontend build directly ===" -ForegroundColor Cyan
Write-Host "Building frontend (this may take 2-3 minutes)..." -ForegroundColor Yellow
SSH "cd /opt/noc-billing-pro && docker compose build noc-frontend 2>&1 | tail -20"

Write-Host "`n=== [6] Replace frontend container ===" -ForegroundColor Cyan
SSH "cd /opt/noc-billing-pro && docker compose up -d noc-frontend 2>&1"
Write-Host "Waiting 10s for startup..."
Start-Sleep -Seconds 10
SSH "docker ps --format 'table {{.Names}}\t{{.Status}}' | grep frontend"

Write-Host "`n=== DONE ===" -ForegroundColor Green
