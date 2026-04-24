#!/bin/bash
echo "=== SYSTEM INFO ==="
uname -a
echo "=== DOCKER PS ==="
docker ps -a
echo "=== DOCKER LOGS BACKEND ==="
docker logs noc-billing-pro-backend --tail 50
