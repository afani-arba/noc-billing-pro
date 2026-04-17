import asyncio
from mikrotik_api import MikroTikRouterAPI

async def main():
    mt = MikroTikRouterAPI("10.254.254.26", "admin", "260495", 758, False, True)
    res = await mt.list_pppoe_active()
    print("Legacy res:", len(res) if isinstance(res, list) else res)
    if isinstance(res, list) and len(res) > 0:
        print("First:", res[0])

asyncio.run(main())
