import sys
import asyncio
import os
sys.path.insert(0, '/app')
os.environ["MONGO_URI"] = "mongodb://mongodb:27017" # Since backend uses docker-compose
os.environ["MONGO_DB"] = "noc_billing_pro"
from core.db import get_db
from routers.peering_eye import get_steering_catalog

async def test():
    class DummyUser: pass
    try:
        catalog = await get_steering_catalog(DummyUser())
        print(f"Catalog length: {len(catalog)}")
        for x in catalog:
            print(x["name"])
    except Exception as e:
        print(f"FAILED: {e}")

asyncio.run(test())
