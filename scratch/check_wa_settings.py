import asyncio
from motor.motor_asyncio import AsyncIOMotorClient
import json

async def check_settings():
    client = AsyncIOMotorClient("mongodb://localhost:27017")
    db = client.noc_billing
    settings = await db.billing_settings.find({}, {"_id": 0}).to_list(100)
    print(json.dumps(settings, indent=2))

if __name__ == "__main__":
    asyncio.run(check_settings())
