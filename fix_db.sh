#!/bin/bash
echo "=== FIX DOCKER COMPOSE ==="
cp /tmp/docker-compose.yml /opt/noc-billing-pro/docker-compose.yml
cd /opt/noc-billing-pro
docker compose up -d genieacs-ui

echo "=== FIX MONGO DB GENIEACS URL ==="
docker exec noc-billing-pro-backend python3 -c '
from pymongo import MongoClient;
import urllib.parse;
db = MongoClient("mongodb://mongodb:27017/noc_billing_pro").noc_billing_pro;
result = db.system_settings.update_one({"_id": "genieacs_config"}, {"$set": {"url": "http://genieacs-nbi:7557"}});
print("DB modified count:", result.modified_count)
'
