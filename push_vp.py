import urllib.request, json

nbi = 'http://172.18.0.4:7557'

# Baca VP baru
with open('/tmp/virtual-parameters.json') as f:
    vps = json.load(f)

rxpower_vp = next((v for v in vps if v.get('_id') == 'RXPower'), None)
new_script = rxpower_vp['script']

print('Script length:', len(new_script))

# GenieACS NBI: PUT /virtual-parameters/{id}
# Coba berbagai format
for method in ['PUT', 'POST']:
    for path in ['/virtual-parameters/RXPower', '/virtual-parameters']:
        url = nbi + path
        payload = json.dumps({
            '_id': 'RXPower',
            'script': new_script
        }).encode()
        req = urllib.request.Request(
            url,
            data=payload,
            headers={'Content-Type': 'application/json'},
            method=method
        )
        try:
            r = urllib.request.urlopen(req, timeout=10)
            print(f'{method} {path}: SUCCESS {r.status}')
            print('Response:', r.read().decode()[:100])
            break
        except urllib.error.HTTPError as e:
            body = e.read().decode()[:100]
            print(f'{method} {path}: {e.code} {e.reason} - {body}')
        except Exception as e:
            print(f'{method} {path}: ERROR {e}')
