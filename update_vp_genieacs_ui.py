"""
Update Virtual Parameter RXPower di GenieACS via UI internal API.
GenieACS UI (172.18.0.2:3000) punya endpoint untuk manage VPs.
"""
import urllib.request, json

with open('/tmp/virtual-parameters.json') as f:
    vps = json.load(f)

rxpower_vp = next((v for v in vps if v.get('_id') == 'RXPower'), None)
new_script = rxpower_vp['script']

print('Script length:', len(new_script))

# Login ke GenieACS UI
base = 'http://172.18.0.2:3000'
login_data = json.dumps({'username': 'admin', 'password': 'admin'}).encode()
req = urllib.request.Request(
    base + '/login',
    data=login_data,
    headers={'Content-Type': 'application/json'},
    method='POST'
)
r = urllib.request.urlopen(req, timeout=5)
token = json.loads(r.read())
print('Token OK, len:', len(token))

headers = {
    'Authorization': 'Bearer ' + token,
    'Content-Type': 'application/json'
}

# Cek VPs yang ada
req2 = urllib.request.Request(
    base + '/api/virtual-parameters',
    headers=headers
)
r2 = urllib.request.urlopen(req2, timeout=5)
current_vps = json.loads(r2.read())
current_ids = [v.get('_id') for v in current_vps]
print('Existing VPs:', current_ids)

# Update atau buat VP RXPower
vp_payload = json.dumps({'script': new_script}).encode()

if 'RXPower' in current_ids:
    print('Updating existing VP RXPower...')
    req3 = urllib.request.Request(
        base + '/api/virtual-parameters/RXPower',
        data=vp_payload,
        headers=headers,
        method='PUT'
    )
else:
    print('Creating new VP RXPower...')
    req3 = urllib.request.Request(
        base + '/api/virtual-parameters',
        data=json.dumps({'_id': 'RXPower', 'script': new_script}).encode(),
        headers=headers,
        method='POST'
    )

try:
    r3 = urllib.request.urlopen(req3, timeout=10)
    print('Status:', r3.status)
    print('Response:', r3.read().decode()[:200])
except urllib.error.HTTPError as e:
    print('Error:', e.code, e.reason)
    print('Body:', e.read().decode()[:500])
