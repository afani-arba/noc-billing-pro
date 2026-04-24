import urllib.request, json
url = 'http://172.18.0.4:7557/devices/847460-F460-8474602968B4/tasks'

def refresh(path):
    req = urllib.request.Request(url, data=json.dumps({"name": "refreshObject", "objectName": path}).encode(), headers={'Content-Type': 'application/json'})
    try:
        print(urllib.request.urlopen(req).read().decode())
    except Exception as e:
        print("Failed", path, e)

refresh("InternetGatewayDevice.WANDevice.1.X_CMCC_EponInterfaceConfig.")
refresh("InternetGatewayDevice.WANDevice.1.X_CMCC_GponInterfaceConfig.")
refresh("InternetGatewayDevice.WANDevice.1.X_CMCC_WANEPONInterfaceConfig.")
refresh("InternetGatewayDevice.WANDevice.1.X_CMCC_WANGPONInterfaceConfig.")
refresh("InternetGatewayDevice.WANDevice.1.WANDSLInterfaceConfig.")
refresh("InternetGatewayDevice.WANDevice.1.WANPONInterfaceConfig.")
refresh("InternetGatewayDevice.WANDevice.1.OpticalSignalLevel.")
