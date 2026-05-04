#!/usr/bin/env python3
import asyncio
import sys
sys.path.insert(0, '/app')

from core.db import init_db, get_db

async def main():
    init_db()
    db = get_db()
    items = await db.bgp_steering_policies.find().to_list(100)
    for i in items:
        print(f"Policy: {i.get('name')} | Gateway IP: {i.get('gateway_ip')} | Target ASN: {i.get('target_asn')}")

if __name__ == "__main__":
    asyncio.run(main())
