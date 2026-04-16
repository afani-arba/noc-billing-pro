import asyncio
import motor.motor_asyncio
async def main():
    client = motor.motor_asyncio.AsyncIOMotorClient('mongodb://mongodb:27017')
    db = client.nocbillingpro
    print("peering_eye_stats:", await db.peering_eye_stats.count_documents({}))
asyncio.run(main())
