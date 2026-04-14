"""
PPPoE users router: list, create, update, delete via MikroTik API.
"""
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from typing import Optional
from core.db import get_db
from core.auth import get_current_user, require_admin, require_write
from mikrotik_api import get_api_client

router = APIRouter(tags=["pppoe"])


class PPPoEUserCreate(BaseModel):
    name: str
    password: str
    profile: str = "default"
    service: str = "pppoe"
    comment: str = ""


class PPPoEUserUpdate(BaseModel):
    name: Optional[str] = None
    password: Optional[str] = None
    profile: Optional[str] = None
    service: Optional[str] = None
    comment: Optional[str] = None
    disabled: Optional[str] = None


async def _get_mt_api(device_id: str):
    db = get_db()
    device = await db.devices.find_one({"id": device_id}, {"_id": 0})
    if not device:
        raise HTTPException(404, "Device not found")
    return get_api_client(device), device


@router.get("/pppoe-users")
async def list_pppoe_users(device_id: str = "", search: str = "", user=Depends(get_current_user)):
    if not device_id:
        return []
    mt, device = await _get_mt_api(device_id)

    # Ambil secrets dan active secara terpisah agar jika salah satu gagal
    # (misal: device tidak punya PPPoE server), yang lain tetap ditampilkan
    try:
        secrets = await mt.list_pppoe_secrets()
        if not isinstance(secrets, list):
            secrets = []
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(503, f"Gagal mengambil PPPoE secrets: {e}")

    try:
        active_list = await mt.list_pppoe_active()
        if not isinstance(active_list, list):
            active_list = []
    except Exception:
        # active bisa gagal jika PPPoE server belum dikonfigurasi — tidak fatal
        active_list = []

    # Build set nama user yang sedang online
    active_names = {a.get("name", "") for a in active_list}

    # Filter: hanya tampilkan user dengan service "pppoe" atau kosong (default pppoe)
    # ROS6 mengembalikan field "service", ROS7 juga sama
    result = []
    for s in secrets:
        svc = str(s.get("service", "pppoe") or "pppoe").lower()
        # Tampilkan jika service adalah pppoe atau any
        if svc not in ("pppoe", "any", ""):
            continue
        s["is_online"] = s.get("name", "") in active_names
        s["active_count"] = len(active_names)  # info total active
        if search and search.lower() not in str(s).lower():
            continue
        result.append(s)

    return result



@router.post("/pppoe-users", status_code=201)
async def create_pppoe_user(device_id: str, data: PPPoEUserCreate, user=Depends(require_write)):
    mt, _ = await _get_mt_api(device_id)
    body = {k: v for k, v in data.model_dump().items() if v}
    try:
        return await mt.create_pppoe_secret(body)
    except Exception as e:
        raise HTTPException(503, f"MikroTik: {e}")


@router.put("/pppoe-users/{mt_id}")
async def update_pppoe_user(mt_id: str, device_id: str, data: PPPoEUserUpdate, user=Depends(require_write)):
    mt, _ = await _get_mt_api(device_id)
    body = {k: v for k, v in data.model_dump().items() if v is not None}
    try:
        return await mt.update_pppoe_secret(mt_id, body)
    except Exception as e:
        raise HTTPException(503, f"MikroTik: {e}")


@router.delete("/pppoe-users/{mt_id}")
async def delete_pppoe_user(mt_id: str, device_id: str, user=Depends(require_admin)):
    mt, _ = await _get_mt_api(device_id)
    try:
        return await mt.delete_pppoe_secret(mt_id)
    except Exception as e:
        raise HTTPException(503, f"MikroTik: {e}")


@router.get("/pppoe-active")
async def list_pppoe_active(device_id: str, user=Depends(get_current_user)):
    mt, _ = await _get_mt_api(device_id)
    try:
        return await mt.list_pppoe_active()
    except Exception as e:
        raise HTTPException(503, f"MikroTik: {e}")


