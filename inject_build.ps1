$plink = "C:\Program Files\PuTTY\plink.exe"
$srv = "10.125.125.238"; $user = "noc"; $pass = "123123"
function SSH([string]$cmd) { echo y | & $plink -ssh "$user@$srv" -pw $pass -batch $cmd 2>&1 }

Write-Host "=== Injecting /frontend/build into Nginx ===" -ForegroundColor Cyan
SSH "docker cp /opt/noc-billing-pro/frontend/build/. noc-billing-pro-frontend:/usr/share/nginx/html/ && echo INJECTED"
SSH "docker exec noc-billing-pro-frontend nginx -s reload && echo NGINX_OK"

Write-Host "`n=== Verifying ===" -ForegroundColor Cyan
SSH "docker exec noc-billing-pro-frontend ls /usr/share/nginx/html/assets/ | grep -i Bgp"

Write-Host "`n=== Check build timestamp to confirm new assets ===" -ForegroundColor Cyan
SSH "docker exec noc-billing-pro-frontend ls -la /usr/share/nginx/html/ | head -5"
Write-Host "`n=== DEPLOY COMPLETE ===" -ForegroundColor Green
Write-Host "Hard refresh browser (Ctrl+Shift+F5) to load the fixed BGP Steering page." -ForegroundColor Yellow
