#!/bin/bash
echo "=== Patching backend: fix sawtooth - replace 0.0 fill with None for empty buckets ==="
docker exec noc-billing-pro-backend python3 << 'PYEOF'
with open('/app/routers/devices.py', 'r') as f:
    content = f.read()

old = '''            else:
                # Slot kosong — isi 0 agar grafik tidak loncat / continuous
                result.append({
                    "time": label, "download": 0.0, "upload": 0.0,
                    "ping": 0.0, "jitter": 0.0, "ping_raw": [], "jitter_raw": []
                })'''

new = '''            else:
                # Slot kosong — isi None agar Recharts skip titik (connectNulls=True di frontend)
                # Mengisi 0.0 menyebabkan pola sawtooth/segitiga karena setiap menit kosong.
                result.append({
                    "time": label, "download": None, "upload": None,
                    "ping": None, "jitter": None, "ping_raw": [], "jitter_raw": []
                })'''

if old in content:
    content = content.replace(old, new)
    with open('/app/routers/devices.py', 'w') as f:
        f.write(content)
    print("OK - empty bucket now returns None instead of 0.0")
else:
    # Show exact content around that area for debugging
    idx = content.find('Slot kosong')
    if idx >= 0:
        print("Found 'Slot kosong' at index", idx)
        print("Context:", repr(content[idx-100:idx+300]))
    else:
        print("ERROR: Pattern not found at all!")
PYEOF

echo ""
echo "=== Verify patch ==="
docker exec noc-billing-pro-backend grep -A5 "Slot kosong" /app/routers/devices.py

echo ""
echo "=== Restart backend ==="
docker restart noc-billing-pro-backend
echo "Waiting 8s..."
sleep 8

echo ""
echo "=== Health check ==="
curl -s http://localhost:8002/api/system/health | python3 -c "import sys,json; d=json.load(sys.stdin); print('Status:', d.get('status','?'))"
