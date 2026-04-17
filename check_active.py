import asyncio
from mikrotik_api import MikroTikRestAPI

async def main():
    mt = MikroTikRestAPI(host="10.254.254.26", username="admin", password="260495", port=758, use_ssl=True)
    res = await mt.list_pppoe_active()
    print("REST res:", len(res) if isinstance(res, list) else res)
    if isinstance(res, list) and len(res) > 0:
        print("First:", res[0])

asyncio.run(main())
