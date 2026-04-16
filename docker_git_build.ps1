$plink = "C:\Program Files\PuTTY\plink.exe"
$pscp  = "C:\Program Files\PuTTY\pscp.exe"
$srv   = "10.125.125.238"
$user  = "noc"
$pass  = "123123"

function SSH([string]$cmd) {
    echo y | & $plink -ssh "$user@$srv" -pw $pass -batch $cmd 2>&1
}

# Strategy: 
# 1. Run a temp node container with the frontend mounted (as root inside container)
# 2. Pull via git inside that container
# 3. Build
# 4. The dist output will be accessible on host
# 5. Docker cp into nginx

Write-Host "=== [1] Check docker group and git status ===" -ForegroundColor Cyan
SSH "id && groups"
SSH "docker ps --format '{{.Names}}' | head"

Write-Host "`n=== [2] Run node build in docker with git fetch inside ===" -ForegroundColor Cyan
Write-Host "This runs everything as root inside the container..." -ForegroundColor Yellow

$buildScript = @"
cd /workspace && 
git config --global --add safe.directory /workspace && 
git fetch origin main && 
git reset --hard origin/main && 
echo PULLED_OK &&
cd frontend && 
npm ci --silent 2>&1 | tail -5 && 
npm run build 2>&1 | tail -10 && 
echo BUILD_COMPLETE
"@

$buildScriptEscaped = $buildScript -replace "`n", " "
SSH "docker run --rm -v /opt/noc-billing-pro:/workspace -w /workspace node:20-alpine sh -c '$buildScriptEscaped' 2>&1"

Write-Host "`n=== [3] Check if dist was created ===" -ForegroundColor Cyan
SSH "ls /opt/noc-billing-pro/frontend/dist/ 2>&1 | head -5"

Write-Host "`n=== [4] Copy dist into nginx container ===" -ForegroundColor Cyan
SSH "docker cp /opt/noc-billing-pro/frontend/dist/. noc-billing-pro-frontend:/usr/share/nginx/html/ && echo 'COPIED_OK'"

Write-Host "`n=== [5] Reload nginx ===" -ForegroundColor Cyan
SSH "docker exec noc-billing-pro-frontend nginx -s reload && echo 'NGINX_OK'"

Write-Host "`n=== [6] Verify fix is in place ===" -ForegroundColor Cyan
SSH "docker exec noc-billing-pro-frontend ls /usr/share/nginx/html/assets/ | head -5"

Write-Host "`n=== DONE ===" -ForegroundColor Green
