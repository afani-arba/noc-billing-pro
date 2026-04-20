import asyncio
from motor.motor_asyncio import AsyncIOMotorClient

async def main():
    db = AsyncIOMotorClient("mongodb://mongodb:27017")["nocbillingpro"]
    hs = await db.hotspot_settings.find_one({}, {"_id": 0})
    if not hs:
        print("NO SETTINGS")
        return
    print("GLOBALRADIUSSECRET:", hs.get("radius_secret"), hs.get("secret"))
asyncio.run(main())
