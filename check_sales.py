import asyncio
from motor.motor_asyncio import AsyncIOMotorClient

async def run():
    db = AsyncIOMotorClient('mongodb://mongodb:27017')['nocbillingpro']
    
    # Let's get the 2 most recent sales records
    sales = await db.hotspot_sales.find().sort("created_at", -1).to_list(5)
    print("=== RECENT 5 SALES ===")
    for s in sales:
        print(s)
        
    print("=== VOUCHER VCH4H8 ===")
    v = await db.hotspot_vouchers.find_one({'username': 'VCH4H8'})
    print(v)
    
    print("=== SALE FOR VCH4H8 ===")
    s2 = await db.hotspot_sales.find_one({'username': 'VCH4H8'})
    print(s2)

asyncio.run(run())
