import asyncio
from motor.motor_asyncio import AsyncIOMotorClient
import os
from datetime import datetime, timezone, timedelta

async def check():
    uri = os.environ.get("MONGO_URI", "mongodb://mongodb:27017/nocbillingpro")
    client = AsyncIOMotorClient(uri)
    db = client.get_database()
    
    # Simulate range_to_start
    hours = 24
    start = (datetime.now(timezone.utc) - timedelta(hours=hours)).isoformat()
    
    # Simulate known_ids
    all_devs = await db.devices.find({}, {"_id": 0, "id": 1, "name": 1, "ip_address": 1}).to_list(200)
    known_ids = set()
    for d in all_devs:
        if d.get("id"): known_ids.add(d["id"])
        if d.get("name"): known_ids.add(d["name"])
        ip = (d.get("ip_address") or "").split(":")[0].strip()
        if ip: known_ids.add(ip)
    
    print(f"known_ids count: {len(known_ids)}")
    print(f"start time: {start}")
    
    match = {"timestamp": {"$gte": start}}
    match["device_id"] = {"$in": list(known_ids)}
    
    count = await db.peering_eye_stats.count_documents(match)
    print(f"matching stats count: {count}")

    pipeline = [
        {"$match": match},
        {"$group": {
            "_id": "$platform",
            "hits":  {"$sum": "$hits"},
        }},
    ]
    docs = await db.peering_eye_stats.aggregate(pipeline).to_list(10)
    print(f"Agg docs: {docs}")

asyncio.run(check())
