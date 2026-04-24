import urllib.request, urllib.parse, json

nbi = "http://172.18.0.4:7557"
v1 = "Events.Inform > NOW() - 4500 * 1000"
v2 = "Events.Inform < (NOW() - 4500 * 1000) AND Events.Inform > (NOW() - 5 * 60 * 1000) - (24 * 60 * 60 * 1000)"

def put_config(key, val):
    url = f"{nbi}/config/{urllib.parse.quote(key)}"
    req = urllib.request.Request(
        url,
        data=json.dumps({"value": val}).encode(),
        headers={"Content-Type": "application/json"},
        method="PUT"
    )
    res = urllib.request.urlopen(req)
    print(f"Updated {key}: {res.status}")

put_config("ui.overview.charts.online.slices.1_onlineNow.filter", v1)
put_config("ui.overview.charts.online.slices.2_past5m.filter", v2)
