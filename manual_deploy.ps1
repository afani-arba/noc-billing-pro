$plink = "C:\Program Files\PuTTY\plink.exe"
$pscp = "C:\Program Files\PuTTY\pscp.exe"
$srv = "103.157.116.29"
$user = "noc"
$pass = "123123"
$port = "2777"

Write-Host "Copying GenieACSPage.jsx..."
echo y | & $pscp -P $port -pw $pass "e:\noc-billing-pro\frontend\src\pages\GenieACSPage.jsx" "$user@${srv}:/opt/noc-billing-pro/frontend/src/pages/GenieACSPage.jsx"

Write-Host "Copying WallDisplayPage.jsx..."
echo y | & $pscp -P $port -pw $pass "e:\noc-billing-pro\frontend\src\pages\WallDisplayPage.jsx" "$user@${srv}:/opt/noc-billing-pro/frontend/src/pages/WallDisplayPage.jsx"

Write-Host "Building frontend on server..."
$cmd1 = "docker run --rm -v /opt/noc-billing-pro/frontend:/app -w /app node:20-alpine sh -c 'npm install && npx vite build'"
echo y | & $plink -ssh "$user@$srv" -P $port -pw $pass -batch $cmd1

Write-Host "Injecting frontend to Nginx..."
$cmd2 = "docker cp /opt/noc-billing-pro/frontend/dist/. noc-billing-pro-frontend:/usr/share/nginx/html/ && docker exec noc-billing-pro-frontend nginx -s reload"
echo y | & $plink -ssh "$user@$srv" -P $port -pw $pass -batch $cmd2

Write-Host "Done deploying locally modified files."
