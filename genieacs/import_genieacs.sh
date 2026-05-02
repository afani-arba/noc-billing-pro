#!/bin/bash
# =============================================================================
# GenieACS Auto-Import Script
# Dijalankan otomatis saat fresh install noc-billing-pro
# Import: provisions, presets, virtual-parameters, config (UI)
# =============================================================================
set -e

GENIE_URL="${GENIEACS_NBI_URL:-http://genieacs-nbi:7557}"

# Jika dijalankan dari host dan genieacs-nbi tidak bisa diresolve, fallback ke docker inspect
if ! ping -c 1 genieacs-nbi >/dev/null 2>&1; then
    NBI_IP=$(docker inspect -f '{{range.NetworkSettings.Networks}}{{.IPAddress}}{{end}}' noc-billing-pro-genieacs-nbi 2>/dev/null || echo "127.0.0.1")
    GENIE_URL="http://$NBI_IP:7557"
fi
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
echo "Menunggu GenieACS NBI siap ($GENIE_URL)..."
for i in $(seq 1 30); do
    if curl -sf "$GENIE_URL/provisions" > /dev/null 2>&1 || curl -s "$GENIE_URL" > /dev/null 2>&1; then
        ok "GenieACS NBI online"
        break
    fi
    if [ $i -eq 30 ]; then
        warn "GenieACS NBI lambat merespons, tetap melanjutkan..."
        break
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
try:
    with open("$PROVISIONS_FILE") as f:
        provisions = json.load(f)
    for p in provisions:
        pid = p["_id"]
        script_text = p.get("script", "")
        # GenieACS Provisions expecting string body not JSON
        url = f"{genie_url}/provisions/{urllib.parse.quote(pid, safe='')}"
        req = urllib.request.Request(url, method="PUT",
              data=script_text.encode("utf-8"))
        try:
            resp = urllib.request.urlopen(req)
            print(f"  [OK] provision: {pid}")
        except Exception as e:
            print(f"  [WARN] provision {pid}: {e}")
except Exception as e:
    print(f"  [WARN] Failed to parse provisions.json: {e}")
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
try:
    with open("$PRESETS_FILE") as f:
        presets = json.load(f)
    for p in presets:
        pid = p["_id"]
        # Hapus _id dari body (GenieACS tidak perlu _id di body)
        data = {k: v for k, v in p.items() if k != "_id"}
        url = f"{genie_url}/presets/{urllib.parse.quote(pid, safe='')}"
        req = urllib.request.Request(url, method="PUT",
              data=json.dumps(data).encode("utf-8"),
              headers={"Content-Type": "application/json"})
        try:
            resp = urllib.request.urlopen(req)
            print(f"  [OK] preset: {pid}")
        except Exception as e:
            print(f"  [WARN] preset {pid}: {e}")
except Exception as e:
    print(f"  [WARN] Failed to parse presets.json: {e}")
PYEOF
else
    warn "presets.json tidak ditemukan di $SCRIPT_DIR"
fi

# ── 3. VIRTUAL PARAMETERS ──────────────────────────────────────────────────────
echo ""
echo "--- Import Virtual Parameters ---"
VP_FILE="$SCRIPT_DIR/virtual-parameters.json"
if [ -f "$VP_FILE" ] && grep -q "{" "$VP_FILE"; then
    python3 << PYEOF
import json, urllib.request, urllib.parse

genie_url = "$GENIE_URL"
try:
    with open("$VP_FILE") as f:
        vps = json.load(f)

    if isinstance(vps, list) and len(vps) > 0:
        for vp in vps:
            vpid = vp["_id"]
            script_text = vp.get("script", "")
            url = f"{genie_url}/virtual_parameters/{urllib.parse.quote(vpid, safe='')}"
            req = urllib.request.Request(url, method="PUT",
                  data=script_text.encode("utf-8"))
            try:
                resp = urllib.request.urlopen(req)
                print(f"  [OK] virtual-parameter: {vpid}")
            except Exception as e:
                print(f"  [WARN] virtual-parameter {vpid}: {e}")
    else:
        print("  [INFO] Tidak ada virtual-parameter untuk di-import")
except Exception as e:
    print(f"  [INFO] Skip virtual-parameters (Invalid JSON or 404): {e}")
PYEOF
else
    warn "Skip virtual-parameters (no valid JSON found)"
fi

# ── 4. CONFIG (UI settings & cwmp) ──────────────────────────────────────────────
echo ""
echo "--- Import UI Config (cwmp + ui.*) ---"
CONFIG_FILE="$SCRIPT_DIR/config.json"
if [ -f "$CONFIG_FILE" ]; then
    if docker ps --format '{{.Names}}' | grep -q 'noc-billing-pro-mongodb'; then
        echo "  Menghapus config default bawaan dan menggunakan mongoimport untuk config.json..."
        # Hapus default layout "online" dari GenieACS agar tidak berbenturan dengan layout custom
        docker exec -i noc-billing-pro-mongodb mongosh genieacs_billing_pro --quiet --eval 'db.config.deleteMany({_id: /ui.overview.groups.online/})' >/dev/null 2>&1
        
        docker exec -i noc-billing-pro-mongodb mongoimport --db genieacs_billing_pro --collection config --jsonArray --mode upsert < "$CONFIG_FILE" >/dev/null 2>&1
        
        # Restart layanan UI untuk apply config
        docker restart noc-billing-pro-genieacs-ui >/dev/null 2>&1
        ok "Imported config.json via MongoDB backend & UI restarted"
    else
        warn "Container noc-billing-pro-mongodb tidak berjalan, gagal import config"
    fi
else
    warn "config.json tidak ditemukan di $SCRIPT_DIR"
fi

echo ""
echo "=============================================="
ok "GenieACS config import selesai!"
echo "=============================================="
echo ""
