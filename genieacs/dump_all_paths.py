import json, urllib.request

url = 'http://172.18.0.4:7557/devices?query=%7B%22_id%22%3A%22847460-F460-8474602968B4%22%7D'
d = json.loads(urllib.request.urlopen(url).read())
if d and len(d) > 0:
    dev = d[0]['InternetGatewayDevice']
    
    with open('/tmp/all_paths.txt', 'w') as f:
        def dump_all(obj, path):
            if isinstance(obj, dict):
                for k, v in obj.items():
                    if isinstance(v, dict) and '_value' in v:
                        val = v['_value']
                        f.write(path + '.' + k + " = " + str(val) + "\n")
                    elif isinstance(v, dict) and not k.startswith('_'):
                        dump_all(v, path + '.' + k)
                        
        dump_all(dev, 'InternetGatewayDevice')
    print("Done dumping paths to /tmp/all_paths.txt")
