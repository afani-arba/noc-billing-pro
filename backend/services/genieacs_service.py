"""
GenieACS NBI (Northbound Interface) service.
Connects to GenieACS REST API at port 7557 to manage TR-069 CPE devices.

Configure via .env:
  GENIEACS_URL=http://10.x.x.x:7557
  GENIEACS_USERNAME=admin
  GENIEACS_PASSWORD=secret
"""
import os
import logging
import requests
import time
from typing import Optional
from pathlib import Path

logger = logging.getLogger(__name__)
TIMEOUT = 30

def get_config():
    """
    Ambil konfigurasi GenieACS. 
    Prioritas: os.environ (yang sudah di-restore dari DB saat startup) -> .env file.
    """
    url = os.environ.get("GENIEACS_URL", "http://localhost:7557")
    user = os.environ.get("GENIEACS_USERNAME", "")
    pwd = os.environ.get("GENIEACS_PASSWORD", "")
    
    # Fallback ke .env jika os.environ kosong (untuk manual CLI/scripts)
    if not url or url == "http://localhost:7557":
        env_path = Path(__file__).parent.parent / ".env"
        if env_path.exists():
            try:
                lines = env_path.read_text(encoding="utf-8").splitlines()
                for line in lines:
                    if "=" in line and not line.startswith("#"):
                        k, v = line.split("=", 1)
                        kv = v.strip().strip("'").strip('"')
                        if k.strip() == "GENIEACS_URL": url = kv
                        elif k.strip() == "GENIEACS_USERNAME": user = kv
                        elif k.strip() == "GENIEACS_PASSWORD": pwd = kv
            except Exception: pass
            
    return {
        "url": url.rstrip("/"),
        "user": user,
        "pass": pwd
    }

def _auth() -> Optional[tuple]:
    cfg = get_config()
    if cfg["user"]:
        return (cfg["user"], cfg["pass"])
    return None

def _get(path: str, params: dict = None) -> any:
    cfg = get_config()
    url = f"{cfg['url']}/{path.lstrip('/')}"
    resp = requests.get(url, params=params, auth=_auth(), timeout=TIMEOUT)
    resp.raise_for_status()
    return resp.json()

def _post(path: str, data: dict = None) -> any:
    cfg = get_config()
    url = f"{cfg['url']}/{path.lstrip('/')}"
    resp = requests.post(url, json=data, auth=_auth(), timeout=TIMEOUT)
    resp.raise_for_status()
    try:
        return resp.json()
    except Exception:
        return {"status": resp.status_code}

def _delete(path: str) -> any:
    cfg = get_config()
    url = f"{cfg['url']}/{path.lstrip('/')}"
    resp = requests.delete(url, auth=_auth(), timeout=TIMEOUT)
    resp.raise_for_status()
    return {"success": True}


# ── Devices ───────────────────────────────────────────────────────────────────

