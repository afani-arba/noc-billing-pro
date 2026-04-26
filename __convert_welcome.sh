#!/bin/bash
docker cp /tmp/lion_net_welcome.svg noc-billing-pro-backend:/tmp/
docker exec -u root noc-billing-pro-backend bash -c "rsvg-convert -h 400 -a /tmp/lion_net_welcome.svg -o /tmp/lion_net_welcome.png"
docker cp noc-billing-pro-backend:/tmp/lion_net_welcome.png /tmp/lion_net_welcome.png
