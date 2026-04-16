# Final fix - push server.py fix and re-deploy to container
$plink = "C:\Program Files\PuTTY\plink.exe"
$pscp = "C:\Program Files\PuTTY\pscp.exe"
$host_ip = "10.125.125.238"
$user = "noc"
$pass = "123123"

function Run-SSH {
    param([string]$cmd)
    $result = echo y | & $plink -ssh "$user@$host_ip" -pw $pass -batch $cmd 2>&1
    return $result
}

Write-Host "=== [1] UPLOAD FIXED server.py ===" -ForegroundColor Cyan
& $pscp -pw $pass -batch "e:\noc-billing-pro\backend\server.py" "${user}@${host_ip}:/tmp/server.py"
Run-SSH "docker cp /tmp/server.py noc-billing-pro-backend:/app/server.py"
Write-Host "server.py uploaded and copied to container."

Write-Host "`n=== [2] RESTART BACKEND ===" -ForegroundColor Cyan
Run-SSH "docker restart noc-billing-pro-backend"
Write-Host "Waiting 12 seconds for startup..."
Start-Sleep -Seconds 12

Write-Host "`n=== [3] BACKEND STARTUP LOGS ===" -ForegroundColor Cyan
Run-SSH "docker logs noc-billing-pro-backend --tail 30 2>&1"

Write-Host "`n=== [4] CHECK FOR ERRORS IN LOG ===" -ForegroundColor Cyan
$errors = Run-SSH "docker logs noc-billing-pro-backend --tail 80 2>&1 | grep -iE 'ERROR|CRITICAL|Exception|Traceback' | grep -v 'RateLimit'"
if ($errors) { 
    Write-Host "FOUND ERRORS:" -ForegroundColor Red
    Write-Host $errors
} else {
    Write-Host "NO CRITICAL ERRORS FOUND!" -ForegroundColor Green
}

Write-Host "`n=== [5] VERIFY ALL PPPoE ROUTES REGISTERED ===" -ForegroundColor Cyan
Run-SSH "docker exec noc-billing-pro-backend grep -c 'pppoe' /app/server.py"

Write-Host "`n=== [6] CHECK IF UVICORN STARTED ===" -ForegroundColor Cyan
Run-SSH "docker logs noc-billing-pro-backend --tail 10 2>&1 | grep -E 'READY|startup complete|Uvicorn running'"

Write-Host "`n=== FINAL STATUS ===" -ForegroundColor Green
Run-SSH "docker ps --format 'table {{.Names}}\t{{.Status}}' | grep -i backend"

Write-Host "`n=== GIT PUSH FIX ===" -ForegroundColor Cyan
Write-Host "Pushing fixes to GitHub..."
