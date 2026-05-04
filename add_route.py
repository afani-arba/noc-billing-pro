#!/usr/bin/env python3
import asyncio
import sys
sys.path.insert(0, '/app')

from mikrotik_api import get_api_client
from core.db import init_db, get_db
from routers.network_tuning import _mt_get

async def main():
    init_db()
    db = get_db()
    dev = await db.devices.find_one({"ip_address": {"$regex": "^10.125.125.1"}})
    if not dev:
        print("Device 10.125.125.1 not found")
        return
    
    api = get_api_client(dev)
    
    print("--- Adding static route for 10.254.254.240 ---")
    try:
        # Check if route exists
        routes = await _mt_get(api, "ip/route")
        exists = any("10.254.254.240" in r.get("dst-address", "") for r in (routes or []))
        if exists:
            print("Route already exists!")
        else:
            res = api._add_resource("ip/route", {
                "dst-address": "10.254.254.240/32",
                "gateway": "10.125.125.235"
            })
            print("Added route:", res)
    except Exception as e:
        print("Error:", e)

if __name__ == "__main__":
    asyncio.run(main())
