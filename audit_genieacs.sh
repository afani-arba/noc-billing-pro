#!/bin/bash
# Audit GenieACS config dari NBI API (port 7557)
GENIE_URL="http://localhost:7557"

echo "=========================================="
echo " GenieACS Config Audit - $(date)"
echo "=========================================="

echo ""
echo "=== 1. PROVISIONS ==="
curl -s "$GENIE_URL/provisions" | python3 -m json.tool 2>/dev/null || curl -s "$GENIE_URL/provisions"

echo ""
echo "=== 2. PRESETS ==="
curl -s "$GENIE_URL/presets" | python3 -m json.tool 2>/dev/null || curl -s "$GENIE_URL/presets"

echo ""
echo "=== 3. VIRTUAL PARAMETERS ==="
curl -s "$GENIE_URL/virtual-parameters" | python3 -m json.tool 2>/dev/null || curl -s "$GENIE_URL/virtual-parameters"

echo ""
echo "=== 4. FILES (firmware, configs) ==="
curl -s "$GENIE_URL/files" | python3 -m json.tool 2>/dev/null || curl -s "$GENIE_URL/files"

echo ""
echo "=== 5. USERS (GenieACS auth) ==="
curl -s "$GENIE_URL/users" | python3 -m json.tool 2>/dev/null || curl -s "$GENIE_URL/users"

echo ""
echo "=== 6. CONFIG (sistem) ==="
curl -s "$GENIE_URL/config" | python3 -m json.tool 2>/dev/null || curl -s "$GENIE_URL/config"

echo ""
echo "=== 7. Extension scripts ==="
ls -la /opt/genieacs/ext/ 2>/dev/null || \
  docker exec genieacs ls -la /opt/genieacs/ext/ 2>/dev/null || \
  echo "ext dir not found"

echo ""
echo "=== 8. GenieACS config files ==="
find /opt/genieacs/config -type f 2>/dev/null | while read f; do
  echo "--- $f ---"
  cat "$f"
done

# Try inside docker
docker exec genieacs sh -c 'find /opt/genieacs/config -type f 2>/dev/null | xargs -I{} sh -c "echo \"--- {} ---\"; cat {}"' 2>/dev/null

echo ""
echo "=== 9. docker-compose GenieACS env ==="
cat /opt/noc-sentinel/docker-compose.yml 2>/dev/null | grep -A5 -B2 "genieacs" || \
cat ~/docker-compose.yml 2>/dev/null | grep -A5 -B2 "genieacs" || \
find / -name "docker-compose.yml" -not -path "*/proc/*" 2>/dev/null | head -5 | xargs grep -l "genieacs" 2>/dev/null

echo ""
echo "=== DONE ==="
