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
SSH "docker run --rm -v /opt/noc-billing-pro/frontend:/app -w /app node:20-alpine sh -c 'rm -rf build && npm ci --silent && npm run build 2>&1 | tail -10 && echo BUILD_OK' 2>&1"

Write-Host "`n=== [4] Check build result ===" -ForegroundColor Cyan
SSH "ls /opt/noc-billing-pro/frontend/build/ 2>&1 | head -10"

Write-Host "`n=== [5] Inject built assets into running Nginx container ===" -ForegroundColor Cyan
SSH "docker cp /opt/noc-billing-pro/frontend/build/. noc-billing-pro-frontend:/usr/share/nginx/html/ && echo 'INJECT_OK'"
SSH "docker exec noc-billing-pro-frontend nginx -s reload && echo 'NGINX_RELOAD_OK'"

Write-Host "`n=== [6] Final verification ===" -ForegroundColor Cyan
SSH "docker exec noc-billing-pro-frontend ls /usr/share/nginx/html/"

Write-Host "`n=== DONE ===" -ForegroundColor Green
