import asyncio
from motor.motor_asyncio import AsyncIOMotorClient

async def main():
    db = AsyncIOMotorClient("mongodb://mongodb:27017")["nocbillingpro"]
    dev = await db.devices.find_one({"name": "ARSYAPRO"})
    if dev:
        print("ARSYAPRO:", dev.get("radius_secret"), dev.get("hotspot_secret"))
    else:
        print("Device not found")
asyncio.run(main())
