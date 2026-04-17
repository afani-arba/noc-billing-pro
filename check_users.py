import asyncio
import motor.motor_asyncio

async def main():
    c = motor.motor_asyncio.AsyncIOMotorClient("mongodb://mongodb:27017")
    db = c["nocbillingpro"]
    users = await db.admin_users.find({}).to_list(5)
    for u in users:
        print(u.get("username"), u.get("is_active"))

asyncio.run(main())
