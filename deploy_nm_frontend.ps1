$plink = "C:\Program Files\PuTTY\plink.exe"
$srv   = "10.125.125.235"
$user  = "noc"
$pass  = "123123"

function SSH([string]$cmd) {
    Write-Host "  CMD: $cmd" -ForegroundColor DarkGray
    $r = echo y | & $plink -ssh "$user@$srv" -pw $pass -batch $cmd 2>&1
    Write-Host $r
}

Write-Host "[1] Build frontend via docker run node:20-alpine..." -ForegroundColor Yellow
$buildCmd = "echo $pass | sudo -S docker run --rm -v /opt/noc-billing-pro/frontend:/app -w /app node:20-alpine sh -c 'npm ci && npm run build 2>&1 | tail -30'"
SSH $buildCmd

Write-Host "[2] Copy dist ke nginx container..." -ForegroundColor Yellow
SSH "echo $pass | sudo -S docker cp /opt/noc-billing-pro/frontend/dist/. noc-billing-pro-frontend:/usr/share/nginx/html/"

Write-Host "[3] Reload nginx..." -ForegroundColor Yellow
SSH "echo $pass | sudo -S docker exec noc-billing-pro-frontend nginx -s reload && echo 'NGINX RELOADED OK'"

Write-Host "[4] Container status..." -ForegroundColor Cyan
SSH "echo $pass | sudo -S docker ps --format 'table {{.Names}}\t{{.Status}}' | grep noc"

Write-Host "`n================================================================" -ForegroundColor Green
Write-Host "  FRONTEND DEPLOY SELESAI! http://$($srv):8082/network-map" -ForegroundColor Green
Write-Host "================================================================" -ForegroundColor Green
