#!/usr/bin/env bash
# Deploy the latest code: pull, install any new packages, restart. Run on the server:  bash /opt/bizimprint/app/deploy/oracle/update.sh
set -euo pipefail
APP=/opt/bizimprint/app
BRANCH=$(sudo -u bizimprint -H git -C "$APP" rev-parse --abbrev-ref HEAD)
sudo -u bizimprint -H git -C "$APP" pull --ff-only origin "$BRANCH"
sudo -u bizimprint -H /opt/bizimprint/venv/bin/pip install --quiet -e "$APP"
sudo cp "$APP/deploy/oracle/bizimprint.service" /etc/systemd/system/bizimprint.service
sudo systemctl daemon-reload
sudo systemctl restart bizimprint
sleep 3
sudo systemctl --no-pager --lines=5 status bizimprint
