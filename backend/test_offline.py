import asyncio
from motor.motor_asyncio import AsyncIOMotorClient
import json
from bson.json_util import dumps

MONGO_URI = "mongodb://mongodb:27017" # using internal docker network
# wait, noc-billing-pro-backend uses:
from core.db import get_db

async def main():
    db = get_db()
    cursor = db.devices.find({"api_mode": "rest"})
    devices = await cursor.to_list(length=10)
    for d in devices:
        print(f"Name: {d.get('name')}, IP: {d.get('ip_address')}, Status: {d.get('status')}")
        print(f"Stats: last_poll={d.get('last_poll')}, reachable={d.get('last_traffic', {}).get('reachable')}, fails={d.get('consecutive_poll_failures')}")
        print("========")

if __name__ == "__main__":
    asyncio.run(main())
