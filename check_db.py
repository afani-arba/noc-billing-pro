import asyncio
from motor.motor_asyncio import AsyncIOMotorClient
async def main():
    db = AsyncIOMotorClient('mongodb://mongodb:27017/nocbillingpro')['nocbillingpro']
    c = await db.customers.find_one({'username': 'FEBRI'})
    if c:
        print('DB User:', c.get('username'), 'current_rate_limit:', c.get('current_rate_limit'), 'package:', c.get('package'))
    else:
        print('No FEBRI')
    pkg = await db.packages.find_one({'name': 'NOC-BW-10M'})
    if not pkg:
        pkg = await db.packages.find_one()
    print('Package:', pkg)
asyncio.run(main())
