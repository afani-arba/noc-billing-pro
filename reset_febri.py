import asyncio
from motor.motor_asyncio import AsyncIOMotorClient

async def main():
    db = AsyncIOMotorClient("mongodb://mongodb:27017")["nocbillingpro"]
    
    uname = "FEBRI"
    
    # 1. Bersihkan semua history session-nya di radius_sessions
    res1 = await db.radius_sessions.delete_many({"username": uname})
    print(f"Blogger: Menghapus {res1.deleted_count} rekaman sesi lama {uname}.")
    
    # 2. Reset status FUP, Booster, Night Mode dan log bandwidth di profil Customers
    res2 = await db.customers.update_one(
        {"username": uname},
        {
            "$set": {
                "fup_active": False,
                "fup_bytes_used": 0,
                "fup_last_total": 0,
                "night_mode_active": False,
                "boost_active": False,
            },
            "$unset": {
                "boost_rate_limit": "",
                "boost_expires_at": "",
                "current_rate_limit": ""  # Biarkan kosong agar kembali ke base speed otomatis
            }
        }
    )
    if res2.modified_count > 0:
        print(f"Blogger: Berhasil menormalkan kembali profil pelanggan {uname} seperti sedia kala (Reset FUP/Booster/State).")
    else:
        print(f"Blogger: Profil {uname} sudah bersih atau tidak ditemukan.")

asyncio.run(main())
