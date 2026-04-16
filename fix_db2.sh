#!/bin/bash
docker exec noc-billing-pro-backend python3 -c '
from pymongo import MongoClient;
db = MongoClient("mongodb://mongodb:27017/nocbillingpro").nocbillingpro;
result = db.system_settings.update_one({"_id": "genieacs_config"}, {"$set": {"url": "http://genieacs-nbi:7557", "username": "admin"}});
print("DB modified count:", result.modified_count)
'
