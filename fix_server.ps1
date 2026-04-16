# SSH Fix Script - Copy files directly into running container
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

Write-Host "=== [1] UPLOAD pppoe_monitoring.py & hotspot.py TO SERVER ===" -ForegroundColor Cyan
$scpResult = & $pscp -pw $pass -batch `
    "e:\noc-billing-pro\backend\routers\pppoe_monitoring.py" `
    "e:\noc-billing-pro\backend\routers\hotspot.py" `
    "${user}@${host_ip}:/tmp/" 2>&1
Write-Host $scpResult

Write-Host "`n=== [2] COPY FILES INTO RUNNING CONTAINER ===" -ForegroundColor Cyan
Run-SSH "docker cp /tmp/pppoe_monitoring.py noc-billing-pro-backend:/app/routers/pppoe_monitoring.py"
Run-SSH "docker cp /tmp/hotspot.py noc-billing-pro-backend:/app/routers/hotspot.py"
Write-Host "Files copied into container."

Write-Host "`n=== [3] UPLOAD server.py ===" -ForegroundColor Cyan
$scpResult2 = & $pscp -pw $pass -batch `
    "e:\noc-billing-pro\backend\server.py" `
    "${user}@${host_ip}:/tmp/server.py" 2>&1
Write-Host $scpResult2

Run-SSH "docker cp /tmp/server.py noc-billing-pro-backend:/app/server.py"
Write-Host "server.py copied into container."

Write-Host "`n=== [4] VERIFY FILES IN CONTAINER ===" -ForegroundColor Cyan
Run-SSH "docker exec noc-billing-pro-backend ls /app/routers/ | grep -E 'pppoe|hotspot'"
Run-SSH "docker exec noc-billing-pro-backend grep -n 'pppoe_monitoring' /app/server.py | head -5"

Write-Host "`n=== [5] RESTART FASTAPI WITHOUT FULL REBUILD ===" -ForegroundColor Cyan
Run-SSH "docker restart noc-billing-pro-backend"
Write-Host "Container restarting..."
Start-Sleep -Seconds 8

Write-Host "`n=== [6] CHECK BACKEND LOGS AFTER RESTART ===" -ForegroundColor Cyan
Run-SSH "docker logs noc-billing-pro-backend --tail 40 2>&1"

Write-Host "`n=== [7] TEST API ENDPOINTS ===" -ForegroundColor Cyan
Run-SSH "docker exec noc-billing-pro-backend python3 -c ""import routers.pppoe_monitoring; print('OK - pppoe_monitoring loaded')"" 2>&1"
Run-SSH "docker exec noc-billing-pro-backend python3 -c ""import routers.hotspot; print('OK - hotspot loaded')"" 2>&1"

Write-Host "`n=== [8] TEST HTTP ENDPOINTS VIA BACKEND PYTHON ===" -ForegroundColor Cyan
Run-SSH "docker exec noc-billing-pro-backend python3 -c ""import httpx; r=httpx.get('http://localhost:8000/api/pppoe-settings', headers={'Authorization':'Bearer fake'}); print(r.status_code)"" 2>&1"

Write-Host "`n=== FIX COMPLETED ===" -ForegroundColor Green
