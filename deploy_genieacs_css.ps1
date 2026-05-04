$plink = "C:\Program Files\PuTTY\plink.exe"
$pscp   = "C:\Program Files\PuTTY\pscp.exe"
$srv   = "10.125.125.235"
$user  = "noc"
$pass  = "123123"
$remote = "/opt/noc-billing-pro"

function SSH([string]$cmd) {
    Write-Host "  CMD: $cmd" -ForegroundColor DarkGray
    $r = echo y | & $plink -ssh "$user@$srv" -pw $pass -batch $cmd 2>&1
    Write-Host $r
}

Write-Host "[1] Push custom-grafana-theme.css ke GitHub..." -ForegroundColor Yellow
Set-Location "E:\noc-billing-pro"
git add genieacs/custom-grafana-theme.css
git commit -m "fix(genieacs): hapus wrapper overflow hidden dan hapus nav stretch yang bikin ui tidak bisa diklik"
git push origin main

Write-Host "`n[2] Pull di server..." -ForegroundColor Yellow
SSH "echo $pass | sudo -S bash -c 'cd $remote && git pull origin main 2>&1'"

Write-Host "`n[3] Apply theme di server..." -ForegroundColor Yellow
SSH "echo $pass | sudo -S bash -c 'cd $remote/genieacs && chmod +x apply_theme.sh && ./apply_theme.sh 2>&1'"

Write-Host "`n[4] Restart GenieACS UI container..." -ForegroundColor Yellow
SSH "echo $pass | sudo -S docker restart noc-billing-pro-genieacs-ui"

Write-Host "`n===========================================================" -ForegroundColor Green
Write-Host "  FIX SELESAI. Silakan Hard Refresh (Ctrl+F5) halaman GenieACS!" -ForegroundColor Green
Write-Host "===========================================================" -ForegroundColor Green
