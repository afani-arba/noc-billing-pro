#!/bin/bash
echo "=== Patching backend devices.py: fix 24h interval_ms ==="
docker exec noc-billing-pro-backend python3 -c "
import re

with open('/app/routers/devices.py', 'r') as f:
    content = f.read()

# Fix 24h interval from 60_000 to 300_000
old = '\"24h\":   60_000,        # 1-menit bucket  -> 1440 titik (continuous per menit)'
new = '\"24h\":   300_000,       # 5-menit bucket  -> 288 titik (lebih efisien, hemat memory)'

if old in content:
    content = content.replace(old, new)
    # Also fix default fallback  
    content = content.replace('}.get(range, 60_000)', '}.get(range, 300_000)')
    with open('/app/routers/devices.py', 'w') as f:
        f.write(content)
    print('OK - interval_ms 24h patched: 60000 -> 300000')
else:
    # Try alternate encoding
    lines = content.split('\n')
    for i, line in enumerate(lines):
        if '24h' in line and '60_000' in line and 'bucket' in line:
            print(f'Found at line {i}: {repr(line)}')
            lines[i] = '        \"24h\":   300_000,       # 5-menit bucket  -> 288 titik'
            content = '\n'.join(lines)
            # Fix default fallback
            content = content.replace('}.get(range, 60_000)', '}.get(range, 300_000)')
            with open('/app/routers/devices.py', 'w') as f:
                f.write(content)
            print('OK - interval_ms 24h patched (fallback method)')
            break
    else:
        print('ERROR: Pattern not found!')
"

echo ""
echo "=== Verify backend patch ==="
docker exec noc-billing-pro-backend grep -n "24h\|interval_ms\|300_000\|60_000" /app/routers/devices.py | head -20

echo ""
echo "=== Restart backend ==="
docker restart noc-billing-pro-backend

echo ""
echo "Waiting 8s for backend to start..."
sleep 8

echo "=== Backend health check ==="
curl -s http://localhost:8002/api/system/health | python3 -c "import sys,json; d=json.load(sys.stdin); print('Status:', d.get('status'))"
