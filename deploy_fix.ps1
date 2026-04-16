$plink = "C:\Program Files\PuTTY\plink.exe"
$pscp  = "C:\Program Files\PuTTY\pscp.exe"
$srv   = "10.125.125.238"
$user  = "noc"
$pass  = "123123"

function SSH([string]$cmd) {
    echo y | & $plink -ssh "$user@$srv" -pw $pass -batch $cmd 2>&1
}

# 1. Upload fixed server.py
Write-Host "=== [1] Uploading fixed server.py ===" -ForegroundColor Cyan
& $pscp -pw $pass -batch "e:\noc-billing-pro\backend\server.py" "${user}@${srv}:/tmp/server.py" 2>&1
SSH "docker cp /tmp/server.py noc-billing-pro-backend:/app/server.py"
Write-Host "Done."

# 2. Restart container
Write-Host "`n=== [2] Restarting backend ===" -ForegroundColor Cyan
SSH "docker restart noc-billing-pro-backend"
Write-Host "Waiting 15 seconds..."
Start-Sleep -Seconds 15

# 3. Check errors
Write-Host "`n=== [3] ERROR CHECK ===" -ForegroundColor Cyan
$errors = SSH "docker logs noc-billing-pro-backend --tail 80 2>&1"
$lines = $errors -split "`n"
$badLines = $lines | Where-Object { $_ -match "ERROR|CRITICAL|Exception|Traceback" -and $_ -notmatch "RateLimit" }
if ($badLines) {
    Write-Host "ERRORS FOUND:" -ForegroundColor Red
    $badLines | ForEach-Object { Write-Host $_ }
} else {
    Write-Host "NO CRITICAL ERRORS!" -ForegroundColor Green
}

# 4. Show ready signal
Write-Host "`n=== [4] READY STATUS ===" -ForegroundColor Cyan
SSH "docker logs noc-billing-pro-backend --tail 20 2>&1"

# 5. Git push
Write-Host "`n=== [5] PUSH FIXES TO GITHUB ===" -ForegroundColor Cyan
