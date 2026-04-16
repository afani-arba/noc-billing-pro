$plink = "C:\Program Files\PuTTY\plink.exe"
$srv = "10.125.125.238"; $user = "noc"; $pass = "123123"
function SSH([string]$cmd) { echo y | & $plink -ssh "$user@$srv" -pw $pass -batch $cmd 2>&1 }

Write-Host "=== 1. Git pull code from GitHub ===" -ForegroundColor Cyan
SSH "docker run --rm -v /opt/noc-billing-pro:/ws bitnami/git:latest sh -c 'cd /ws && git config --global --add safe.directory /ws && git fetch origin main && git reset --hard origin/main && echo PULLED_OK'"

Write-Host "`n=== 2. Restart Backend ===" -ForegroundColor Cyan
SSH "docker restart noc-billing-pro-backend"

Write-Host "`n=== DEPLOY COMPLETE ===" -ForegroundColor Green
