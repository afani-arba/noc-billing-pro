# SSH Audit Script v3 - Full fix
$plink = "C:\Program Files\PuTTY\plink.exe"
$host_ip = "10.125.125.238"
$user = "noc"
$pass = "123123"

function Run-SSH {
    param([string]$cmd)
    $result = echo y | & $plink -ssh "$user@$host_ip" -pw $pass -batch $cmd 2>&1
    return $result
}

Write-Host "=== [1] GET EXACT CONTAINER NAMES ===" -ForegroundColor Cyan
Run-SSH "docker ps --format '{{.Names}}'"

Write-Host "`n=== [2] FIND ACTUAL BACKEND CONTAINER ===" -ForegroundColor Cyan
$backContainer = (Run-SSH "docker ps --format '{{.Names}}' | grep -i backend") | Select-String "backend" | ForEach-Object { $_.ToString().Trim() } | Select-Object -First 1
Write-Host "Detected backend container: [$backContainer]"

Write-Host "`n=== [3] CHECK pppoe_monitoring.py INSIDE CONTAINER ===" -ForegroundColor Cyan
Run-SSH "docker ps --format '{{.Names}}' | grep -i backend | xargs -I{} docker exec {} ls /app/routers/ | sort"

Write-Host "`n=== [4] CHECK git status (as root) ===" -ForegroundColor Cyan
Run-SSH "docker exec noc-billing-pro-backend git -C /app log --oneline -3 2>&1 || echo 'git not in container, check volume'"

Write-Host "`n=== [5] CHECK BACKEND API ROUTES ===" -ForegroundColor Cyan
Run-SSH "docker exec noc-billing-pro-backend grep -r 'pppoe' /app/routers/ --include='*.py' -l 2>&1"

Write-Host "`n=== [6] CHECK BACKEND API ROUTES - ACTUAL ENDPOINTS ===" -ForegroundColor Cyan
Run-SSH "docker exec noc-billing-pro-backend grep -rn 'router.get\|router.post' /app/routers/pppoe_monitoring.py 2>&1 || echo 'File not found in container!'"

Write-Host "`n=== [7] CHECK IF PPPOE ROUTER IS IN server.py INSIDE CONTAINER ===" -ForegroundColor Cyan
Run-SSH "docker exec noc-billing-pro-backend grep -n 'pppoe_monitoring' /app/server.py 2>&1 || echo 'NOT REGISTERED'"

Write-Host "`n=== [8] CHECK BACKEND LOGS FOR API ERRORS ===" -ForegroundColor Cyan
Run-SSH "docker logs noc-billing-pro-backend --tail 50 2>&1 | grep -i 'error\|404\|exception\|fail' | head -30"

Write-Host "`n=== [9] TEST API REACHABILITY ===" -ForegroundColor Cyan
Run-SSH "docker exec noc-billing-pro-backend curl -s -w '\nHTTP_CODE:%{http_code}' 'http://localhost:8000/api/pppoe-settings' -H 'Authorization: Bearer test' 2>&1 | tail -2"

Write-Host "`n=== [10] REBUILD BACKEND WITH LATEST CODE ===" -ForegroundColor Cyan
Write-Host "Pulling latest code and rebuilding..." -ForegroundColor Yellow
Run-SSH "cd /opt/noc-billing-pro && git config --global --add safe.directory /opt/noc-billing-pro"
Run-SSH "cd /opt/noc-billing-pro && git fetch origin main"

# Check if we can actually pull (maybe root owns it)
Write-Host "`nChecking git repo ownership..." -ForegroundColor Yellow
Run-SSH "ls -la /opt/noc-billing-pro/.git"

Write-Host "`n=== [11] REBUILD BACKEND ===" -ForegroundColor Cyan
Run-SSH "cd /opt/noc-billing-pro && docker compose build --no-cache noc-backend 2>&1 | tail -30"

Write-Host "`n=== [12] RESTART BACKEND ===" -ForegroundColor Cyan
Run-SSH "cd /opt/noc-billing-pro && docker compose up -d noc-backend 2>&1"

Write-Host "`n=== AUDIT PHASE 2 DONE ===" -ForegroundColor Green
