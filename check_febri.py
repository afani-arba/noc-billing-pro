import asyncio
from motor.motor_asyncio import AsyncIOMotorClient

async def main():
    db = AsyncIOMotorClient("mongodb://mongodb:27017")["nocbillingpro"]
    c = await db.customers.find_one({"username": "FEBRI"}, {"_id": 0})
    if not c:
        print("FEBRI not found")
        return
        
    pkg = await db.billing_packages.find_one({"id": c.get("package_id")})
    print("CUSTOMERRATE:", c.get("current_rate_limit"), "FUP_ACTIVE:", c.get("fup_active"))
    print("PACKAGE ID:", c.get("package_id"))
    if pkg:
       print("PKG SPEED:", pkg.get("speed_up"), "/", pkg.get("speed_down"))
       print("PKG FUP RATE:", pkg.get("fup_rate_limit"))

asyncio.run(main())
