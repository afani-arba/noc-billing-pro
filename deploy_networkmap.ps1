$plink = "C:\Program Files\PuTTY\plink.exe"
$srv   = "10.125.125.235"
$user  = "noc"
$pass  = "123123"
$remote = "/opt/noc-billing-pro"

function SSH([string]$cmd) {
    Write-Host "  >> $cmd" -ForegroundColor DarkGray
    $result = echo y | & $plink -ssh "$user@$srv" -pw $pass -batch $cmd 2>&1
    Write-Host $result
}

Write-Host "`n[1/6] Git pull di server..." -ForegroundColor Yellow
SSH "echo $pass | sudo -S bash -c 'cd $remote && git pull origin main 2>&1'"

Write-Host "`n[2/6] Copy backend files ke container..." -ForegroundColor Yellow
SSH "echo $pass | sudo -S docker cp $remote/backend/routers/network_map.py noc-billing-pro-backend:/app/routers/network_map.py"
SSH "echo $pass | sudo -S docker cp $remote/backend/server.py noc-billing-pro-backend:/app/server.py"

Write-Host "`n[3/6] Syntax check Python..." -ForegroundColor Yellow
SSH "echo $pass | sudo -S docker exec noc-billing-pro-backend python3 -m py_compile /app/routers/network_map.py && echo 'network_map.py OK'"
SSH "echo $pass | sudo -S docker exec noc-billing-pro-backend python3 -m py_compile /app/server.py && echo 'server.py OK'"

Write-Host "`n[4/6] Restart backend..." -ForegroundColor Yellow
SSH "echo $pass | sudo -S docker restart noc-billing-pro-backend"
Start-Sleep -Seconds 8

Write-Host "`n[5/6] Build frontend di server..." -ForegroundColor Yellow
SSH "echo $pass | sudo -S bash -c 'cd $remote/frontend && npm run build 2>&1 | tail -25'"

Write-Host "`n[6/6] Copy dist ke nginx & reload..." -ForegroundColor Yellow
SSH "echo $pass | sudo -S docker cp $remote/frontend/dist/. noc-billing-pro-frontend:/usr/share/nginx/html/"
SSH "echo $pass | sudo -S docker exec noc-billing-pro-frontend nginx -s reload && echo 'NGINX RELOADED'"

Write-Host "`n--- Container Status ---" -ForegroundColor Cyan
SSH "echo $pass | sudo -S docker ps --format 'table {{.Names}}\t{{.Status}}' | grep noc"

Write-Host "`n--- Backend Logs (last 15) ---" -ForegroundColor Cyan
SSH "echo $pass | sudo -S docker logs noc-billing-pro-backend --tail 15 2>&1"

Write-Host "`n================================================================" -ForegroundColor Green
Write-Host "  DEPLOY SELESAI! http://$($srv):8082/network-map" -ForegroundColor Green
Write-Host "================================================================" -ForegroundColor Green
