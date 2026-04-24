import json, urllib.request
url = 'http://172.18.0.4:7557/devices?query=%7B%22_id%22%3A%22847460-F460-8474602968B4%22%7D'
d = json.loads(urllib.request.urlopen(url).read())
if d and len(d) > 0:
    dev = d[0]['InternetGatewayDevice']
    
    def find_all(obj, path):
        if isinstance(obj, dict):
            for k, v in obj.items():
                if isinstance(v, dict) and '_value' in v:
                    val = v['_value']
                    # Print anything that might be an optical parameter
                    lower_k = k.lower()
                    if 'power' in lower_k or 'level' in lower_k or 'optic' in lower_k or 'attenuation' in lower_k or 'temperature' in lower_k:
                        print(path + '.' + k, ":", val)
                elif isinstance(v, dict) and not k.startswith('_'):
                    find_all(v, path + '.' + k)
                    
    find_all(dev, 'InternetGatewayDevice')
