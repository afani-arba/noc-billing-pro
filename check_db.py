import asyncio
import motor.motor_asyncio
async def main():
    client = motor.motor_asyncio.AsyncIOMotorClient('mongodb://mongodb:27017')
    db = client.nocbillingpro
    print("syslog_entries:", await db.syslog_entries.count_documents({}))
asyncio.run(main())
