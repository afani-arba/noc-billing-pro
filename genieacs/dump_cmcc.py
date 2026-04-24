import json, urllib.request

url = 'http://172.18.0.4:7557/devices?query=%7B%22_id%22%3A%22847460-F460-8474602968B4%22%7D'
d = json.loads(urllib.request.urlopen(url).read())
if d and len(d) > 0:
    obj = d[0]['InternetGatewayDevice']['WANDevice']['1']['X_CMCC_EponInterfaceConfig']
    print(json.dumps(obj, indent=2))
