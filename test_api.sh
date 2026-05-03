#!/bin/bash
echo "Testing /api/zapret/status (GET)"
curl -s -i -X GET http://localhost:8002/api/zapret/status

echo -e "\n\nTesting /api/zapret/start (POST)"
curl -s -i -X POST http://localhost:8002/api/zapret/start

echo -e "\n\nTesting /api/zapret/start (GET)"
curl -s -i -X GET http://localhost:8002/api/zapret/start
