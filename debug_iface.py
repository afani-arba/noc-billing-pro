import asyncio
import pprint
from mikrotik_api import get_api_client
from core.db import get_db, init_db

async def m():
    await init_db()
    db = get_db()
    dev = await db.devices.find_one({"name": "DEMO"})  # The router name from the screenshot is DEMO!
    mt = get_api_client(dev)
    
    print("Testing list_pppoe_active:")
    res = await mt.list_pppoe_active()
    pprint.pprint(res[:2] if res else [])
    
    print("Testing GET interface:")
    i = await mt._async_req("GET", "interface")
    pprint.pprint([x for x in i if "pppoe" in x.get("type", "")] [:2])

asyncio.run(m())
