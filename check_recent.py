import asyncio
from motor.motor_asyncio import AsyncIOMotorClient
import os
from datetime import datetime, timezone, timedelta

async def check():
    uri = os.environ.get("MONGO_URI", "mongodb://mongodb:27017/nocbillingpro")
    client = AsyncIOMotorClient(uri)
    db = client.get_database()
    
    start = (datetime.now(timezone.utc) - timedelta(hours=24)).isoformat()
    docs = await db.peering_eye_stats.find({"timestamp": {"$gte": start}}, {"_id":0, "device_id":1, "timestamp":1}).to_list(10)
    print("Recent records:")
    for d in docs:
        print(d)

    # Let's see what the latest records actually look like regardless of start
    latest = await db.peering_eye_stats.find({}, {"_id":0, "device_id":1, "timestamp":1}).sort("timestamp", -1).to_list(10)
    print("\nLatest records overall:")
    for d in latest:
        print(d)

asyncio.run(check())
