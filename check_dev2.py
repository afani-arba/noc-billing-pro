import asyncio
from motor.motor_asyncio import AsyncIOMotorClient

async def main():
    db = AsyncIOMotorClient("mongodb://mongodb:27017")["nocbillingpro"]
    devs = await db.devices.find({}).to_list(100)
    for d in devs:
        print(d.get("name"), d.get("ip_address"), d.get("radius_secret"), d.get("hotspot_secret"))
asyncio.run(main())