@router.get("/pppoe-profiles")
async def list_pppoe_profiles(device_id: str, user=Depends(get_current_user)):
    """List PPP profiles from MikroTik (for use in create/edit user forms)."""
    if not device_id:
        return []
    try:
        mt, _ = await _get_mt_api(device_id)
        profiles = await mt.list_pppoe_profiles()
        return [
            {"name": p.get("name", ""), "rate_limit": p.get("rate-limit", p.get("rate_limit", "")), "comment": p.get("comment", "")}
            for p in profiles if p.get("name")
        ]
    except Exception as e:
        raise HTTPException(503, f"MikroTik: {e}")


# ── PPPoE Setup Pool ──────────────────────────────────────────────────────────

class PPPoEPoolSetup(BaseModel):
    pool_name: str = "pppoe-pool"
    pool_ranges: str
    gateway_ip: str
    dns_servers: str
    profile_name: str = "default"

@router.get("/pppoe-settings")
async def get_pppoe_pool_settings(user=Depends(get_current_user)):
    db = get_db()
    settings = await db.system_settings.find_one({"_id": "pppoe_pool_config"}) or {}
    return {
        "pool_name": settings.get("pool_name", "pppoe-pool"),
        "pool_ranges": settings.get("pool_ranges", "10.20.30.2-10.20.30.254"),
        "gateway_ip": settings.get("gateway_ip", "10.20.30.1"),
        "dns_servers": settings.get("dns_servers", "8.8.8.8,1.1.1.1"),
        "profile_name": settings.get("profile_name", "default"),
    }

@router.post("/pppoe-setup-pool")
async def setup_pppoe_pool(data: PPPoEPoolSetup, user=Depends(require_admin)):
    import asyncio
    db = get_db()
    config = data.model_dump()
    
    await db.system_settings.update_one(
        {"_id": "pppoe_pool_config"},
        {"$set": config},
        upsert=True
    )
    
    devices = await db.devices.find({"api_mode": {"$in": ["api", "rest"]}}).to_list(100)
    results = []
    
    for dev in devices:
        try:
            mt = get_api_client(dev)
            pool_name = config["pool_name"]
            
            # --- Handle IP Pool ---
            # Cari pool berdasarkan nama
            pools = await mt._async_req("GET", "ip/pool")
            pool_id = None
            if isinstance(pools, list):
                for p in pools:
                    if p.get("name") == pool_name:
                        pool_id = p.get(".id") or p.get("id")
                        break
            
            pool_data = {"name": pool_name, "ranges": config["pool_ranges"]}
            if pool_id:
                try:
                    await mt._async_req("PATCH", f"ip/pool/{pool_id}", pool_data)
                except Exception:
                    # Fallback untuk ROS6 legacy/kurang support PATCH di _async_req generic
                    # Or just ignore if it fails in ROS6, manual update is needed
                    pass
            else:
                try:
                    await mt._async_req("PUT", "ip/pool", pool_data)
                except Exception:
                    pass
            
            # --- Handle PPP Profile ---
            profiles = await mt._async_req("GET", "ppp/profile")
            profile_id = None
            if isinstance(profiles, list):
                for p in profiles:
                    if p.get("name") == config["profile_name"]:
                        profile_id = p.get(".id") or p.get("id")
                        break
            
            prof_data = {
                "name": config["profile_name"],
                "local-address": config["gateway_ip"],
                "remote-address": pool_name,
                "dns-server": config["dns_servers"]
            }
            if profile_id:
                try:
                    await mt._async_req("PATCH", f"ppp/profile/{profile_id}", prof_data)
                except Exception:
                    pass
            else:
                try:
                    await mt._async_req("PUT", "ppp/profile", prof_data)
                except Exception:
                    pass
                
            results.append({"device": dev.get("name"), "status": "Sukses"})
        except Exception as e:
            results.append({"device": dev.get("name"), "status": f"Gagal: {e}"})
            
    return {"message": "Konfigurasi Pool disimpan & dicoba sinkronisasi ke Router", "results": results}



# ── Monitoring PPPoE ──────────────────────────────────────────────────────────

# In-memory delta store for ROS 6 bps calculation
# { "host:username": {"rx": int, "tx": int, "ts": float} }
_bps_prev = {}

