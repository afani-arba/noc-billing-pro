import asyncio
import argparse
import sys
from getpass import getpass
import uuid
from datetime import datetime, timezone

from core.db import get_db, init_db
from core.auth import pwd_context

async def manage_user():
    init_db()
    db = get_db()
    
    parser = argparse.ArgumentParser(description="User Management untuk NOC Billing Pro")
    parser.add_argument("--create", action="store_true", help="Buat user baru")
    parser.add_argument("--reset", action="store_true", help="Reset password user")
    
    args = parser.parse_args()
    
    if args.create:
        print("=== CREATE NEW ADMIN USER ===")
        user = input("Username: ")
        
        existing = await db.admin_users.find_one({"username": user})
        if existing:
            print(f"Error: Username '{user}' sudah ada di database. Gunakan --reset jika ingin mengubah password.")
            sys.exit(1)
            
        name = input("Nama Lengkap: ")
        password = getpass("Password: ")
        
        user_doc = {
            "id": str(uuid.uuid4()),
            "username": user,
            "password": pwd_context.hash(password),
            "name": name,
            "role": "administrator",
            "is_active": True,
            "created_at": datetime.now(timezone.utc).isoformat()
        }
        await db.admin_users.insert_one(user_doc)
        print(f"SUKSES: User '{user}' berhasil ditambahkan!")
        
    elif args.reset:
        print("=== RESET USER PASSWORD ===")
        user = input("Username yang ingin direset: ")
        
        existing = await db.admin_users.find_one({"username": user})
        if not existing:
            print(f"Error: Username '{user}' tidak ditemukan di database.")
            sys.exit(1)
            
        password = getpass("Password Baru: ")
        await db.admin_users.update_one(
            {"_id": existing["_id"]},
            {"$set": {"password": pwd_context.hash(password)}}
        )
        print(f"SUKSES: Password untuk user '{user}' berhasil direset!")
    else:
        parser.print_help()

if __name__ == "__main__":
    asyncio.run(manage_user())
