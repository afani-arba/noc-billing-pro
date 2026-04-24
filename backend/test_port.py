import asyncio
import logging
logging.basicConfig(level=logging.DEBUG)

# Mock dictionary as it would come from MongoDB
device = {"api_mode": "api", "ip_address": "172.16.1.1", "api_port": "9654", "api_username": "admin", "api_password": ""}

from mikrotik_api import get_api_client

async def main():
    mt = get_api_client(device)
    print("Type of port:", type(mt.port))
    try:
        # We don't actually need to connect, just checking if routeros_api throws an error on port type during initialization
        pass
    except Exception as e:
        print("Error:", e)

asyncio.run(main())