async def _get_pppoe_bps_ros7(mt, pppoe_iface_names: list) -> dict:
    """
    ROS 7 REST: POST interface/monitor-traffic with comma-separated interface names.
    Returns { iface_name_lower: { "rx-bits-per-second": int, "tx-bits-per-second": int } }
    """
    if not pppoe_iface_names:
        return {}
    bps_map = {}
    try:
        iface_str = ",".join(pppoe_iface_names[:100])
        result = await mt.get_interface_traffic(iface_str)
        # get_interface_traffic returns dict or list of dict
        if isinstance(result, list):
            for item in result:
                bps_map[str(item.get("name", "")).lower()] = item
        elif isinstance(result, dict) and result:
            bps_map[str(result.get("name", "")).lower()] = result
    except Exception:
        pass
    return bps_map


async def _get_pppoe_bps_ros6(mt, iface_map: dict, host: str) -> dict:
    """
    ROS 6: calculate bps via byte delta between polls.
    Returns { iface_name_lower: { "rx-bits-per-second": int, "tx-bits-per-second": int } }
    """
    import time
    bps_map = {}
    now = time.monotonic()

    # iface_map already has current rx-byte / tx-byte from list_interfaces()
    for name, idata in iface_map.items():
        prev_key = f"{host}:{name}"
        rx_now = int(idata.get("rx-byte", 0) or 0)
        tx_now = int(idata.get("tx-byte", 0) or 0)

        if prev_key in _bps_prev:
            prev = _bps_prev[prev_key]
            dt = now - prev["ts"]
            if dt > 0:
                rx_bps = max(0, int((rx_now - prev["rx"]) * 8 / dt))
                tx_bps = max(0, int((tx_now - prev["tx"]) * 8 / dt))
                bps_map[name] = {
                    "rx-bits-per-second": rx_bps,
                    "tx-bits-per-second": tx_bps,
                }

        _bps_prev[prev_key] = {"rx": rx_now, "tx": tx_now, "ts": now}

    return bps_map


