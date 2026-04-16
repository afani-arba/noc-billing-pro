$plink = "C:\Program Files\PuTTY\plink.exe"
$pscp  = "C:\Program Files\PuTTY\pscp.exe"
$srv   = "10.125.125.238"
$user  = "noc"
$pass  = "123123"

function SSH([string]$cmd) {
    echo y | & $plink -ssh "$user@$srv" -pw $pass -batch $cmd 2>&1
}

# node:20-alpine doesn't have git. Use node:20-bookworm-slim which has apt
# Alternatively: install git inside node container, pull, then build

Write-Host "=== Building frontend using node:20-bookworm with git ===" -ForegroundColor Cyan
Write-Host "Starting build (4-6 minutes)..." -ForegroundColor Yellow

$buildCmd = "docker run --rm -v /opt/noc-billing-pro:/workspace -w /workspace node:20-bookworm-slim sh -c 'apt-get install -y git -qq 2>/dev/null && git config --global --add safe.directory /workspace && git fetch origin main && git reset --hard origin/main && echo PULLED_OK && cd frontend && npm ci --silent 2>&1 | tail -3 && npm run build 2>&1 | tail -5 && echo BUILD_COMPLETE' 2>&1"

SSH $buildCmd

Write-Host "`n=== Check build result ===" -ForegroundColor Cyan
SSH "ls /opt/noc-billing-pro/frontend/dist/ 2>&1 | head -5"

Write-Host "`n=== Inject into Nginx ===" -ForegroundColor Cyan
SSH "docker cp /opt/noc-billing-pro/frontend/dist/. noc-billing-pro-frontend:/usr/share/nginx/html/ && echo INJECT_OK"
SSH "docker exec noc-billing-pro-frontend nginx -s reload && echo NGINX_OK"

Write-Host "`n=== Verify files ===" -ForegroundColor Cyan
SSH "docker exec noc-billing-pro-frontend ls /usr/share/nginx/html/assets/ | grep Bgp"
Write-Host "`n=== DONE ===" -ForegroundColor Green
