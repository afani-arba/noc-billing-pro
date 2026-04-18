import asyncio, sys
sys.path.append('backend')
from backend.mikrotik_api import get_api_client

async def main():
    device = {
        'api_mode': 'api',
        'ip_address': '10.254.254.240',
        'api_port': 8728,
        'api_username': 'admin',
        'api_password': '123123',
        'api_ssl': False,
    }
    mt = get_api_client(device)
    clients = await mt.list_radius_clients()
    print('RADIUS CLIENTS:', clients)

asyncio.run(main())
