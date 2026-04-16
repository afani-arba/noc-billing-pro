#!/bin/bash
# Audit bandwidth history di MongoDB production
echo "=== COUNT traffic_history ==="
docker exec noc-billing-pro-mongodb mongosh nocbillingpro --quiet --eval "
db.traffic_history.countDocuments({})
"

echo ""
echo "=== LATEST 3 DOCS (fields summary) ==="
docker exec noc-billing-pro-mongodb mongosh nocbillingpro --quiet --eval "
db.traffic_history.find({}, {
  device_id:1, timestamp:1,
  'isp_bandwidth': { \$objectToArray: '\$isp_bandwidth' },
  'bw_keys': { \$objectToArray: '\$bandwidth' }
}).sort({timestamp:-1}).limit(3).forEach(d => {
  const bwKeys = Object.keys(d.bandwidth || {});
  const ispKeys = Object.keys(d.isp_bandwidth || {});
  const bwSample = bwKeys.length > 0 ? d.bandwidth[bwKeys[0]] : {};
  print('=== DOC ===');
  print('device_id:', d.device_id);
  print('timestamp:', d.timestamp);
  print('bandwidth keys:', JSON.stringify(bwKeys));
  print('isp_bandwidth keys:', JSON.stringify(ispKeys));
  if(bwSample) print('bw sample (first iface):', JSON.stringify(bwSample));
  if(ispKeys.length > 0) print('isp sample:', JSON.stringify(d.isp_bandwidth[ispKeys[0]]));
});
"

echo ""
echo "=== DEVICES (id, name, isp_interfaces) ==="
docker exec noc-billing-pro-mongodb mongosh nocbillingpro --quiet --eval "
db.devices.find({}, {id:1, name:1, isp_interfaces:1, status:1}).forEach(d => {
  print(d.id, '|', d.name, '| status:', d.status, '| isp_interfaces:', JSON.stringify(d.isp_interfaces || []));
});
"

echo ""
echo "=== SNMP CONFIG ==="
docker exec noc-billing-pro-mongodb mongosh nocbillingpro --quiet --eval "
printjson(db.system_settings.findOne({_id: 'snmp_config'}));
"
