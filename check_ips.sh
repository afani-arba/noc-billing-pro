#!/bin/bash
docker exec noc-billing-pro-mongodb mongosh nocbillingpro --quiet --eval '
print("=== IP in Stats ===");
printjson(db.peering_eye_stats.distinct("device_id"));
print("=== Registered Devices ===");
printjson(db.devices.find({}, {ip_address:1, name:1, _id:0}).toArray());
'