def get_devices(limit: int = 200, skip: int = 0, search: str = "", model: str = "") -> list:
    """
    List all CPE devices from GenieACS.
    GenieACS query uses MongoDB-style queries via 'query' param.
    """
    # Eksplisit projection agar VirtualParameters & WANDevice fields pasti disertakan.
    # Memasukkan Device. (TR-181 / Mikrotik hAP) dan InternetGatewayDevice.WANDevice penuh.
    projection_fields = [
        "_id", "_lastInform", "_registered",
        "VirtualParameters",
        "InternetGatewayDevice.DeviceInfo",
        "InternetGatewayDevice.LANDevice",
        "InternetGatewayDevice.WANDevice",
        # --- ZTE path langsung di IGD (older firmware) ---
        "InternetGatewayDevice.X_ZTE-COM_ONU_PonPower",
        "InternetGatewayDevice.X_ZTE-COM_GponOnu",
        "InternetGatewayDevice.X_ZTE-COM_OntOptics",
        "InternetGatewayDevice.X_ZTE-COM_EponOnu",
        "InternetGatewayDevice.X_ZTE-COM_GPON",
        "InternetGatewayDevice.X_FIBERHOME-COM_GponStatus",
        "InternetGatewayDevice.X_CT-COM_GponOntPower",
        # --- WANDevice (PPPoE IP + koneksi + PON interface) ---
        "InternetGatewayDevice.WANDevice.1.WANConnectionDevice.1.WANPPPConnection.1",
        "InternetGatewayDevice.WANDevice.1.WANConnectionDevice.1.WANIPConnection.1",
        # --- ZTE EPON/GPON via WANDevice.1 (path utama F663NV3A) ---
        "InternetGatewayDevice.WANDevice.1.X_ZTE-COM_WANPONInterfaceConfig",
        "InternetGatewayDevice.WANDevice.1.X_ZTE-COM_WANEPONInterfaceConfig",
        "InternetGatewayDevice.WANDevice.1.X_ZTE-COM_WANGPONInterfaceConfig",
        # --- CT-COM GPON/EPON via WANDevice.1 ---
        "InternetGatewayDevice.WANDevice.1.X_CT-COM_GponInterfaceConfig",
        "InternetGatewayDevice.WANDevice.1.X_CT-COM_EponInterfaceConfig",
        "InternetGatewayDevice.WANDevice.1.X_CT-COM_WANPONInterfaceConfig",
        # --- TR-181 equivalents (Mikrotik, TP-Link, dll) ---
        "Device.DeviceInfo",
        "Device.LANDevice",
        "Device.WANDevice",
        "Device.IP",
        "Device.PPP",
        "Device.Optical"
    ]
    params = {
        "limit": limit,
        "skip": skip,
        "projection": ",".join(projection_fields),
    }
    if search:
        params["query"] = (
            '{"$or":['
            f'{{"_id":{{"$regex":"{search}","$options":"i"}}}},'
            f'{{"InternetGatewayDevice.DeviceInfo.ModelName._value":{{"$regex":"{search}","$options":"i"}}}},'
            f'{{"InternetGatewayDevice.WANDevice.1.WANConnectionDevice.1.WANIPConnection.1.ExternalIPAddress._value":{{"$regex":"{search}","$options":"i"}}}},'
            f'{{"InternetGatewayDevice.WANDevice.1.WANConnectionDevice.1.WANPPPConnection.1.Username._value":{{"$regex":"{search}","$options":"i"}}}}'
            ']}'
        )
    elif model:
        params["query"] = f'{{"InternetGatewayDevice.DeviceInfo.ModelName._value":{{"$regex":"{model}","$options":"i"}}}}'
    return _get("/devices", params)


def get_device(device_id: str) -> dict:
    """Get full parameter tree of one device."""
    return _get(f"/devices/{requests.utils.quote(device_id, safe='')}")


def get_connected_devices_realtime(device_id: str) -> int:
    """
    Ambil jumlah perangkat terhubung (LAN Host) secara REAL-TIME langsung dari GenieACS NBI.
    Bypass cache MongoDB — dipanggil saat refresh client portal.
    Return: jumlah perangkat aktif (integer), atau -1 jika gagal/timeout.
    """
    params = {
        "projection": "InternetGatewayDevice.LANDevice,Device.Hosts",
        "limit": 1,
        "query": '{\"_id\":\"' + device_id.replace('"', '\\"') + '\"}',
    }
    try:
        results = _get("/devices", params)
        if not results:
            return -1
        d = results[0]
        d_igd = d.get("InternetGatewayDevice") or {}
        d_dev = d.get("Device") or {}

        # TR-098: InternetGatewayDevice.LANDevice.*.Hosts.Host.*
        for root in [d_igd]:
            lan_obj = root.get("LANDevice", {})
            if isinstance(lan_obj, dict):
                for ld in lan_obj.values():
                    if isinstance(ld, dict):
                        hosts_obj = ld.get("Hosts", {})
                        if isinstance(hosts_obj, dict):
                            # Prioritas 1: HostNumberOfEntries
                            h = (hosts_obj.get("HostNumberOfEntries") or {}).get("_value") or \
                                hosts_obj.get("HostNumberOfEntries", {})
                            if isinstance(h, dict):
                                h = h.get("_value", "")
                            if h and str(h) not in ("", "0"):
                                return int(h)
                            # Prioritas 2: hitung dari Host list
                            h_list = hosts_obj.get("Host", {})
                            if isinstance(h_list, dict) and h_list:
                                return len([k for k, v in h_list.items() if isinstance(v, dict)])
        # TR-181: Device.Hosts.Host.*
        hosts = d_dev.get("Hosts", {}).get("Host", {})
        if isinstance(hosts, dict) and hosts:
            return len([k for k, v in hosts.items() if isinstance(v, dict)])
        return 0
    except Exception:
        return -1


