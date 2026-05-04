$plink = "C:\Program Files\PuTTY\plink.exe"
$srv   = "10.125.125.235"
$user  = "noc"
$pass  = "123123"

function SSH([string]$cmd) {
    Write-Host "  CMD: $cmd" -ForegroundColor DarkGray
    $r = echo y | & $plink -ssh "$user@$srv" -pw $pass -batch $cmd 2>&1
    Write-Host $r
}

Write-Host "[1] Resolve git conflict - stash then pull..." -ForegroundColor Yellow
SSH "echo $pass | sudo -S bash -c 'cd /opt/noc-billing-pro && git stash && git pull origin main 2>&1'"

Write-Host "[2] Check node npm on server..." -ForegroundColor Yellow
SSH "which node 2>&1; which npm 2>&1; node --version 2>&1"

Write-Host "[3] Check npm in updater container..." -ForegroundColor Yellow
SSH "echo $pass | sudo -S docker exec noc-billing-pro-updater which npm 2>&1"

Write-Host "[4] Find npm binary on host..." -ForegroundColor Yellow
SSH "find /usr/local/bin /usr/bin /snap/bin -name npm 2>&1 | head -5"
