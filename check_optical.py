import urllib.request, json, urllib.parse

nbi = 'http://172.18.0.4:7557'
dev_id = '6CD2B2-F477V2-RTEGC6B21E68'

# Fetch dengan projection ke OpticalTransceiver
projection = 'InternetGatewayDevice.WANDevice.1.X_CU_WANEPONInterfaceConfig.OpticalTransceiver'

url = (nbi + '/devices?query=' + urllib.parse.quote('{"_id":"' + dev_id + '"}')
       + '&projection=' + urllib.parse.quote(projection))
r = urllib.request.urlopen(url, timeout=15)
d = json.loads(r.read())[0]

igd = d.get('InternetGatewayDevice', {})
wan1 = igd.get('WANDevice', {}).get('1', {})
cu_epon = wan1.get('X_CU_WANEPONInterfaceConfig', {})
ot = cu_epon.get('OpticalTransceiver', {})

print('OpticalTransceiver keys:', list(ot.keys()) if isinstance(ot, dict) else str(ot))

if isinstance(ot, dict):
    for k, v in ot.items():
        val = v.get('_value') if isinstance(v, dict) else v
        ts = v.get('_timestamp') if isinstance(v, dict) else ''
        print(f'  {k} = {repr(val)}  (ts: {ts})')