def get_rx_power_raw(device_id: str) -> str:
    """
    Fetch RXPower directly with minimal projection — untuk fallback / debug.
    Tries VirtualParameters.RXPower then WANDevice ZTE path.
    """
    fields = [
        "VirtualParameters.RXPower",
        "InternetGatewayDevice.WANDevice.1.X_ZTE-COM_WANPONInterfaceConfig.RXPower",
        "InternetGatewayDevice.WANDevice.1.X_ZTE-COM_WANEPONInterfaceConfig.RXPower",
        "InternetGatewayDevice.WANDevice.1.X_CT-COM_GponInterfaceConfig.RXPower",
        "InternetGatewayDevice.WANDevice.1.X_CT-COM_EponInterfaceConfig.RXPower",
    ]
    params = {
        "projection": ",".join(fields),
        "limit": 1,
        "query": '{"_id":"' + device_id.replace('"', '\\"') + '"}',
    }
    try:
        results = _get("/devices", params)
        if not results:
            return ""
        d = results[0]
        vp = d.get("VirtualParameters", {})
        rxp = vp.get("RXPower", {})
        if isinstance(rxp, dict) and rxp.get("_value") not in (None, "", "0", "0.0"):
            return str(rxp["_value"])
        igd = d.get("InternetGatewayDevice", {})
        wan1 = igd.get("WANDevice", {}).get("1", {})
        for cfg_key in [
            "X_ZTE-COM_WANPONInterfaceConfig",
            "X_ZTE-COM_WANEPONInterfaceConfig",
            "X_CT-COM_GponInterfaceConfig",
            "X_CT-COM_EponInterfaceConfig",
        ]:
            cfg = wan1.get(cfg_key, {})
            if isinstance(cfg, dict):
                rx = cfg.get("RXPower", {})
                if isinstance(rx, dict) and rx.get("_value") not in (None, "", "0", "0.0"):
                    return str(rx["_value"])
        return ""
    except Exception:
        return ""


def get_device_summary(device_id: str) -> dict:
    """Get key info fields for a device (lighter than full tree)."""
    fields = [
        "_id", "_lastInform", "_registered",
        "InternetGatewayDevice.DeviceInfo.Manufacturer._value",
        "InternetGatewayDevice.DeviceInfo.ModelName._value",
        "InternetGatewayDevice.DeviceInfo.SerialNumber._value",
        "InternetGatewayDevice.DeviceInfo.SoftwareVersion._value",
        "InternetGatewayDevice.WANDevice.1.WANConnectionDevice.1.WANIPConnection.1.ExternalIPAddress._value",
        "InternetGatewayDevice.DeviceInfo.UpTime._value",
        "VirtualParameters.Tag._value",
    ]
    params = {
        "projection": ",".join(fields),
        "limit": 1,
        "query": f'{{"_id":"{device_id}"}}',
    }
    results = _get("/devices", params)
    return results[0] if results else {}


def reboot_device(device_id: str) -> dict:
    """Send reboot task to device."""
    return _post(f"/devices/{requests.utils.quote(device_id, safe='')}/tasks?timeout=30000&connection_request", {"name": "reboot"})


def factory_reset_device(device_id: str) -> dict:
    """Send factory reset task to device."""
    return _post(f"/devices/{requests.utils.quote(device_id, safe='')}/tasks?timeout=30000&connection_request", {"name": "factoryReset"})


def refresh_device(device_id: str) -> dict:
    """Send refreshObject task to refresh all parameters."""
    return _post(
        f"/devices/{requests.utils.quote(device_id, safe='')}/tasks?timeout=30000&connection_request",
        {"name": "refreshObject", "objectName": ""}
    )


def set_parameter(device_id: str, param_name: str, param_value: str, param_type: str = "xsd:string") -> dict:
    """Set a TR-069 parameter on device."""
    return _post(
        f"/devices/{requests.utils.quote(device_id, safe='')}/tasks?timeout=30000&connection_request",
        {
            "name": "setParameterValues",
            "parameterValues": [[param_name, param_value, param_type]]
        }
    )