@router.get("/pppoe-active-monitoring")
async def get_pppoe_active_monitoring(
    router_id: str = None,
    user=Depends(get_current_user)
):
    db = get_db()

    # ── Build device query ────────────────────────────────────────────────────
    if router_id and router_id != "all":
        from bson import ObjectId
        devices = await db.devices.find(
            {"api_mode": {"$in": ["api", "rest"]}, "id": router_id}
        ).to_list(10)
        if not devices:
            try:
                devices = await db.devices.find({"_id": ObjectId(router_id)}).to_list(10)
            except Exception:
                devices = []
    else:
        devices = await db.devices.find(
            {"api_mode": {"$in": ["api", "rest"]}}
        ).to_list(100)

    # ── Customer map: supports both local and RADIUS users ────────────────────
    customers = await db.customers.find(
        {}, {"_id": 0, "username": 1, "password": 1, "name": 1}
    ).to_list(10000)
    cust_map = {
        c.get("username", "").lower(): c
        for c in customers if c.get("username")
    }

    all_actives = []

    for dev in devices:
        host        = dev.get("host", dev.get("ip_address", ""))
        router_name = dev.get("name", host)
        dev_id      = str(dev.get("id", str(dev.get("_id", ""))))
        api_mode    = dev.get("api_mode", "rest")

        try:
            mt = get_api_client(dev)

            # ── Step 1: Active PPPoE sessions ─────────────────────────────────
            # list_pppoe_active() is implemented in BOTH MikroTikRestAPI (ROS7)
            # and MikroTikLegacyAPI (ROS6) — never call _async_req directly here
            actives = await mt.list_pppoe_active()
            if not isinstance(actives, list):
                actives = []
            if not actives:
                continue

            # ── Step 2: Interface list for total byte counters ─────────────────
            # list_interfaces() also works for both ROS 6 and ROS 7
            interfaces = await mt.list_interfaces()
            iface_map = {}
            if isinstance(interfaces, list):
                for iface in interfaces:
                    itype = str(iface.get("type", "")).lower()
                    iname = str(iface.get("name", ""))
                    if itype in ("pppoe-in", "ppp") or iname.startswith("<pppoe-"):
                        iface_map[iname.lower()] = iface

            # ── Step 3: Real-time BPS ─────────────────────────────────────────
            pppoe_iface_names = list(iface_map.keys())
            if api_mode == "rest":
                # ROS 7: POST /interface/monitor-traffic (true real-time bps)
                bps_map = await _get_pppoe_bps_ros7(mt, pppoe_iface_names)
            else:
                # ROS 6: delta from rx-byte/tx-byte between polls
                bps_map = await _get_pppoe_bps_ros6(mt, iface_map, host)

            # ── Step 4: Build result per active session ───────────────────────
            for a in actives:
                uname      = str(a.get("name", ""))
                uname_low  = uname.lower()

                # Dynamic interface: MikroTik names it <pppoe-USERNAME>
                ikey  = f"<pppoe-{uname_low}>"
                idata = iface_map.get(ikey, {})
                bdata = bps_map.get(ikey, {})

                rx_byte = str(idata.get("rx-byte", a.get("rx-byte", "0")))
                tx_byte = str(idata.get("tx-byte", a.get("tx-byte", "0")))
                rx_bps  = str(bdata.get("rx-bits-per-second", "0"))
                tx_bps  = str(bdata.get("tx-bits-per-second", "0"))

                # Customer lookup — fallback to raw username for RADIUS users
                cinfo     = cust_map.get(uname_low, {})
                cust_name = cinfo.get("name") or uname
                password  = cinfo.get("password", "")

                all_actives.append({
                    "name":          uname,
                    "customer_name": cust_name,
                    "password":      password,
                    "is_radius":     not bool(cinfo),
                    "address":       a.get("address", ""),
                    "caller_id":     a.get("caller-id", a.get("caller_id", "")),
                    "uptime":        a.get("uptime", ""),
                    "router_name":   router_name,
                    "router_id":     dev_id,
                    "rx_byte":       rx_byte,
                    "tx_byte":       tx_byte,
                    "rx_bps":        rx_bps,
                    "tx_bps":        tx_bps,
                })

        except Exception as e:
            logger.warning(f"[pppoe-monitoring] Gagal dari {router_name}: {e}")

    return all_actives


@router.get("/pppoe-monitoring-routers")
async def get_monitoring_routers(user=Depends(get_current_user)):
    """Return routers list for the filter dropdown."""
    db = get_db()
    devices = await db.devices.find(
        {"api_mode": {"$in": ["api", "rest"]}},
        {"_id": 0, "id": 1, "name": 1, "host": 1, "api_mode": 1}
    ).to_list(200)
    return [
        {
            "id":       d.get("id", ""),
            "name":     d.get("name", d.get("host", "")),
            "api_mode": d.get("api_mode", "rest"),
        }
        for d in devices
    ]


@router.post("/pppoe-kick")
async def kick_pppoe_user(data: dict, user=Depends(get_current_user)):
    """
    Kick (putus koneksi) active PPPoE session.
    Body: { "username": str, "router_id": str }
    """
    from fastapi import HTTPException
    from bson import ObjectId

    username  = data.get("username", "").strip()
    router_id = data.get("router_id", "").strip()

    if not username or not router_id:
        raise HTTPException(status_code=400, detail="username dan router_id wajib diisi")

    db  = get_db()
    dev = None

    devs = await db.devices.find({"id": router_id}).to_list(1)
    if devs:
        dev = devs[0]
    else:
        try:
            devs = await db.devices.find({"_id": ObjectId(router_id)}).to_list(1)
            if devs:
                dev = devs[0]
        except Exception:
            pass

    if not dev:
        raise HTTPException(status_code=404, detail=f"Router '{router_id}' tidak ditemukan")

    try:
        mt      = get_api_client(dev)
        removed = await mt.remove_pppoe_active_session(username)
        return {
            "success":          True,
            "username":         username,
            "router":           dev.get("name", ""),
            "sessions_removed": removed,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Gagal kick '{username}': {e}")


