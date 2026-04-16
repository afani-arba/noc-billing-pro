#!/bin/bash
# Export semua GenieACS config ke file JSON
GENIE_URL="http://localhost:7557"
OUT_DIR="/tmp/genieacs_export"
mkdir -p "$OUT_DIR"

echo "=== Exporting GenieACS config to $OUT_DIR ==="

echo "1. Provisions..."
curl -s "$GENIE_URL/provisions" > "$OUT_DIR/provisions.json"
PROV_COUNT=$(python3 -c "import json,sys; d=json.load(open('$OUT_DIR/provisions.json')); print(len(d))" 2>/dev/null || echo "?")
echo "   Found: $PROV_COUNT provisions"

echo "2. Presets..."
curl -s "$GENIE_URL/presets" > "$OUT_DIR/presets.json"
PRE_COUNT=$(python3 -c "import json,sys; d=json.load(open('$OUT_DIR/presets.json')); print(len(d))" 2>/dev/null || echo "?")
echo "   Found: $PRE_COUNT presets"

echo "3. Virtual Parameters..."
curl -s "$GENIE_URL/virtual-parameters" > "$OUT_DIR/virtual-parameters.json"
VP_COUNT=$(python3 -c "import json,sys; d=json.load(open('$OUT_DIR/virtual-parameters.json')); print(len(d))" 2>/dev/null || echo "?")
echo "   Found: $VP_COUNT virtual-parameters"

echo "4. Config..."
curl -s "$GENIE_URL/config" > "$OUT_DIR/config.json"
CFG_COUNT=$(python3 -c "import json,sys; d=json.load(open('$OUT_DIR/config.json')); print(len(d))" 2>/dev/null || echo "?")
echo "   Found: $CFG_COUNT config entries"

echo "5. Users..."
curl -s "$GENIE_URL/users" > "$OUT_DIR/users.json"

echo "6. Files metadata..."
curl -s "$GENIE_URL/files" > "$OUT_DIR/files_meta.json"

# Extension scripts
echo "7. Extension scripts..."
EXT_DIR_DOCKER=$(docker exec noc-genieacs-cwmp sh -c 'ls /opt/genieacs/ext/ 2>/dev/null' 2>/dev/null)
if [ -n "$EXT_DIR_DOCKER" ]; then
    mkdir -p "$OUT_DIR/ext"
    for f in $EXT_DIR_DOCKER; do
        docker exec noc-genieacs-cwmp cat "/opt/genieacs/ext/$f" > "$OUT_DIR/ext/$f" 2>/dev/null
        echo "   Exported ext: $f"
    done
else
    echo "   No ext scripts found"
fi

# Create summary
echo ""
echo "=== Export Summary ==="
ls -lah "$OUT_DIR/"
echo ""
echo "Tarball..."
tar -czf /tmp/genieacs_config.tar.gz -C /tmp genieacs_export/
ls -lah /tmp/genieacs_config.tar.gz
echo "EXPORT COMPLETE"
