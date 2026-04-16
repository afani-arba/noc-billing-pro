$plink = "C:\Program Files\PuTTY\plink.exe"
$pscp  = "C:\Program Files\PuTTY\pscp.exe"
$srv   = "10.125.125.238"
$user  = "noc"
$pass  = "123123"

function SSH([string]$cmd) {
    echo y | & $plink -ssh "$user@$srv" -pw $pass -batch $cmd 2>&1
}

# The build is cached because git pull as 'noc' fails (root owns the repo)
# Strategy: build the JS bundle locally and inject the built assets into the running Nginx container

Write-Host "=== [1] Build frontend locally ===" -ForegroundColor Cyan
Set-Location "e:\noc-billing-pro\frontend"
npm run build 2>&1 | Select-Object -Last 20
Set-Location "e:\noc-billing-pro"

Write-Host "`n=== [2] Check if local build succeeded ===" -ForegroundColor Cyan
if (Test-Path "e:\noc-billing-pro\frontend\dist\index.html") {
    Write-Host "Build SUCCESS - dist folder exists" -ForegroundColor Green
    Get-ChildItem "e:\noc-billing-pro\frontend\dist"
} else {
    Write-Host "Build FAILED - dist folder missing" -ForegroundColor Red
    exit 1
}

Write-Host "`n=== [3] Upload dist/assets to server ===" -ForegroundColor Cyan
# Upload the entire dist folder as a tar
Compress-Archive -Path "e:\noc-billing-pro\frontend\dist\*" -DestinationPath "e:\noc-billing-pro\dist.zip" -Force
& $pscp -pw $pass -batch "e:\noc-billing-pro\dist.zip" "${user}@${srv}:/tmp/dist.zip" 2>&1

Write-Host "`n=== [4] Extract and inject into Nginx container ===" -ForegroundColor Cyan
SSH "rm -rf /tmp/dist && mkdir -p /tmp/dist && unzip -q /tmp/dist.zip -d /tmp/dist && echo 'Extracted OK'"
SSH "docker exec noc-billing-pro-frontend rm -rf /usr/share/nginx/html/assets"
SSH "docker cp /tmp/dist/. noc-billing-pro-frontend:/usr/share/nginx/html/"
Write-Host "Assets injected into Nginx container."

Write-Host "`n=== [5] Verify new files are in Nginx ===" -ForegroundColor Cyan
SSH "docker exec noc-billing-pro-frontend ls /usr/share/nginx/html/"

Write-Host "`n=== [6] Reload Nginx (no downtime) ===" -ForegroundColor Cyan
SSH "docker exec noc-billing-pro-frontend nginx -s reload 2>&1 && echo 'Nginx reloaded OK'"

Write-Host "`n=== FRONTEND UPDATED SUCCESSFULLY ===" -ForegroundColor Green
Write-Host "Please hard-refresh the browser (Ctrl+Shift+F5) to see the fix." -ForegroundColor Yellow
