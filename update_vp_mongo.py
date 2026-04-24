"""
Update Virtual Parameter RXPower di MongoDB GenieACS.
MongoDB ada di 172.18.0.8:27017, database: genieacs_billing_pro, collection: virtual_parameters
"""
import json
import socket

# Baca script baru
with open('/tmp/virtual-parameters.json') as f:
    vps = json.load(f)

rxpower_vp = next((v for v in vps if v.get('_id') == 'RXPower'), None)
new_script = rxpower_vp['script']
print('New script length:', len(new_script))

# Gunakan pymongo jika tersedia
try:
    from pymongo import MongoClient
    
    client = MongoClient('172.18.0.8', 27017, serverSelectionTimeoutMS=5000)
    db = client['genieacs_billing_pro']
    
    # Cek collection name
    collections = db.list_collection_names()
    print('Collections:', collections)
    
    # Cari VP RXPower
    vp_col = db.get_collection('virtual_parameters')
    existing = vp_col.find_one({'_id': 'RXPower'})
    
    if existing:
        print('VP RXPower ditemukan, updating...')
        old_len = len(existing.get('script', ''))
        result = vp_col.update_one(
            {'_id': 'RXPower'},
            {'$set': {'script': new_script}}
        )
        print('Modified count:', result.modified_count)
        print(f'Script updated: {old_len} -> {len(new_script)} chars')
    else:
        print('VP RXPower tidak ada, inserting...')
        result = vp_col.insert_one({'_id': 'RXPower', 'script': new_script})
        print('Inserted ID:', result.inserted_id)
    
    # Verify
    updated = vp_col.find_one({'_id': 'RXPower'})
    print('Verification - Script preview:', updated['script'][:80])
    print()
    print('SUCCESS! VP RXPower diupdate.')
    
    client.close()
    
except ImportError:
    print('pymongo tidak tersedia, mencoba via raw socket...')
    print('Install: pip install pymongo')
except Exception as e:
    print('Error:', e)
    import traceback
    traceback.print_exc()