def summon_device(device_id: str) -> dict:
    """
    Send a connection request to the device (summon it to check in to ACS).
    
    IMPORTANT: Do NOT attach a task body to the connection_request URL.
    Some devices (ZTE EG8145V5, Huawei EG8145x6) return cwmp:8002 Internal Error
    when GenieACS queues a refreshObject task with empty objectName alongside
    the connection request.
    
    Strategy:
    1. First send a bare connection_request (POST with empty body) to wake the device.
    2. If device is online (200 response), separately queue a refreshObject task
       with the full root objectName to avoid the empty-string fault.
    """
    cfg = get_config()
    enc_id = requests.utils.quote(device_id, safe='')
    
    # Step 1: Bare connection request — wake the device (empty JSON body, no task created)
    # GenieACS accepts empty body {} with ?connection_request to send a pure ping without creating a task.
    # TIDAK menggunakan json=None karena requests tidak set Content-Type header,
    # yang menyebabkan GenieACS return 401 Unauthorized.
    cr_url = f"{cfg['url']}/devices/{enc_id}/tasks?connection_request"
    resp = requests.post(cr_url, json={}, auth=_auth(), timeout=TIMEOUT)
    
    # 200 = device is online & responded immediately
    # 202 = device offline, task queued for next inform
    # 4xx/5xx = error
    if resp.status_code not in (200, 202):
        resp.raise_for_status()
    
    is_online = resp.status_code == 200
    
    # Step 2: If device is online, queue a proper refreshObject with root path
    if is_online:
        try:
            refresh_url = f"{cfg['url']}/devices/{enc_id}/tasks"
            requests.post(
                refresh_url,
                json={"name": "refreshObject", "objectName": "InternetGatewayDevice."},
                auth=_auth(),
                timeout=TIMEOUT
            )
        except Exception:
            pass  # Non-critical — connection request already went through
    
    return {"status": resp.status_code, "queued": not is_online, "online": is_online}


# ── Faults ────────────────────────────────────────────────────────────────────

def get_faults(limit: int = 100) -> list:
    """List recent faults across all devices."""
    return _get("/faults", {"limit": limit})


def delete_fault(fault_id: str) -> dict:
    """Delete/resolve a fault."""
    return _delete(f"/faults/{fault_id}")


# ── Tasks ─────────────────────────────────────────────────────────────────────

def get_tasks(device_id: str) -> list:
    """List pending tasks for a device."""
    params = {"query": f'{{"device":"{device_id}"}}'}
    return _get("/tasks", params)


# ── Presets & Files ───────────────────────────────────────────────────────────

def get_presets() -> list:
    """List all provisioning presets."""
    return _get("/presets")


def get_files() -> list:
    """List firmware/config files uploaded to GenieACS."""
    return _get("/files")


# ── Advanced Features (ZTP, Self-Care, Hard Isolation) ────────────────────────

def _get_serial_pass(device_id: str) -> str:
    """
    Derive ConnectionRequestPassword from Device ID.
    Standard: Last 8 characters of the serial number portion.
    Example: 00259E-EG8145V5-485754432B0466B3 -> 2B0466B3
    """
    parts = device_id.split("-")
    serial = parts[-1] if parts else device_id
    password = serial[-8:] if len(serial) >= 8 else serial
    return password

