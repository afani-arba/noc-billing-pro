import json

with open('e:\\noc-billing-pro\\genieacs\\virtual-parameters.json', 'r') as f:
    vps = json.load(f)

for vp in vps:
    if vp['_id'] == 'RXPower':
        script = vp['script']
        
        # We will add Path 8 for F460
        new_path = """
// ── Path 8: CT-COM EPON (ZTE F460 dll) ──
let p8 = declare("InternetGatewayDevice.WANDevice.1.X_CT-COM_EponInterfaceConfig.RXPower", {value: 1});
if (p8.value !== undefined && p8.value !== null) {
  let n = normalizeRx(p8.value[0]);
  if (n) return {writable: false, value: [n, "xsd:string"]};
}

// ── Path 9: CT-COM EPON Typo (ZTE F460 firmware lama) ──
let p9 = declare("InternetGatewayDevice.WANDevice.1.X_CT-COM_EponInterafceConfig.RXPower", {value: 1});
if (p9.value !== undefined && p9.value !== null) {
  let n = normalizeRx(p9.value[0]);
  if (n) return {writable: false, value: [n, "xsd:string"]};
}

return {writable: false, value: ["", "xsd:string"]};"""

        # Replace the final return statement
        script = script.replace('return {writable: false, value: ["", "xsd:string"]};', new_path)
        vp['script'] = script

with open('e:\\noc-billing-pro\\genieacs\\virtual-parameters.json', 'w') as f:
    json.dump(vps, f, indent=2)
