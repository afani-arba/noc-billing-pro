#!/bin/bash
# Fix: Convert array-format isp_bandwidth to object-format in existing docs
echo "=== Fixing isp_bandwidth format in traffic_history ==="
docker exec noc-billing-pro-mongodb mongosh nocbillingpro --quiet --eval "
// Find docs where isp_bandwidth is an array (bug: stored as [{k,v}] instead of {key:val})
const cursor = db.traffic_history.find({ 'isp_bandwidth.0': { \$exists: true } });
let fixed = 0;
let skipped = 0;
cursor.forEach(doc => {
  const arr = doc.isp_bandwidth;
  if (!Array.isArray(arr)) { skipped++; return; }
  // Convert [{k: 'ether1', v: {...}}] to {ether1: {...}}
  const obj = {};
  arr.forEach(item => {
    if (item && item.k) obj[item.k] = item.v;
  });
  db.traffic_history.updateOne(
    { _id: doc._id },
    { \$set: { isp_bandwidth: obj, bandwidth: obj } }
  );
  fixed++;
});
print('Fixed:', fixed, 'Skipped (already OK):', skipped);
"

echo ""
echo "=== Verify fix - latest 2 docs ==="
docker exec noc-billing-pro-mongodb mongosh nocbillingpro --quiet --eval "
db.traffic_history.find({}).sort({timestamp:-1}).limit(2).forEach(d => {
  const bwKeys = typeof d.bandwidth === 'object' && !Array.isArray(d.bandwidth) ? Object.keys(d.bandwidth) : [];
  const ispKeys = typeof d.isp_bandwidth === 'object' && !Array.isArray(d.isp_bandwidth) ? Object.keys(d.isp_bandwidth) : [];
  print('device_id:', d.device_id);
  print('bandwidth keys (should be iface names):', JSON.stringify(bwKeys));
  print('isp_bandwidth keys (should be iface names):', JSON.stringify(ispKeys));
  if(ispKeys.length > 0) {
    const sample = d.isp_bandwidth[ispKeys[0]];
    print('isp_bandwidth sample:', JSON.stringify(sample));
  }
  print('---');
});
"