def _find_pppoe_wan_path(device_id: str) -> str:
    """
    Auto-discover correct WANConnectionDevice index for PPPoE INTERNET service.

    Pass 1: Cari WANConnectionDevice yang punya WANPPPConnection dengan ServiceList=INTERNET
    Pass 2: Jika tidak ada label INTERNET, gunakan WANConnectionDevice pertama yang punya WANPPPConnection
    Fallback: WANConnectionDevice.1.WANPPPConnection.1 (umum untuk home ONT ZTE EG8145V5, F663N)
    """
    default = "InternetGatewayDevice.WANDevice.1.WANConnectionDevice.1.WANPPPConnection.1"
    try:
        params = {
            "projection": "InternetGatewayDevice.WANDevice.1.WANConnectionDevice",
            "limit": 1,
            "query": '{\"_id\":\"' + device_id.replace('"', '\\"') + '\"}',
        }
        results = _get("/devices", params)
        if not results:
            logger.warning(f"ZTP discovery: device {device_id} not found in GenieACS cache, using default path")
            return default

        d = results[0]
        wan_dev = (d.get("InternetGatewayDevice") or {}).get("WANDevice", {}).get("1", {})
        wan_conn_devs = wan_dev.get("WANConnectionDevice", {})
        if not isinstance(wan_conn_devs, dict) or not wan_conn_devs:
            logger.warning("ZTP discovery: WANConnectionDevice not in cache, using fallback .1")
            return default

        # ── Pass 1: Cari yang ServiceList mengandung "INTERNET" ──────────────
        any_ppp_idx = None  # simpan index WANPPPConnection pertama yang ditemukan
        for idx_str in sorted(wan_conn_devs.keys(), key=lambda x: int(x) if x.isdigit() else 999):
            conn_dev = wan_conn_devs[idx_str]
            if not idx_str.isdigit() or not isinstance(conn_dev, dict):
                continue
            wan_ppp = conn_dev.get("WANPPPConnection", {})
            if not isinstance(wan_ppp, dict) or not wan_ppp:
                continue
            for ppp_val in wan_ppp.values():
                if not isinstance(ppp_val, dict):
                    continue
                # Simpan index pertama yang punya WANPPPConnection (untuk fallback pass 2)
                if any_ppp_idx is None:
                    any_ppp_idx = idx_str
                # Cek ServiceList mengandung INTERNET
                svc_raw = ppp_val.get("ServiceList", {})
                svc = svc_raw.get("_value", "") if isinstance(svc_raw, dict) else str(svc_raw or "")
                if "INTERNET" in svc.upper():
                    path = f"InternetGatewayDevice.WANDevice.1.WANConnectionDevice.{idx_str}.WANPPPConnection.1"
                    logger.info(f"ZTP discovery (pass1): INTERNET PPPoE found at WANConnectionDevice.{idx_str}")
                    return path

        # ── Pass 2: Gunakan index pertama yang punya WANPPPConnection ─────────
        if any_ppp_idx is not None:
            path = f"InternetGatewayDevice.WANDevice.1.WANConnectionDevice.{any_ppp_idx}.WANPPPConnection.1"
            logger.info(f"ZTP discovery (pass2): Using first WANPPPConnection at WANConnectionDevice.{any_ppp_idx}")
            return path

        # ── Final fallback: .1 (home ONT ZTE biasanya internet di sini) ───────
        logger.warning("ZTP discovery: no WANPPPConnection in cache, falling back to WANConnectionDevice.1")
        return default

    except Exception as e:
        logger.error(f"ZTP _find_pppoe_wan_path failed: {e}")
        return default


