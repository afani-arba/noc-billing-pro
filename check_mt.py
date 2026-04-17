import asyncio
import sys
sys.path.insert(0, "/app")

from core.db import get_db
from mikrotik_api import get_api_client
import motor.motor_asyncio
import logging

logging.basicConfig(level=logging.DEBUG)

async def main():
    # Setup motor
    c = motor.motor_asyncio.AsyncIOMotorClient("mongodb://mongodb:27017")
    db = c["nocbillingpro"]
    
    device = await db.devices.find_one({"id": "9df0a9d8-176a-4427-b54c-27ae66cc05a3"})
    if not device:
        print("Device not found")
        return
        
    print(f"Device: {device.get('name')}")
    print(f"Mode: {device.get('api_mode')}, Port: {device.get('api_port')}, HTTPS: {device.get('use_https')}")
    
    mt = get_api_client(device)
    print(f"Client: {type(mt).__name__}")
    
    try:
        res = await asyncio.wait_for(mt.list_pppoe_active(), timeout=10.0)
        print(f"Result count: {len(res) if isinstance(res, list) else 0}")
    except Exception as e:
        print(f"Exception: {e}")

asyncio.run(main())
