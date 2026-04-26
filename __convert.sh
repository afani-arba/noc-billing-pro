#!/bin/bash
docker cp /tmp/lion_net_logo.svg noc-billing-pro-backend:/tmp/
docker exec -u root noc-billing-pro-backend bash -c "apt-get update && apt-get install -y librsvg2-bin && rsvg-convert -h 400 -a /tmp/lion_net_logo.svg -o /tmp/lion_net_logo.png"
docker cp noc-billing-pro-backend:/tmp/lion_net_logo.png /tmp/lion_net_logo.png
