#!/bin/bash
# Script untuk trigger inject cycle pada GoBGP BGP Steering
echo 123123 | su -c 'docker exec -w /app noc-billing-pro-backend python3 force_sync4.py' root
