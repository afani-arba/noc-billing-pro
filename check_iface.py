import asyncio
import sys
sys.path.insert(0, "/app")

from core.db import get_db
from mikrotik_api import get_api_client
import motor.motor_asyncio

async def main():
    c = motor.motor_asyncio.AsyncIOMotorClient("mongodb://mongodb:27017")
    db = c["nocbillingpro"]
    device = await db.devices.find_one({"id": "9df0a9d8-176a-4427-b54c-27ae66cc05a3"})
    if not device:
        print("Device not found")
        return
        
    mt = get_api_client(device)
    try:
        ifaces = await mt._async_req("GET", "interface")
        if isinstance(ifaces, list) and len(ifaces) > 0:
            print(f"Got {len(ifaces)} interfaces")
            # Print a sample pppoe interface
            for i in ifaces:
                if "pppoe" in i.get("name", "").lower():
                    print(i)
                    break
        else:
            print("Failed to get a list: ", type(ifaces))
    except Exception as e:
        print(f"Exception: {e}")
        
    # fallback test
    try:
        import asyncio
        ifaces2 = await asyncio.to_thread(mt._list_resource, "/interface")
        print(f"Legacy got {len(ifaces2) if isinstance(ifaces2, list) else 'none'} interfaces")
    except Exception as e:
        print(f"Legacy exception: {e}")

asyncio.run(main())
