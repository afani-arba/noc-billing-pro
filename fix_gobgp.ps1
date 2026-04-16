$plink = "C:\Program Files\PuTTY\plink.exe"
$srv = "10.125.125.238"; $user = "noc"; $pass = "123123"
function SSH([string]$cmd) { echo y | & $plink -ssh "$user@$srv" -pw $pass -batch $cmd 2>&1 }

$config = @"
[global.config]
  as = 65000
  router-id = `"10.125.125.238`"
  listen-addresses = [`"0.0.0.0`"]
  listen-port = 179

[[neighbors]]
  [neighbors.config]
    neighbor-address = `"0.0.0.0`"
    peer-as = 65001
    description = `"MikroTik-All-Peers`"
  [neighbors.transport.config]
    passive-mode = true
  [neighbors.ebgp-multihop.config]
    enabled = true
    multihop-ttl = 10
  [neighbors.apply-policy.config]
    default-import-policy = `"accept-route`"
    default-export-policy = `"accept-route`"
  [[neighbors.afi-safis]]
    [neighbors.afi-safis.config]
      afi-safi-name = `"ipv4-unicast`"
"@

$configEscaped = $config -replace '"', '\"' -replace '`n', '\n'

Write-Host "Fixing corrupted GoBGP config..."
# using docker to gain root and write securely since simple echo might hit permissions
SSH "docker run --rm -v /etc/gobgpd:/etc/gobgpd alpine sh -c 'echo -e `"$configEscaped`" > /etc/gobgpd/gobgpd.conf'"
SSH "echo '123123' | sudo -S systemctl restart gobgpd"
SSH "echo '123123' | sudo -S systemctl status gobgpd --no-pager | grep Active"