def provision_cpe(device_id: str, pppoe_user: str, pppoe_pass: str, ssid: str, wifi_pass: str, vlan_id: str = "") -> dict:
    """
    Zero Touch Provisioning: Mengatur PPPoE dan WiFi SSID/Password pada ONT ZTE.

    Alur:
    1. Cek apakah WANPPPConnection sudah ada di device cache GenieACS.
    2a. Jika SUDAH ada → langsung setParameterValues ke path yang ditemukan.
    2b. Jika BELUM ada (fresh ONT) →
        - addObject WANPPPConnection (di dalam WANConnectionDevice.1)
        - setParameterValues credentials
        Semua task dieksekusi GenieACS dalam satu sesi TR-069.
    """
    cfg = get_config()
    enc_id  = requests.utils.quote(device_id, safe="")
    cr_url   = f"{cfg['url']}/devices/{enc_id}/tasks?timeout=30000&connection_request"
    task_url = f"{cfg['url']}/devices/{enc_id}/tasks"

    has_ppp_wan = False
    existing_path = _find_pppoe_wan_path(device_id)
    try:
        chk_params = {
            "projection": "InternetGatewayDevice.WANDevice.1.WANConnectionDevice",
            "limit": 1,
            "query": '{\"_id\":\"' + device_id.replace('"', '\\"') + '\"}',
        }
        chk = _get("/devices", chk_params)
        if chk:
            wan_dev = (chk[0].get("InternetGatewayDevice") or {}).get("WANDevice", {}).get("1", {})
            wan_cds = wan_dev.get("WANConnectionDevice", {})
            wan_cd_keys = [k for k in wan_cds.keys() if k.isdigit()]
            logger.info(f"ZTP detection: WANConnectionDevice keys={wan_cd_keys}")
            
            # Cek di SEMUA index WANConnectionDevice apakah ada WANPPPConnection
            for idx in wan_cd_keys:
                ppp = wan_cds.get(idx, {}).get("WANPPPConnection", {})
                if isinstance(ppp, dict) and ppp:
                    # Pastikan ppp itu dict object dan bukan _object flag kosong, cek isi keys angka
                    ppp_keys = [k for k in ppp.keys() if k.isdigit()]
                    if ppp_keys:
                        has_ppp_wan = True
                        logger.info(f"ZTP detection: found existing PPPoE WAN at WANConnectionDevice.{idx}.WANPPPConnection.{ppp_keys[0]}")
                        # override existing_path jika discovery awal fallback ke default tapi aslinya ada di index ini
                        existing_path = f"InternetGatewayDevice.WANDevice.1.WANConnectionDevice.{idx}.WANPPPConnection.{ppp_keys[0]}"
                        break
            
    except Exception as e:
        logger.warning(f"ZTP WANPPPConnection check error: {e}")


    # ── Shared params: WiFi + Management ─────────────────────────────────────
    mgmt_pass = _get_serial_pass(device_id)
    extra_params = [
        ["InternetGatewayDevice.ManagementServer.ConnectionRequestUsername", "admin",    "xsd:string"],
        ["InternetGatewayDevice.ManagementServer.ConnectionRequestPassword", mgmt_pass, "xsd:string"],
    ]
    if ssid:
        extra_params.append(["InternetGatewayDevice.LANDevice.1.WLANConfiguration.1.SSID", ssid, "xsd:string"])
    if wifi_pass:
        extra_params.extend([
            ["InternetGatewayDevice.LANDevice.1.WLANConfiguration.1.PreSharedKey.1.PreSharedKey", wifi_pass, "xsd:string"],
            ["InternetGatewayDevice.LANDevice.1.WLANConfiguration.1.PreSharedKey.1.KeyPassphrase", wifi_pass, "xsd:string"],
        ])

    if has_ppp_wan:
        # ── 2a: PPPoE profile sudah ada — langsung set ───────────────────────
        bp = existing_path
        pppoe_params = []
        if pppoe_user and pppoe_pass:
            pppoe_params.extend([
                [f"{bp}.Enable",           "1",         "xsd:boolean"],
                [f"{bp}.ConnectionType",   "IP_Routed", "xsd:string"],
                [f"{bp}.Username",         pppoe_user,  "xsd:string"],
                [f"{bp}.Password",         pppoe_pass,  "xsd:string"],
                [f"{bp}.NATEnabled",       "1",         "xsd:boolean"],
                [f"{bp}.ConnectionTrigger","AlwaysOn",  "xsd:string"],
                [f"{bp}.ServiceList",      "INTERNET",  "xsd:string"],
            ])
            if vlan_id:
                pppoe_params.append([f"{bp}.X_ZTE-COM_VLANID", str(vlan_id), "xsd:string"])
        all_params = pppoe_params + extra_params
        res = requests.post(cr_url, json={"name": "setParameterValues", "parameterValues": all_params}, auth=_auth(), timeout=TIMEOUT)
        res.raise_for_status()
        logger.info(f"ZTP [existing] sent to {device_id}: status={res.status_code} path={bp} user={pppoe_user}")
        return {"success": True, "message": f"PPPoE config dikirim ke {bp}", "result": res.status_code}

    else:
        # ── 2b: Fresh ONT — buat WAN PPPoE profile baru via addObject ────────
        # CRITICAL FIX: GenieACS API v1.2 MENGHARUSKAN "objectName" TANPA TITIK DI AKHIR!
        # Jika menggunakan titik akhir (cth: ...WANConnectionDevice.), GenieACS akan mem-parsing
        # menjadi "WANConnectionDevice..[]" yang menyebabkan Fault 9005 (Invalid parameter path).
        new_wan_cd = "InternetGatewayDevice.WANDevice.1.WANConnectionDevice"
        new_ppp_cd = "InternetGatewayDevice.WANDevice.1.WANConnectionDevice.2.WANPPPConnection"
        ppp_base   = "InternetGatewayDevice.WANDevice.1.WANConnectionDevice.2.WANPPPConnection.1"

        pppoe_params = []
        if pppoe_user and pppoe_pass:
            pppoe_params.extend([
                [f"{ppp_base}.Enable",           "1",         "xsd:boolean"],
                [f"{ppp_base}.ConnectionType",   "IP_Routed", "xsd:string"],
                [f"{ppp_base}.Username",         pppoe_user,  "xsd:string"],
                [f"{ppp_base}.Password",         pppoe_pass,  "xsd:string"],
                [f"{ppp_base}.NATEnabled",       "1",         "xsd:boolean"],
                [f"{ppp_base}.ConnectionTrigger","AlwaysOn",  "xsd:string"],
                [f"{ppp_base}.ServiceList",      "INTERNET",  "xsd:string"],
                [f"{ppp_base}.Name",             "INTERNET",  "xsd:string"],
            ])
            # Explicitly set VLAN tags to avoid Huawei/ZTE factory defaults (yang biasanya otomatis Enable VLAN 1)
            # Jika user tidak mengisi vlan_id, kita force '0' atau '' agar VLAN OFF (Untagged).
            if vlan_id:
                pppoe_params.append([f"{ppp_base}.X_ZTE-COM_VLANID", str(vlan_id), "xsd:string"])
                pppoe_params.append([f"{ppp_base}.X_HW_VLAN", str(vlan_id), "xsd:string"])
            else:
                # Disable VLAN (Untagged)
                pppoe_params.append([f"{ppp_base}.X_ZTE-COM_VLANID", "0", "xsd:string"])
                pppoe_params.append([f"{ppp_base}.X_HW_VLAN", "0", "xsd:string"])

        # Task 1: addObject WANConnectionDevice (TANPA trailing dot) -> Menghasilkan index .2
        t1 = requests.post(cr_url, json={"name": "addObject", "objectName": new_wan_cd}, auth=_auth(), timeout=TIMEOUT)
        t1.raise_for_status()

        # Task 2: addObject WANPPPConnection di dalam WANConnectionDevice.2 (TANPA trailing dot) -> Menghasilkan index .1
        t2 = requests.post(cr_url, json={"name": "addObject", "objectName": new_ppp_cd}, auth=_auth(), timeout=TIMEOUT)
        t2.raise_for_status()

        # Task 3: setParameterValues PPPoE + WiFi + Mgmt pada hasil addObject (index 2 / 1)
        res = requests.post(task_url, json={"name": "setParameterValues", "parameterValues": pppoe_params + extra_params}, auth=_auth(), timeout=TIMEOUT)
        res.raise_for_status()

        logger.info(f"ZTP [fresh ONT] 3 tasks queued for {device_id}: addObject WAN, addObject PPPoE, setParams user={pppoe_user}")
        return {
            "success": True,
            "message": (
                "ONT fresh: 3 Task TR-069 diantrekan — "
                "(1) Buat WANConnectionDevice.2, (2) Buat WANPPPConnection, "
                "(3) Set Username/Password/NAT/SSID. "
                "GenieACS eksekusi saat ONT merespons connection request."
            ),
            "result": res.status_code
        }




