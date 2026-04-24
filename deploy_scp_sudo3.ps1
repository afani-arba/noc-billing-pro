$plink = "C:\Program Files\PuTTY\plink.exe"
$srv = "103.157.116.29"
$user = "noc"
$pass = "123123"
$port = "2777"

Write-Host "Injecting frontend to Nginx from build/ ..."
$cmd2 = "echo $pass | sudo -S docker cp /opt/noc-billing-pro/frontend/build/. noc-billing-pro-frontend:/usr/share/nginx/html/"
echo y | & $plink -ssh "$user@$srv" -P $port -pw $pass -batch -t $cmd2

$cmd3 = "echo $pass | sudo -S docker exec noc-billing-pro-frontend nginx -s reload"
echo y | & $plink -ssh "$user@$srv" -P $port -pw $pass -batch -t $cmd3

Write-Host "Done copying build to Nginx."
