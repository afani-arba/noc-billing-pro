import re

with open(r'e:\noc-billing-pro\backend\routers\hotspot.py', 'rb') as f:
    content = f.read().decode('utf-8', errors='replace')

NEW_BLOCK = '''    now_utc = datetime.now(timezone.utc)
    result = []
    for v in vouchers:
        v["router_name"] = devices_map.get(v.get("device_id", ""), v.get("device_id", ""))

        limit_uptime  = int(v.get("limit_uptime_secs", 0))
        used_uptime   = int(v.get("used_uptime_secs", 0))
        validity_secs = int(v.get("validity_secs", 0))

        # Sisa Uptime (hitung mundur, BERHENTI saat offline)
        if limit_uptime > 0:
            current_sess_elapsed = 0
            last_sess_start = v.get("last_session_start")
            if last_sess_start and v.get("status") == "active":
                try:
                    start_dt = datetime.fromisoformat(last_sess_start.replace("Z", "+00:00"))
                    current_sess_elapsed = max(0, int((now_utc - start_dt).total_seconds()))
                except Exception:
                    pass
            total_used_uptime = used_uptime + current_sess_elapsed
            v["rem_uptime_secs"]         = max(0, limit_uptime - total_used_uptime)
            v["total_used_uptime_secs"]  = total_used_uptime
            v["current_sess_elapsed"]    = current_sess_elapsed
        else:
            v["rem_uptime_secs"]         = 0
            v["total_used_uptime_secs"]  = used_uptime
            v["current_sess_elapsed"]    = 0

        # Sisa Validitas (berjalan TERUS sejak first_login, tidak berhenti)
        first_login = v.get("first_login_time")
        if validity_secs > 0 and first_login:
            try:
                first_dt = datetime.fromisoformat(first_login.replace("Z", "+00:00"))
                elapsed_since_first = max(0, int((now_utc - first_dt).total_seconds()))
                v["rem_validity_secs"] = max(0, validity_secs - elapsed_since_first)
            except Exception:
                v["rem_validity_secs"] = validity_secs
        elif validity_secs > 0:
            v["rem_validity_secs"] = validity_secs
        else:
            v["rem_validity_secs"] = 0

        result.append(v)

    return result
'''

# Find the start marker
start_marker = '    now_utc = datetime.now(timezone.utc)\n    result = []\n    for v in vouchers:'
end_marker = '    return result\n\n\n@router.put("/hotspot-vouchers/{voucher_id}"'

start_idx = content.find(start_marker)
end_idx   = content.find(end_marker)

if start_idx == -1 or end_idx == -1:
    print(f"ERROR: start_idx={start_idx}, end_idx={end_idx}")
    print("Looking for alternate pattern...")
    # Try to find any occurrence
    for i, line in enumerate(content.splitlines()):
        if 'session_start_time' in line or 'rem_validity_secs' in line or 'now_utc' in line:
            print(f"  L{i+1}: {line[:80]}")
else:
    before = content[:start_idx]
    after  = content[end_idx:]
    new_content = before + NEW_BLOCK + '\n\n' + '@router.put("/hotspot-vouchers/{voucher_id}"' + after[len(end_marker):]
    with open(r'e:\noc-billing-pro\backend\routers\hotspot.py', 'wb') as f:
        f.write(new_content.encode('utf-8'))
    print("SUCCESS: File patched!")
    print(f"Replaced {end_idx - start_idx} chars with {len(NEW_BLOCK)} chars")