def get_wifi_settings(device_id: str) -> dict:
    """Mengambil konfigurasi WiFi SSID dan Password dari ONT."""
    fields = [
        "InternetGatewayDevice.LANDevice.1.WLANConfiguration.1.SSID",
        "InternetGatewayDevice.LANDevice.1.WLANConfiguration.1.PreSharedKey.1.PreSharedKey",
        "InternetGatewayDevice.LANDevice.1.WLANConfiguration.1.AssociatedDeviceNumberOfEntries"
    ]
    params = {
        "projection": ",".join(fields),
        "limit": 1,
        "query": f'{{"_id":"{device_id}"}}',
    }
    results = _get("/devices", params)
    if not results:
        return {"ssid": "", "password": "", "connected_devices": 0}
    
    d = results[0]
    wlan = d.get("InternetGatewayDevice", {}).get("LANDevice", {}).get("1", {}).get("WLANConfiguration", {}).get("1", {})
    ssid = wlan.get("SSID", {}).get("_value", "") if isinstance(wlan.get("SSID"), dict) else wlan.get("SSID", "")
    
    psk1 = wlan.get("PreSharedKey", {}).get("1", {})
    password = psk1.get("PreSharedKey", {}).get("_value", "") if isinstance(psk1.get("PreSharedKey"), dict) else psk1.get("PreSharedKey", "")
    
    connected_str = wlan.get("AssociatedDeviceNumberOfEntries", {}).get("_value", "0") if isinstance(wlan.get("AssociatedDeviceNumberOfEntries"), dict) else wlan.get("AssociatedDeviceNumberOfEntries", "0")
    try:
        connected = int(connected_str)
    except:
        connected = 0
    
    return {"ssid": str(ssid).strip(), "password": str(password).strip(), "connected_devices": connected}


