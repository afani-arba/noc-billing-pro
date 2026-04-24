import urllib.request, json
url = 'http://172.18.0.4:7557/devices/847460-F460-8474602968B4/tasks'
req = urllib.request.Request(url, data=json.dumps({"name": "refreshObject", "objectName": "InternetGatewayDevice.WANDevice.1."}).encode(), headers={'Content-Type': 'application/json'})
try:
    urllib.request.urlopen(req)
    print("Refreshed WANDevice.1.")
except Exception as e:
    print("Failed", e)

req = urllib.request.Request(url, data=json.dumps({"name": "refreshObject", "objectName": "InternetGatewayDevice.DeviceInfo."}).encode(), headers={'Content-Type': 'application/json'})
try:
    urllib.request.urlopen(req)
    print("Refreshed DeviceInfo.")
except Exception as e:
    print("Failed", e)
