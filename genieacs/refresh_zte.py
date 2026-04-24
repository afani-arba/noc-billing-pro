import urllib.request, json
url = 'http://172.18.0.4:7557/devices/847460-F460-8474602968B4/tasks'
def refresh(path):
    req = urllib.request.Request(url, data=json.dumps({"name": "refreshObject", "objectName": path}).encode(), headers={'Content-Type': 'application/json'})
    try:
        urllib.request.urlopen(req)
        print("Refreshed", path)
    except Exception as e:
        print("Failed", path, e)

refresh("InternetGatewayDevice.X_ZTE-COM_ONU_PonPower.")
refresh("InternetGatewayDevice.WANDevice.1.X_ZTE-COM_WANEPONInterfaceConfig.")
refresh("InternetGatewayDevice.WANDevice.1.X_ZTE-COM_WANGPONInterfaceConfig.")
refresh("InternetGatewayDevice.WANDevice.1.X_ZTE-COM_WANPONInterfaceConfig.")