def set_wifi_settings(device_id: str, ssid: str, password: str) -> dict:
    """Mengubah SSID dan Password WiFi."""
    params = []
    if ssid:
        params.append(["InternetGatewayDevice.LANDevice.1.WLANConfiguration.1.SSID", ssid, "xsd:string"])
    if password:
        params.extend([
            ["InternetGatewayDevice.LANDevice.1.WLANConfiguration.1.PreSharedKey.1.PreSharedKey", password, "xsd:string"],
            ["InternetGatewayDevice.LANDevice.1.WLANConfiguration.1.PreSharedKey.1.KeyPassphrase", password, "xsd:string"]
        ])
        
    if not params:
        return {"success": False, "message": "SSID atau password kosong"}
        
    res = _post(
        f"/devices/{requests.utils.quote(device_id, safe='')}/tasks?timeout=30000&connection_request",
        {
            "name": "setParameterValues",
            "parameterValues": params
        }
    )
    return {"success": True, "message": "Perintah ubah WiFi dikirim", "result": res}


def set_hard_isolation(device_id: str, enable: bool) -> dict:
    """Isolasi Hardcore: Menonaktifkan/Mengaktifkan pemancaran sinyal WiFi (WLAN Enable)."""
    val = "0" if enable else "1"
    
    res = _post(
        f"/devices/{requests.utils.quote(device_id, safe='')}/tasks?timeout=30000&connection_request",
        {
            "name": "setParameterValues",
            "parameterValues": [
                ["InternetGatewayDevice.LANDevice.1.WLANConfiguration.1.Enable", val, "boolean"]
            ]
        }
    )
    status_msg = "Sinyal WiFi dimatikan (Isolasi Hardcore)" if enable else "Sinyal WiFi diaktifkan kembali"
    return {"success": True, "message": status_msg, "result": res}


# ── Stats ─────────────────────────────────────────────────────────────────────

def get_stats() -> dict:
    """
    Return overall stats: total devices, online count, faults count.
    'Online' = lastInform within last 15 minutes.
    """
    try:
        all_devices = _get("/devices", {"limit": 5000, "projection": "_id,_lastInform"})
        total = len(all_devices)

        from datetime import datetime, timezone, timedelta
        cutoff = datetime.now(timezone.utc) - timedelta(minutes=15)

        online = 0
        for d in all_devices:
            last = d.get("_lastInform")
            if last:
                try:
                    last_dt = datetime.fromisoformat(last.replace("Z", "+00:00"))
                    if last_dt > cutoff:
                        online += 1
                except Exception:
                    pass

        faults = _get("/faults", {"limit": 1000, "projection": "_id"})
        return {"total": total, "online": online, "offline": total - online, "faults": len(faults)}
    except Exception as e:
        logger.warning(f"GenieACS stats error: {e}")
        return {"total": 0, "online": 0, "offline": 0, "faults": 0}


def check_health() -> dict:
    """
    Test connectivity to GenieACS server.
    Returns: {connected, url, latency_ms, error}
    """
    cfg = get_config()
    url = cfg["url"]
    if not url or url == "http://localhost:7557":
        # If not configured, return not configured
        configured = bool(os.environ.get("GENIEACS_URL", ""))
        if not configured:
            return {"connected": False, "url": url, "latency_ms": 0, "error": "GENIEACS_URL not configured in .env"}

    try:
        t0 = time.time()
        resp = requests.get(f"{url}/devices", params={"limit": 1, "projection": "_id"},
                            auth=_auth(), timeout=5)
        latency = round((time.time() - t0) * 1000)
        if resp.status_code in (200, 401):
            if resp.status_code == 401:
                return {"connected": False, "url": url, "latency_ms": latency,
                        "error": "Authentication failed - check GENIEACS_USERNAME/PASSWORD"}
            return {"connected": True, "url": url, "latency_ms": latency, "error": None}
        return {"connected": False, "url": url, "latency_ms": latency,
                "error": f"HTTP {resp.status_code}"}
    except requests.exceptions.ConnectionError:
        return {"connected": False, "url": url, "latency_ms": 0,
                "error": "Connection refused - GenieACS server tidak aktif atau URL salah"}
    except requests.exceptions.Timeout:
        return {"connected": False, "url": url, "latency_ms": 5000,
                "error": "Connection timeout (>5s)"}
    except Exception as e:
        return {"connected": False, "url": url, "latency_ms": 0, "error": str(e)}
