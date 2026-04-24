#!/bin/sh
su - root -c "docker exec noc-billing-pro-mongodb mongosh genieacs_billing_pro --quiet --eval 'db.config.updateOne({_id: \"ui.overview.charts.online.slices.1_onlineNow.filter\"}, {\$set: {value: \"Events.Inform > NOW() - 4500 * 1000\"}}); db.config.updateOne({_id: \"ui.overview.charts.online.slices.2_past5m.filter\"}, {\$set: {value: \"Events.Inform < (NOW() - 4500 * 1000) AND Events.Inform > (NOW() - 5 * 60 * 1000) - (24 * 60 * 60 * 1000)\"}});'" <<EOF
123123
EOF
