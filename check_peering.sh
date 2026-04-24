#!/bin/bash
# Check peering eye data
echo "=== Collections ==="
docker exec noc-billing-pro-mongodb mongosh noc_billing --quiet --eval 'db.getCollectionNames().forEach(c => print(c))'

echo "=== peering_eye_stats count ==="
docker exec noc-billing-pro-mongodb mongosh noc_billing --quiet --eval 'print(db.peering_eye_stats.countDocuments({}))'

echo "=== peering_eye_stats sample ==="
docker exec noc-billing-pro-mongodb mongosh noc_billing --quiet --eval 'db.peering_eye_stats.find().sort({timestamp:-1}).limit(3).forEach(d => printjson({device_id:d.device_id,platform:d.platform,hits:d.hits,ts:d.timestamp}))'

echo "=== syslog_entries count ==="
docker exec noc-billing-pro-mongodb mongosh noc_billing --quiet --eval 'print(db.syslog_entries.countDocuments({}))'

echo "=== syslog_entries sample ==="
docker exec noc-billing-pro-mongodb mongosh noc_billing --quiet --eval 'db.syslog_entries.find().sort({timestamp:-1}).limit(2).forEach(d => printjson({source:d.source_ip,msg:d.message?d.message.substring(0,120):"",ts:d.timestamp}))'

echo "=== devices sample ==="
docker exec noc-billing-pro-mongodb mongosh noc_billing --quiet --eval 'db.devices.find({},{_id:0,id:1,name:1,ip_address:1}).limit(3).forEach(d => printjson(d))'
