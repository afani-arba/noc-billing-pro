import json, urllib.request

url = 'http://172.18.0.4:7557/devices?query=%7B%22_id%22%3A%22847460-F460-8474602968B4%22%7D'
d = json.loads(urllib.request.urlopen(url).read())
if d and len(d) > 0:
    dev = d[0]['InternetGatewayDevice']
    rx_paths = []
    
    def find_rx(obj, path):
        if isinstance(obj, dict):
            for k, v in obj.items():
                if k in ['RXPower', 'RxPower', 'OpticalSignalLevel', 'OpticalTransceiver']:
                    if isinstance(v, dict) and '_value' in v:
                        rx_paths.append((path + '.' + k, v['_value']))
                    elif isinstance(v, dict):
                        find_rx(v, path + '.' + k)
                elif not k.startswith('_'):
                    find_rx(v, path + '.' + k)
                    
    find_rx(dev, 'InternetGatewayDevice')
    print("Found RX Paths:")
    for p in rx_paths:
        print(p)
