import urllib.request, json, urllib.parse

nbi = 'http://172.18.0.4:7557'
dev_id = '6CD2B2-F477V2-RTEGC6B21E68'

url = nbi + '/devices?query=' + urllib.parse.quote('{"_id":"' + dev_id + '"}')
r = urllib.request.urlopen(url, timeout=30)
d = json.loads(r.read())[0]

igd = d.get('InternetGatewayDevice', {})
wan1 = igd.get('WANDevice', {}).get('1', {})

print('=== WANDevice.1.X_CU_WANEPONInterfaceConfig ===')
cu_epon = wan1.get('X_CU_WANEPONInterfaceConfig', {})
print('Keys:', list(cu_epon.keys()))
for k, v in cu_epon.items():
    if not k.startswith('_'):
        val = v.get('_value') if isinstance(v, dict) else v
        print(f'  {k} = {val}')

print()
print('=== VirtualParameters ===')
vp = d.get('VirtualParameters', {})
for k, v in vp.items():
    val = v.get('_value') if isinstance(v, dict) else v
    ts = v.get('_timestamp') if isinstance(v, dict) else ''
    print(f'  {k} = {val!r}  (updated: {ts})')

print()
print('=== IGD-level X_ZTE-COM_Device ===')
zte_dev = igd.get('X_ZTE-COM_Device', {})
if zte_dev:
    for k, v in list(zte_dev.items())[:20]:
        if not k.startswith('_'):
            val = v.get('_value') if isinstance(v, dict) else v
            if isinstance(v, dict) and v.get('_object'):
                print(f'  {k} = [object, keys: {list(v.keys())[:10]}]')
            else:
                print(f'  {k} = {val}')

print()
print('=== Search for TransmitPower / OpticalTransceiver in full tree ===')
import json as j
raw_str = j.dumps(d)
# Find context around these keywords
for kw in ['TransmitPower', 'OpticalTransceiver', 'RXPower', 'RxPower']:
    idx = raw_str.find('"' + kw + '"')
    while idx != -1:
        snippet = raw_str[max(0, idx-100):idx+150]
        print(f'\n  [{kw}] context: ...{snippet}...')
        idx = raw_str.find('"' + kw + '"', idx+1)
