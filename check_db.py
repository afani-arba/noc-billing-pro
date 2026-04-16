import sys
import asyncio
sys.path.insert(0, '/app')
from core.db import get_db

async def check():
    db = get_db()
    c1 = await db.peering_platforms.count_documents({})
    c2 = await db.peering_eye_platforms.count_documents({})
    print(f"peering_platforms count: {c1}")
    print(f"peering_eye_platforms count: {c2}")

asyncio.run(check())
