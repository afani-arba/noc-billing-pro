import asyncio
import httpx
import json

async def main():
    async with httpx.AsyncClient(base_url="http://localhost:8000", timeout=30.0) as client:
        # Login
        for pwd in ["admin", "123123", "admin123", "password"]:
            r = await client.post("/api/auth/login", json={"username": "admin", "password": pwd})
            if r.status_code == 200:
                print(f"Login OK dengan password: {pwd}")
                token = r.json()["token"]
                break
        else:
            print("Semua password gagal")
            return

        # Test monitoring endpoint langsung
        headers = {"Authorization": f"Bearer {token}"}
        router_id = "9df0a9d8-176a-4427-b54c-27ae66cc05a3"
        
        print(f"\nTesting /api/pppoe-active-monitoring?router_id={router_id}")
        res = await client.get(
            f"/api/pppoe-active-monitoring?router_id={router_id}",
            headers=headers
        )
        print(f"Status: {res.status_code}")
        data = res.json()
        print(f"Jumlah sesi: {len(data) if isinstance(data, list) else 'bukan list'}")
        if isinstance(data, list) and len(data) > 0:
            print(f"Contoh item pertama:")
            print(json.dumps(data[0], indent=2))
        else:
            print(f"Response: {json.dumps(data)[:300]}")

asyncio.run(main())
