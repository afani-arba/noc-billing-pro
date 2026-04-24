import urllib.request, json, urllib.parse, re

nbi = 'http://172.18.0.4:7557'
dev_id = '6CD2B2-F477V2-RTEGC6B21E68'

# Ambil SEMUA data device tanpa projection
url = nbi + '/devices?query=' + urllib.parse.quote('{"_id":"' + dev_id + '"}')
r = urllib.request.urlopen(url, timeout=30)
devices = json.loads(r.read())

if not devices:
    print('Device not found')
    exit(1)

d = devices[0]
raw_str = json.dumps(d)

print('Total JSON size:', len(raw_str))

# Cari semua keys yang mungkin berhubungan dengan RX/PON
keywords = ['RXPower', 'RxPower', 'Optical', 'Signal', 'PON', 'GPON', 'EPON', 'X_ZTE', 'X_CT', 'Power', 'Fiber']

all_keys = set()
for kw in keywords:
    for match in re.finditer(r'"([^"]*' + kw + r'[^"]*?)"\s*:', raw_str, re.IGNORECASE):
        all_keys.add(match.group(1))

print()
print('Keys dengan kata kunci RX/PON/Optical/Signal/Power/ZTE:')
for k in sorted(all_keys)[:60]:
    print(' ', k)

# Tampilkan WANDevice structure
igd = d.get('InternetGatewayDevice', {})
wan = igd.get('WANDevice', {})

print()
if wan:
    print('WANDevice instances:', list(wan.keys()))
    for wk, wv in wan.items():
        if isinstance(wv, dict):
            print('  WANDevice.' + wk + ' top-keys:', list(wv.keys())[:25])
else:
    print('WANDevice: TIDAK ADA')
    print('IGD top-level keys:', list(igd.keys())[:30])

# Cari X_ZTE di mana saja
print()
print('Semua X_ZTE-COM occurrences:')
for match in re.finditer(r'"(X_ZTE-COM[^"]*?)"\s*:', raw_str):
    k = match.group(1)
    # Cari nilai setelah key
    idx = match.end()
    snippet = raw_str[idx:idx+100]
    print('  ' + k + ' -> ' + snippet[:80])
