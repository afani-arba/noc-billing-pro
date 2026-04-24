import urllib.request, json, re

base = 'http://127.0.0.1:8002'

# Login
req = urllib.request.Request(
    base + '/api/auth/login',
    data=json.dumps({'username': 'admin', 'password': 'admin123'}).encode(),
    headers={'Content-Type': 'application/json'},
    method='POST'
)
r = urllib.request.urlopen(req, timeout=5)
token = json.loads(r.read()).get('token', '')
print('Token OK')

# Ambil semua devices F477
req2 = urllib.request.Request(
    base + '/api/genieacs/devices?search=F477&limit=5',
    headers={'Authorization': 'Bearer ' + token}
)
r2 = urllib.request.urlopen(req2, timeout=10)
data = json.loads(r2.read())
print('Jumlah F477:', len(data))

for dev in data[:1]:
    dev_id = dev.get('id', '')
    print('Device ID:', dev_id)
    print('RX Power (parsed field):', dev.get('rx_power', 'KOSONG'))
    print('ONT Temp:', dev.get('ont_temp', ''))
    print('Uptime:', dev.get('uptime', ''))
    print('Online:', dev.get('online', ''))
    print('Last Inform:', dev.get('last_inform', ''))

    # Fetch full raw tree
    import urllib.parse
    encoded = urllib.parse.quote(dev_id, safe='')
    req3 = urllib.request.Request(
        base + '/api/genieacs/device/' + encoded,
        headers={'Authorization': 'Bearer ' + token}
    )
    try:
        r3 = urllib.request.urlopen(req3, timeout=10)
        full = json.loads(r3.read())
        raw_str = json.dumps(full)
        print('Full response size:', len(raw_str))
        
        # Cari keys yang relevan
        keywords = ['RX', 'rx', 'Rx', 'PON', 'Pon', 'Optical', 'optical', 'Signal', 'signal', 'Power', 'DSL', 'GPON', 'EPON', 'ZTE', 'CT-COM']
        found_keys = set()
        for kw in keywords:
            pattern = '"' + kw
            idx = 0
            while True:
                idx = raw_str.find(pattern, idx)
                if idx == -1:
                    break
                end = raw_str.find('"', idx+1)
                if end != -1:
                    found_keys.add(raw_str[idx+1:end])
                idx += 1
        
        print('Keys yang relevan (RX/PON/Optical/Signal):')
        for k in sorted(found_keys)[:40]:
            print('  ', k)
        
        if isinstance(full, dict):
            print('Top level keys:', list(full.keys()))
    except Exception as e:
        print('Error fetch detail:', e)
