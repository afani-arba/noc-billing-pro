$plink = "C:\Program Files\PuTTY\plink.exe"
$srv = "103.157.116.29"
$user = "noc"
$pass = "123123"
$port = "2777"

Write-Host "Pulling from Github..."
$cmd1 = "echo $pass | sudo -S sh -c 'cd /opt/noc-billing-pro && git pull'"
echo y | & $plink -ssh "$user@$srv" -P $port -pw $pass -batch -t $cmd1

Write-Host "Restarting Backend (FastAPI & Radius)..."
$cmd2 = "echo $pass | sudo -S docker restart noc-billing-pro-backend noc-billing-pro-radius"
echo y | & $plink -ssh "$user@$srv" -P $port -pw $pass -batch -t $cmd2

Write-Host "Building Frontend..."
$cmd3 = "echo $pass | sudo -S docker run --rm -v /opt/noc-billing-pro/frontend:/app -w /app node:20-alpine sh -c 'npm install --silent && npx vite build'"
echo y | & $plink -ssh "$user@$srv" -P $port -pw $pass -batch -t $cmd3

Write-Host "Deploying Frontend to Nginx..."
$cmd4 = "echo $pass | sudo -S docker cp /opt/noc-billing-pro/frontend/build/. noc-billing-pro-frontend:/usr/share/nginx/html/ && echo $pass | sudo -S docker exec noc-billing-pro-frontend nginx -s reload"
echo y | & $plink -ssh "$user@$srv" -P $port -pw $pass -batch -t $cmd4

Write-Host "Deployment Completed!"
