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
    
    print("--- BGP PEERS ---")
    try:
        res = await _mt_get(api, "routing/bgp/peer")
        print(res)
    except Exception as e:
        print("Error getting BGP peers:", e)
        
    print("\n--- BGP ROUTES ---")
    try:
        res2 = await _mt_get(api, "routing/bgp/route")
        routes = [r for r in (res2 or []) if "65000" in str(r.get("bgp-as-path", "")) or r.get("bgp-origin") == "incomplete"]
        print(f"Total BGP routes from AS 65000: {len(routes)}")
        if len(routes) > 0:
            print(routes[0])
            
        print("\nChecking unreachable routes...")
        unreachable = [r for r in (res2 or []) if r.get("invalid") == "true" or r.get("active") == "false"]
        print(f"Total unreachable/invalid: {len(unreachable)}")
        if len(unreachable) > 0:
            print(unreachable[0])
            
    except Exception as e:
        print("Error getting BGP routes:", e)

if __name__ == "__main__":
    asyncio.run(main())
