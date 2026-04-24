import asyncio
from motor.motor_asyncio import AsyncIOMotorClient
import os
from datetime import datetime, timezone, timedelta

async def check():
    uri = os.environ.get("MONGO_URI", "mongodb://mongodb:27017/nocbillingpro")
    client = AsyncIOMotorClient(uri)
    db = client.get_database()
    
    all_devs = await db.devices.find({}, {"_id": 0, "id": 1, "name": 1, "ip_address": 1}).to_list(200)
    known_ids = set()
    for d in all_devs:
        if d.get("id"): known_ids.add(d["id"])
        if d.get("name"): known_ids.add(d["name"])
        ip = (d.get("ip_address") or "").split(":")[0].strip()
        if ip: known_ids.add(ip)
    
    cnt1 = await db.peering_eye_stats.count_documents({"device_id": {"$in": list(known_ids)}})
    cnt2 = await db.peering_eye_stats.count_documents({})
    print(f"Total: {cnt2}, Matching known_ids: {cnt1}")
    
    # Also check the timestamp format
    doc = await db.peering_eye_stats.find_one()
    if doc:
        print(f"Sample timestamp: {doc.get('timestamp')} (type: {type(doc.get('timestamp'))})")

asyncio.run(check())
