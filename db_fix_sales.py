import asyncio
from motor.motor_asyncio import AsyncIOMotorClient

async def run():
    db = AsyncIOMotorClient('mongodb://mongodb:27017')['nocbillingpro']
    
    # Update sales missing device_id by fetching from their vouchers
    sales = await db.hotspot_sales.find({'device_id': {'$exists': False}}).to_list(1000)
    print(f'Found {len(sales)} sales records missing device_id.')
    updated = 0
    
    for s in sales:
        if 'voucher_id' in s:
            v = await db.hotspot_vouchers.find_one({'id': s['voucher_id']})
            if v and 'device_id' in v:
                await db.hotspot_sales.update_one(
                    {'_id': s['_id']},
                    {'$set': {'device_id': v['device_id']}}
                )
                updated += 1
            else:
                await db.hotspot_sales.update_one({'_id': s['_id']}, {'$set': {'device_id': ''}})
        else:
            await db.hotspot_sales.update_one({'_id': s['_id']}, {'$set': {'device_id': ''}})
            
    print(f'Successfully updated {updated} sales records.')

asyncio.run(run())
