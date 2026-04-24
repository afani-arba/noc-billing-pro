import urllib.request

print('Scanning Docker network for GenieACS NBI (port 7557)...')
found_ips = []
for i in range(2, 20):
    ip = f'172.18.0.{i}'
    try:
        r = urllib.request.urlopen(f'http://{ip}:7557/virtual-parameters', timeout=1)
        content = r.read().decode()[:100]
        print(f'FOUND: {ip} -> {content[:80]}')
        found_ips.append(ip)
    except Exception as e:
        err = str(e)
        if 'refused' not in err and 'timed out' not in err:
            print(f'  {ip}: {err[:50]}')

if not found_ips:
    print('NBI not found in 172.18.0.x range, try other ranges...')
    for i in range(2, 10):
        ip = f'172.17.0.{i}'
        try:
            r = urllib.request.urlopen(f'http://{ip}:7557/virtual-parameters', timeout=1)
            content = r.read().decode()[:100]
            print(f'FOUND 172.17.x: {ip} -> {content[:80]}')
            found_ips.append(ip)
        except Exception:
            pass
