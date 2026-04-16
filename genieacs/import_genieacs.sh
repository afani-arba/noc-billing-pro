#!/bin/bash
# =============================================================================
# GenieACS Auto-Import Script
# Dijalankan otomatis saat fresh install noc-billing-pro
# Import: provisions, presets, virtual-parameters, config (UI)
# =============================================================================
set -e

GENIEACS_CONTAINER="noc-billing-pro-genieacs-nbi"
NBI_IP=$(docker inspect -f '{{range.NetworkSettings.Networks}}{{.IPAddress}}{{end}}' "$GENIEACS_CONTAINER" 2>/dev/null || echo "localhost")
GENIE_URL="${GENIEACS_NBI_URL:-http://$NBI_IP:7557}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Warna output
GREEN='\033[0;32m'; YELLOW='\033[1;33m'; RED='\033[0;31m'; NC='\033[0m'
ok()   { echo -e "${GREEN}[OK]${NC} $1"; }
warn() { echo -e "${YELLOW}[WARN]${NC} $1"; }
err()  { echo -e "${RED}[ERROR]${NC} $1"; }

echo ""
echo "=============================================="
echo " GenieACS Config Import - noc-billing-pro"
echo "=============================================="
echo " Target: $GENIE_URL"
echo ""

# Tunggu GenieACS NBI siap
echo "Menunggu GenieACS NBI siap..."
for i in $(seq 1 30); do
    if curl -sf "$GENIE_URL" > /dev/null 2>&1; then
        ok "GenieACS NBI online"
        break
    fi
    if [ $i -eq 30 ]; then
        err "GenieACS NBI tidak responsif setelah 60 detik"
        exit 1
    fi
    echo -n "."
    sleep 2
done

# Helper: PUT JSON ke GenieACS NBI
genie_put() {
    local endpoint="$1"
    local id="$2"
    local data="$3"
    local resp
    resp=$(curl -s -o /dev/null -w "%{http_code}" \
        -X PUT "$GENIE_URL/$endpoint/$(python3 -c "import urllib.parse,sys; print(urllib.parse.quote(sys.argv[1]))" "$id")" \
        -H "Content-Type: application/json" \
        -d "$data")
    if [ "$resp" = "200" ] || [ "$resp" = "201" ]; then
        ok "  $endpoint/$id"
        return 0
    else
        warn "  $endpoint/$id (HTTP $resp)"
        return 1
    fi
}

# ── 1. PROVISIONS ──────────────────────────────────────────────────────────────
echo ""
echo "--- Import Provisions ---"
PROVISIONS_FILE="$SCRIPT_DIR/provisions.json"
if [ -f "$PROVISIONS_FILE" ]; then
    python3 << PYEOF
import json, urllib.request, urllib.parse

genie_url = "$GENIE_URL"
with open("$PROVISIONS_FILE") as f:
    provisions = json.load(f)

for p in provisions:
    pid = p["_id"]
    data = {"script": p.get("script", "")}
    url = f"{genie_url}/provisions/{urllib.parse.quote(pid, safe='')}"
    req = urllib.request.Request(url, method="PUT",
          data=json.dumps(data).encode(),
          headers={"Content-Type": "application/json"})
    try:
        resp = urllib.request.urlopen(req)
        print(f"  [OK] provision: {pid}")
    except Exception as e:
        print(f"  [WARN] provision {pid}: {e}")
PYEOF
else
    warn "provisions.json tidak ditemukan di $SCRIPT_DIR"
fi

# ── 2. PRESETS ─────────────────────────────────────────────────────────────────
echo ""
echo "--- Import Presets ---"
PRESETS_FILE="$SCRIPT_DIR/presets.json"
if [ -f "$PRESETS_FILE" ]; then
    python3 << PYEOF
import json, urllib.request, urllib.parse

genie_url = "$GENIE_URL"
with open("$PRESETS_FILE") as f:
    presets = json.load(f)

for p in presets:
    pid = p["_id"]
    # Hapus _id dari body (GenieACS tidak perlu _id di body)
    data = {k: v for k, v in p.items() if k != "_id"}
    url = f"{genie_url}/presets/{urllib.parse.quote(pid, safe='')}"
    req = urllib.request.Request(url, method="PUT",
          data=json.dumps(data).encode(),
          headers={"Content-Type": "application/json"})
    try:
        resp = urllib.request.urlopen(req)
        print(f"  [OK] preset: {pid}")
    except Exception as e:
        print(f"  [WARN] preset {pid}: {e}")
PYEOF
else
    warn "presets.json tidak ditemukan di $SCRIPT_DIR"
fi

# ── 3. VIRTUAL PARAMETERS ──────────────────────────────────────────────────────
echo ""
echo "--- Import Virtual Parameters ---"
VP_FILE="$SCRIPT_DIR/virtual-parameters.json"
if [ -f "$VP_FILE" ]; then
    python3 << PYEOF
import json, urllib.request, urllib.parse

genie_url = "$GENIE_URL"
with open("$VP_FILE") as f:
    vps = json.load(f)

if isinstance(vps, list) and len(vps) > 0:
    for vp in vps:
        vpid = vp["_id"]
        data = {"script": vp.get("script", "")}
        url = f"{genie_url}/virtual-parameters/{urllib.parse.quote(vpid, safe='')}"
        req = urllib.request.Request(url, method="PUT",
              data=json.dumps(data).encode(),
              headers={"Content-Type": "application/json"})
        try:
            resp = urllib.request.urlopen(req)
            print(f"  [OK] virtual-parameter: {vpid}")
        except Exception as e:
            print(f"  [WARN] virtual-parameter {vpid}: {e}")
else:
    print("  [INFO] Tidak ada virtual-parameter untuk di-import")
PYEOF
else
    warn "virtual-parameters.json tidak ditemukan di $SCRIPT_DIR"
fi

# ── 4. CONFIG (UI settings penting saja) ──────────────────────────────────────
echo ""
echo "--- Import UI Config (cwmp + ui.pageSize) ---"
CONFIG_FILE="$SCRIPT_DIR/config.json"
if [ -f "$CONFIG_FILE" ]; then
    python3 << PYEOF
import json, urllib.request, urllib.parse

genie_url = "$GENIE_URL"
with open("$CONFIG_FILE") as f:
    configs = json.load(f)

# Import hanya config penting: cwmp.* dan ui.pageSize
IMPORTANT_KEYS = {
    "cwmp.connectionRequestAllowBasicAuth",
    "cwmp.datetimeMilliseconds",
    "ui.pageSize",
}
imported = 0
for c in configs:
    cid = c["_id"]
    # Hanya import config yang ada di whitelist atau dimulai dengan cwmp./ui.
    if cid not in IMPORTANT_KEYS and not cid.startswith("cwmp.") and not cid.startswith("ui."):
        continue
    val = c.get("value", "")
    url = f"{genie_url}/config/{urllib.parse.quote(cid, safe='')}"
    req = urllib.request.Request(url, method="PUT",
          data=json.dumps({"value": val}).encode(),
          headers={"Content-Type": "application/json"})
    try:
        resp = urllib.request.urlopen(req)
        imported += 1
    except Exception as e:
        pass  # Config UI opsional, skip error

print(f"  [OK] Imported {imported} config entries")
PYEOF
else
    warn "config.json tidak ditemukan di $SCRIPT_DIR"
fi

echo ""
echo "=============================================="
ok "GenieACS config import selesai!"
echo "=============================================="
echo ""
