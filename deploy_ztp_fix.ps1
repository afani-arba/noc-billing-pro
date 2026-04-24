$plink = "C:\Program Files\PuTTY\plink.exe"
$pscp = "C:\Program Files\PuTTY\pscp.exe"
$srv = "103.157.116.29"
$user = "noc"
$pass = "123123"
$port = "2777"

# === Upload Frontend ===
Write-Host "Uploading GenieACSPage.jsx..." -ForegroundColor Cyan
echo y | & $pscp -P $port -pw $pass "e:\noc-billing-pro\frontend\src\pages\GenieACSPage.jsx" "$user@${srv}:/home/noc/GenieACSPage.jsx"

# === Upload Backend ===
Write-Host "Uploading genieacs_service.py..." -ForegroundColor Cyan
echo y | & $pscp -P $port -pw $pass "e:\noc-billing-pro\backend\services\genieacs_service.py" "$user@${srv}:/home/noc/genieacs_service.py"

Write-Host "Uploading genieacs.py (router)..." -ForegroundColor Cyan
echo y | & $pscp -P $port -pw $pass "e:\noc-billing-pro\backend\routers\genieacs.py" "$user@${srv}:/home/noc/genieacs_router.py"

# === Move files with sudo ===
Write-Host "Moving files to correct locations (sudo)..." -ForegroundColor Yellow
echo y | & $plink -ssh "$user@$srv" -P $port -pw $pass -batch -t "echo $pass | sudo -S mv /home/noc/GenieACSPage.jsx /opt/noc-billing-pro/frontend/src/pages/GenieACSPage.jsx"
echo y | & $plink -ssh "$user@$srv" -P $port -pw $pass -batch -t "echo $pass | sudo -S mv /home/noc/genieacs_service.py /opt/noc-billing-pro/backend/services/genieacs_service.py"
echo y | & $plink -ssh "$user@$srv" -P $port -pw $pass -batch -t "echo $pass | sudo -S mv /home/noc/genieacs_router.py /opt/noc-billing-pro/backend/routers/genieacs.py"

# === Syntax check backend ===
Write-Host "Checking Python syntax..." -ForegroundColor Cyan
echo y | & $plink -ssh "$user@$srv" -P $port -pw $pass -batch -t "echo $pass | sudo -S docker exec noc-billing-pro-backend python3 -m py_compile /app/services/genieacs_service.py && echo 'service OK'"
echo y | & $plink -ssh "$user@$srv" -P $port -pw $pass -batch -t "echo $pass | sudo -S docker exec noc-billing-pro-backend python3 -m py_compile /app/routers/genieacs.py && echo 'router OK'"

# === Inject backend files into container ===
Write-Host "Injecting backend into container..." -ForegroundColor Cyan
echo y | & $plink -ssh "$user@$srv" -P $port -pw $pass -batch -t "echo $pass | sudo -S docker cp /opt/noc-billing-pro/backend/services/genieacs_service.py noc-billing-pro-backend:/app/services/genieacs_service.py"
echo y | & $plink -ssh "$user@$srv" -P $port -pw $pass -batch -t "echo $pass | sudo -S docker cp /opt/noc-billing-pro/backend/routers/genieacs.py noc-billing-pro-backend:/app/routers/genieacs.py"
echo y | & $plink -ssh "$user@$srv" -P $port -pw $pass -batch -t "echo $pass | sudo -S docker restart noc-billing-pro-backend && echo 'BACKEND_RESTARTED'"

# === Build Frontend ===
Write-Host "Building frontend..." -ForegroundColor Cyan
$buildCmd = "echo $pass | sudo -S docker run --rm -v /opt/noc-billing-pro/frontend:/app -w /app node:20-alpine sh -c 'npm install --silent && npx vite build'"
echo y | & $plink -ssh "$user@$srv" -P $port -pw $pass -batch -t $buildCmd

# === Inject to Nginx ===
Write-Host "Injecting to Nginx..." -ForegroundColor Cyan
echo y | & $plink -ssh "$user@$srv" -P $port -pw $pass -batch -t "echo $pass | sudo -S docker cp /opt/noc-billing-pro/frontend/build/. noc-billing-pro-frontend:/usr/share/nginx/html/"
echo y | & $plink -ssh "$user@$srv" -P $port -pw $pass -batch -t "echo $pass | sudo -S docker exec noc-billing-pro-frontend nginx -s reload"

Write-Host "=== DEPLOY DONE ===" -ForegroundColor Green
