docker exec noc-billing-pro-backend sh -c "cp /app-host/backend/routers/peering_eye.py /app/routers/peering_eye.py && cp /app-host/backend/services/bgp_steering_injector.py /app/services/bgp_steering_injector.py"
docker restart noc-billing-pro-backend
