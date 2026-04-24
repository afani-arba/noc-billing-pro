#!/bin/bash
# Diagnosis script untuk Peering-Eye device_id mismatch

echo "=== DISTINCT device_id in peering_eye_stats ==="
docker exec noc-billing-pro-mongodb mongosh noc_billing --quiet --eval '
var ids = db.peering_eye_stats.distinct("device_id");
ids.forEach(function(id) {
  var cnt = db.peering_eye_stats.countDocuments({device_id: id});
  print(id + " => " + cnt + " records");
});
'

echo ""
echo "=== DEVICES in DB (UUID, name, ip_address, bgp_peer_ip, vpn_ip) ==="
docker exec noc-billing-pro-mongodb mongosh noc_billing --quiet --eval '
db.devices.find({},{id:1,name:1,ip_address:1,bgp_peer_ip:1,vpn_ip:1,_id:0}).forEach(function(d) {
  var id = d.id || "";
  var short = id.length > 12 ? id.substring(0,12) + "..." : id;
  print(short + " | " + d.name + " | ip=" + d.ip_address + " | bgp=" + d.bgp_peer_ip + " | vpn=" + d.vpn_ip);
});
'

echo ""
echo "=== TOTAL peering_eye_stats records ==="
docker exec noc-billing-pro-mongodb mongosh noc_billing --quiet --eval 'print(db.peering_eye_stats.countDocuments({}))'

echo ""
echo "=== SAMPLE 5 records terbaru di stats ==="
docker exec noc-billing-pro-mongodb mongosh noc_billing --quiet --eval '
db.peering_eye_stats.find({},{device_id:1,platform:1,hits:1,timestamp:1}).sort({timestamp:-1}).limit(5).forEach(function(d) {
  print(d.timestamp + " | dev=" + d.device_id + " | plat=" + d.platform + " | hits=" + d.hits);
});
'

echo ""
echo "=== CHECK pppoe_sessions sample ==="
docker exec noc-billing-pro-mongodb mongosh noc_billing --quiet --eval '
var cnt = db.pppoe_sessions.countDocuments({});
print("Total pppoe_sessions: " + cnt);
db.pppoe_sessions.find({}).limit(3).forEach(function(d) {
  print("  ip=" + d.ip + " name=" + d.name + " device=" + d.device_id);
});
'
