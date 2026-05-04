$plink = "C:\Program Files\PuTTY\plink.exe"
$srv   = "10.125.125.235"
$user  = "noc"
$pass  = "123123"

function SSH([string]$cmd) {
    Write-Host "  CMD: $cmd" -ForegroundColor DarkGray
    $r = echo y | & $plink -ssh "$user@$srv" -pw $pass -batch $cmd 2>&1
    Write-Host $r
}

# Build output ke /opt folder saja (bukan /app/dist di dalam container)
# node_modules sudah ada di server (/opt/noc-billing-pro/frontend/node_modules)
# Gunakan node:20 (bukan alpine) agar kompatibel

Write-Host "[1] Check npm inside node_modules..." -ForegroundColor Yellow
SSH "ls /opt/noc-billing-pro/frontend/node_modules/.bin/vite 2>&1"

Write-Host "[2] Build with docker node:20 with correct output dir..." -ForegroundColor Yellow
# npm run build menghasilkan dist/ (Vite), bukan build/ (CRA)
# Jalankan dengan timeout lebih lama via nohup di background, log ke file
SSH "echo $pass | sudo -S docker run --rm -v /opt/noc-billing-pro/frontend:/app -w /app node:20 sh -c 'npm run build > /app/build_log.txt 2>&1 && echo BUILD_OK || echo BUILD_FAIL' 2>&1"

Write-Host "[3] Check build log..." -ForegroundColor Yellow
SSH "cat /opt/noc-billing-pro/frontend/build_log.txt 2>&1 | tail -30"

Write-Host "[4] Check dist output..." -ForegroundColor Yellow
SSH "ls -la /opt/noc-billing-pro/frontend/dist/ 2>&1 | head -10"

Write-Host "[5] Copy dist to nginx..." -ForegroundColor Yellow
SSH "echo $pass | sudo -S docker cp /opt/noc-billing-pro/frontend/dist/. noc-billing-pro-frontend:/usr/share/nginx/html/ 2>&1"

Write-Host "[6] Reload nginx..." -ForegroundColor Yellow
SSH "echo $pass | sudo -S docker exec noc-billing-pro-frontend nginx -s reload && echo 'NGINX OK'"

Write-Host "`n============================================" -ForegroundColor Green
Write-Host "  DONE: http://$($srv):8082/network-map" -ForegroundColor Green
Write-Host "============================================" -ForegroundColor Green
