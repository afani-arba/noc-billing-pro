from fastapi import APIRouter, Depends, HTTPException, Query
from core.db import get_db
from core.auth import get_current_user, require_write
import logging

router = APIRouter(tags=["pppoe-monitoring"])
logger = logging.getLogger(__name__)

@router.get("/pppoe-monitoring-routers")
async def get_monitoring_routers(user=Depends(get_current_user)):
    db = get_db()
    routers = await db.devices.find({"type": "mikrotik"}, {"id": 1, "name": 1, "api_mode": 1, "_id": 0}).to_list(100)
    return routers

@router.get("/pppoe-active-monitoring")
async def get_pppoe_active(router_id: str = Query(None), user=Depends(get_current_user)):
    db = get_db()
    q = {"type": "mikrotik"}
    if router_id:
        q["id"] = router_id
        
    devices = await db.devices.find(q).to_list(100)
    all_actives = []
    
    for dev in devices:
        try:
            from mikrotik_api import get_api_client
            mt = get_api_client(dev)
            
            # Use ROS API to get active PPPoE connections
            actives = await mt.get_active_pppoe_connections()
            for a in actives:
                a["router_id"] = dev["id"]
                a["router_name"] = dev.get("name", "MikroTik")
            
            all_actives.extend(actives)
        except Exception as e:
            logger.warning(f"[pppoe-monitoring] Failed to query {dev.get('name')}: {e}")
            
    return all_actives

from pydantic import BaseModel
class KickRequest(BaseModel):
    username: str
    router_id: str

@router.post("/pppoe-kick")
async def kick_pppoe_user(req: KickRequest, user=Depends(require_write)):
    db = get_db()
    device = await db.devices.find_one({"id": req.router_id})
    if not device:
        raise HTTPException(404, "Router not found")
        
    try:
        from mikrotik_api import get_api_client
        mt = get_api_client(device)
        await mt.kick_pppoe_user(req.username)
        return {"status": "success", "message": f"Kicked {req.username}"}
    except Exception as e:
        logger.error(f"[pppoe-monitoring] Failed to kick {req.username}: {e}")
        raise HTTPException(500, str(e))

@router.get("/pppoe-users")
async def get_pppoe_users(device_id: str, user=Depends(get_current_user)):
    db = get_db()
    device = await db.devices.find_one({"id": device_id})
    if not device:
        raise HTTPException(404, "Device not found")
        
    try:
        from mikrotik_api import get_api_client
        mt = get_api_client(device)
        return await mt.list_pppoe_secrets()
    except Exception as e:
        logger.error(f"[pppoe-users] Failed: {e}")
        raise HTTPException(500, str(e))

@router.get("/pppoe-settings")
async def get_pppoe_settings(user=Depends(get_current_user)):
    db = get_db()
    settings = await db.settings.find_one({"_id": "pppoe_settings"})
    return settings or {}

class PppoeSettingsUpdate(BaseModel):
    pppoe_pool_name: str
    pppoe_profile_name: str
    pppoe_local_address: str
    dns1: str
    dns2: str

@router.post("/pppoe-setup-pool")
async def setup_pppoe_pool(req: PppoeSettingsUpdate, user=Depends(require_write)):
    db = get_db()
    # Save settings to DB
    await db.settings.update_one(
        {"_id": "pppoe_settings"},
        {"$set": req.model_dump()},
        upsert=True
    )
    return {"status": "success", "message": "Konfigurasi PPPoE berhasil disimpan."}
