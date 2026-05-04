$plink = "C:\Program Files\PuTTY\plink.exe"
$srv   = "10.125.125.235"
$user  = "noc"
$pass  = "123123"

function SSH([string]$cmd) {
    Write-Host "  CMD: $cmd" -ForegroundColor DarkGray
    $r = echo y | & $plink -ssh "$user@$srv" -pw $pass -batch $cmd 2>&1
    Write-Host $r
}

Write-Host "[1] Verify build/assets ada..." -ForegroundColor Yellow
SSH "ls -la /opt/noc-billing-pro/frontend/build/assets/ 2>&1 | tail -5"

Write-Host "[2] Copy build/ ke nginx container..." -ForegroundColor Yellow
SSH "echo $pass | sudo -S docker cp /opt/noc-billing-pro/frontend/build/. noc-billing-pro-frontend:/usr/share/nginx/html/ 2>&1"

Write-Host "[3] Reload nginx..." -ForegroundColor Yellow
SSH "echo $pass | sudo -S docker exec noc-billing-pro-frontend nginx -s reload && echo 'NGINX RELOADED'"

Write-Host "[4] Verify NetworkMapPage in nginx..." -ForegroundColor Yellow
SSH "echo $pass | sudo -S docker exec noc-billing-pro-frontend ls /usr/share/nginx/html/assets/ 2>&1 | grep -i NetworkMap"

Write-Host "[5] Container status..." -ForegroundColor Cyan
SSH "echo $pass | sudo -S docker ps --format 'table {{.Names}}\t{{.Status}}' | grep noc"

Write-Host "`n============================================" -ForegroundColor Green
Write-Host "  FRONTEND LIVE: http://$($srv):8082/network-map" -ForegroundColor Green
Write-Host "============================================" -ForegroundColor Green
