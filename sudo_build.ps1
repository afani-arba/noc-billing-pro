$plink = "C:\Program Files\PuTTY\plink.exe"
$pscp  = "C:\Program Files\PuTTY\pscp.exe"
$srv   = "10.125.125.238"
$user  = "noc"
$pass  = "123123"

function SSH([string]$cmd) {
    echo y | & $plink -ssh "$user@$srv" -pw $pass -batch $cmd 2>&1
}

Write-Host "=== [1] Pull latest with sudo via echo ===" -ForegroundColor Cyan
SSH "echo '123123' | sudo -S git -C /opt/noc-billing-pro config --global --add safe.directory /opt/noc-billing-pro 2>&1"
SSH "echo '123123' | sudo -S git -C /opt/noc-billing-pro fetch origin main 2>&1"
SSH "echo '123123' | sudo -S git -C /opt/noc-billing-pro reset --hard origin/main 2>&1"
Write-Host "Git pull done."

Write-Host "`n=== [2] Check if BgpSteeringPage is updated ===" -ForegroundColor Cyan
SSH "grep -n 'summaryRaw\|Array.isArray' /opt/noc-billing-pro/frontend/src/pages/BgpSteeringPage.jsx | head -5"

Write-Host "`n=== [3] Build frontend using Docker compose --no-cache ===" -ForegroundColor Cyan
Write-Host "Building (3-5 min)..."
SSH "echo '123123' | sudo -S bash -c 'cd /opt/noc-billing-pro && docker compose build --no-cache noc-frontend 2>&1 | tail -15'"

Write-Host "`n=== [4] Restart frontend container ===" -ForegroundColor Cyan
SSH "cd /opt/noc-billing-pro && docker compose up -d noc-frontend 2>&1"
Start-Sleep -Seconds 8

Write-Host "`n=== [5] Verify ===" -ForegroundColor Cyan
SSH "docker ps --format 'table {{.Names}}\t{{.Status}}' | grep frontend"

Write-Host "`n=== SUCCESS ===" -ForegroundColor Green
