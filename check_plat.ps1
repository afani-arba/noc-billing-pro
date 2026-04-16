$plink = "C:\Program Files\PuTTY\plink.exe"
$srv = "10.125.125.238"; $user = "noc"; $pass = "123123"
function SSH([string]$cmd) { echo y | & $plink -ssh "$user@$srv" -pw $pass -batch $cmd 2>&1 }

$py = @"
import sys
import asyncio
sys.path.insert(0, '/app')
from core.db import get_db

async def check():
    db = get_db()
    docs = await db.peering_platforms.find({}, {"_id": 0}).to_list(100)
    for d in docs:
        print(d.get("name"))

asyncio.run(check())
"@

$pyEscaped = $py -replace '"', '\"' -replace '`n', '\n'
SSH "docker run --rm -v /opt/noc-billing-pro:/app python:3.11-slim sh -c 'apt update && apt install -y python3-motor || pip install motor; echo -e `"$pyEscaped`" > /tmp/x.py && python3 /tmp/x.py'"

