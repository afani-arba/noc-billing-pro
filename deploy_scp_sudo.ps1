$plink = "C:\Program Files\PuTTY\plink.exe"
$pscp = "C:\Program Files\PuTTY\pscp.exe"
$srv = "103.157.116.29"
$user = "noc"
$pass = "123123"
$port = "2777"

Write-Host "Copying to noc home..."
echo y | & $pscp -P $port -pw $pass "e:\noc-billing-pro\frontend\src\pages\GenieACSPage.jsx" "$user@${srv}:~/"
echo y | & $pscp -P $port -pw $pass "e:\noc-billing-pro\frontend\src\pages\WallDisplayPage.jsx" "$user@${srv}:~/"

Write-Host "Moving with sudo..."
echo y | & $plink -ssh "$user@$srv" -P $port -pw $pass -batch -t "echo $pass | sudo -S mv ~/GenieACSPage.jsx /opt/noc-billing-pro/frontend/src/pages/GenieACSPage.jsx"
echo y | & $plink -ssh "$user@$srv" -P $port -pw $pass -batch -t "echo $pass | sudo -S mv ~/WallDisplayPage.jsx /opt/noc-billing-pro/frontend/src/pages/WallDisplayPage.jsx"

Write-Host "Building frontend on server..."
$cmd1 = "echo $pass | sudo -S docker run --rm -v /opt/noc-billing-pro/frontend:/app -w /app node:20-alpine sh -c 'npm install --silent && npx vite build'"
echo y | & $plink -ssh "$user@$srv" -P $port -pw $pass -batch -t $cmd1

Write-Host "Injecting frontend to Nginx..."
$cmd2 = "echo $pass | sudo -S docker cp /opt/noc-billing-pro/frontend/dist/. noc-billing-pro-frontend:/usr/share/nginx/html/"
echo y | & $plink -ssh "$user@$srv" -P $port -pw $pass -batch -t $cmd2

$cmd3 = "echo $pass | sudo -S docker exec noc-billing-pro-frontend nginx -s reload"
echo y | & $plink -ssh "$user@$srv" -P $port -pw $pass -batch -t $cmd3

Write-Host "Clean up and done."
