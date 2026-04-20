import asyncio
from database import get_db_direct
async def main():
    db = get_db_direct()
    bs = await db.billing_settings.find_one({'device_id': 'GLOBAL'}, {'_id': 0})
    hs = await db.hotspot_settings.find_one({}, {'_id': 0})
    print('BILLING_SETTINGS:', bs)
asyncio.run(main())
