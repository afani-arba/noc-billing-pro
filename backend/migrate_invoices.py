import asyncio
from motor.motor_asyncio import AsyncIOMotorClient
import os

async def backfill_invoice_device_id():
    db_url = os.getenv('MONGO_URI', 'mongodb://mongodb:27017/nocbillingpro')
    db_name = os.getenv('MONGO_DB_NAME', 'nocbillingpro')
    client = AsyncIOMotorClient(db_url)
    db = client[db_name]

    invoices = await db.invoices.find({'device_id': {'$exists': False}}).to_list(10000)
    print(f'Mendapatkan {len(invoices)} invoice yang belum memiliki device_id.')

    updated_count = 0
    not_found_count = 0
    
    for inv in invoices:
        customer = await db.customers.find_one({'id': inv.get('customer_id')})
        if customer and customer.get('device_id'):
            await db.invoices.update_one(
                {'_id': inv['_id']},
                {'$set': {'device_id': customer['device_id']}}
            )
            updated_count += 1
        else:
            not_found_count += 1
    
    print(f'Migrasi Selesai: {updated_count} invoice berhasil diperbarui.')
    print(f'Dilewati (customer tidak ditemukan/tanpa router): {not_found_count}')
    
    client.close()

if __name__ == '__main__':
    asyncio.run(backfill_invoice_device_id())
