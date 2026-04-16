import sys
import asyncio
import os
os.environ["MONGO_URI"] = "mongodb://noc-billing-pro-mongodb-1:27017" # Since backend uses docker-compose
os.environ["MONGO_DB"] = "noc_billing_pro"
sys.path.insert(0, '/app')

async def test():
    from motor.motor_asyncio import AsyncIOMotorClient
    client = AsyncIOMotorClient("mongodb://noc-billing-pro-mongodb-1:27017")
    db = client.get_database("noc_billing_pro")
    c1 = await db.peering_platforms.count_documents({})
    c2 = await db.peering_eye_platforms.count_documents({})
    print(f"peering_platforms count: {c1}")
    print(f"peering_eye_platforms count: {c2}")

    docs = await db.peering_platforms.find({}).to_list(100)
    for d in docs:
        if d.get("name") not in ["YouTube", "Facebook", "TikTok", "WhatsApp"]:
            print(d.get("name"))

asyncio.run(test())
