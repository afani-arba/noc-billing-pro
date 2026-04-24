import json, urllib.request
url = 'http://172.18.0.4:7557/devices?query=%7B%22VirtualParameters.pppoeUsername2%22%3A%22PYK11250022%22%7D&projection=InternetGatewayDevice.WANDevice.1'
d = json.loads(urllib.request.urlopen(url).read())
if d and len(d) > 0:
    wan = d[0]['InternetGatewayDevice']['WANDevice']['1']
    keys = [k for k in wan.keys() if not k.startswith('_')]
    print("Keys in WANDevice.1:", keys)
    for k in keys:
        if 'Epon' in k or 'Gpon' in k or 'Pon' in k or 'Optical' in k or 'DSL' in k or 'Fiber' in k or 'Transceiver' in k:
            print(k, ":", wan[k])
