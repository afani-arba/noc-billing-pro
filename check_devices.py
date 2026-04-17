import asyncio
import motor.motor_asyncio

async def main():
    client = motor.motor_asyncio.AsyncIOMotorClient("mongodb://mongodb:27017")
    db = client["nocbillingpro"]
    devs = await db.devices.find({}).to_list(20)
    print(f"Total devices: {len(devs)}")
    for d in devs:
        # Print all fields except _id
        d.pop("_id", None)
        print("---")
        for k, v in d.items():
            print(f"  {k} = {repr(v)}")

asyncio.run(main())
