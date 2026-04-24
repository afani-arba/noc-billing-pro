import json, urllib.request, urllib.parse

vps = json.load(open('/tmp/virtual-parameters.json'))
for vp in vps:
    if vp['_id'] == 'RXPower':
        url = 'http://172.18.0.4:7557/virtual_parameters/' + urllib.parse.quote(vp['_id'])
        req = urllib.request.Request(url, data=vp.get('script','').encode('utf-8'), method='PUT')
        urllib.request.urlopen(req)
        print("Successfully updated RXPower virtual parameter.")
