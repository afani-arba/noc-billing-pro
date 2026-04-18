import asyncio
from bson import ObjectId
from motor.motor_asyncio import AsyncIOMotorClient

async def run():
    db = AsyncIOMotorClient('mongodb://mongodb:27017')['nocbillingpro']
    
    # Ambil semua sales yang device_id masih kosong atau bermasalah
    sales = await db.hotspot_sales.find({"$or": [{"device_id": ""}, {"device_id": {"$exists": False}}]}).to_list(2000)
    print(f'Found {len(sales)} sales records missing real device_id.')
    
    updated = 0
    for s in sales:
        vid = s.get('voucher_id')
        if not vid: continue
        
        v = None
        if len(vid) == 24:
            # ObjectId string
            v = await db.hotspot_vouchers.find_one({'_id': ObjectId(vid)})
        else:
            # UUID string
            v = await db.hotspot_vouchers.find_one({'id': vid})
            
        if v and 'device_id' in v:
            await db.hotspot_sales.update_one(
                {'_id': s['_id']},
                {'$set': {'device_id': v['device_id']}}
            )
            updated += 1
            print(f"Fixed {s['username']} -> {v['device_id']}")
    
    print(f"Update done. {updated} fixed.")

if __name__ == '__main__':
    asyncio.run(run())
