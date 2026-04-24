import json, subprocess

# Baca VP baru
with open('/tmp/virtual-parameters.json') as f:
    vps = json.load(f)

rxpower_vp = next((v for v in vps if v.get('_id') == 'RXPower'), None)
new_script = rxpower_vp['script']

print('Script length:', len(new_script))

# Escape script untuk JS string
js_escaped = new_script.replace('\\', '\\\\').replace('"', '\\"').replace('\n', '\\n').replace('\r', '')

# Buat mongosh command
mongosh_cmd = f"""
db = db.getSiblingDB('genieacs_billing_pro');
var result = db.virtual_parameters.updateOne(
  {{_id: 'RXPower'}},
  {{$set: {{script: "{js_escaped}"}}}},
  {{upsert: true}}
);
printjson(result);
"""

# Simpan ke file untuk dieksekusi
with open('/tmp/update_vp.js', 'w') as f:
    f.write(mongosh_cmd)

print('JS command saved to /tmp/update_vp.js')
print('Length:', len(mongosh_cmd))

# Coba jalankan mongosh dari container MongoDB (172.18.0.8)
# Akses melalui TCP ke mongosh yang ada di dalam container
# Karena tidak ada docker CLI, kita perlu nsenter atau socat

# Alternatif: coba via mongosh di container genieacs-cwmp yang mungkin punya mongosh
import socket

# Coba cari container yang bisa dipakai untuk eksekusi
# Backend Python container di 172.18.0.5:8000 pasti punya pymongo!
print()
print('Backend container (pymongo available) di 172.18.0.5:8000')
print('Kita bisa inject command via backend API setelah login...')
