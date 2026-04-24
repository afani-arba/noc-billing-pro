import json

d = json.load(open('/tmp/f460.json'))[0]
rx = []
def find_rx(obj, path):
    if isinstance(obj, dict):
        for k, v in obj.items():
            if k in ['RXPower', 'RxPower', 'OpticalSignalLevel', 'OpticalTransceiver']:
                if isinstance(v, dict) and '_value' in v:
                    rx.append((path + '.' + k, v['_value']))
                elif isinstance(v, dict):
                    # check deeper
                    find_rx(v, path + '.' + k)
            elif not k.startswith('_'):
                find_rx(v, path + '.' + k)

find_rx(d, '')
print(json.dumps(rx, indent=2))
