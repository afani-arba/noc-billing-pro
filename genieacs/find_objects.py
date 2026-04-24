import json, urllib.request

url = 'http://172.18.0.4:7557/devices?query=%7B%22_id%22%3A%22847460-F460-8474602968B4%22%7D'
d = json.loads(urllib.request.urlopen(url).read())
if d and len(d) > 0:
    dev = d[0]['InternetGatewayDevice']
    paths = []
    
    def find_objects(obj, path):
        if isinstance(obj, dict):
            for k, v in obj.items():
                if isinstance(v, dict) and '_object' in v and v['_object'] == True:
                    if 'X_ZTE' in k or 'X_CMCC' in k or 'PON' in k or 'Pon' in k or 'Epon' in k or 'Gpon' in k or 'DSL' in k or 'WANDevice' in k:
                        paths.append(path + '.' + k)
                    find_objects(v, path + '.' + k)
                elif isinstance(v, dict) and not k.startswith('_'):
                    find_objects(v, path + '.' + k)
                    
    find_objects(dev, 'InternetGatewayDevice')
    for p in paths:
        print(p)
