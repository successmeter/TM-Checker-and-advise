#!/usr/bin/env bash
# Daily backup of the orders database and the generated reports, kept for 14 days.
# Installed by setup.sh as /usr/local/bin/bizimprint-backup and run by cron as the bizimprint user.
set -euo pipefail
DATA=/opt/bizimprint/app/data
OUT=/opt/bizimprint/backups
STAMP=$(date +%Y-%m-%d)
mkdir -p "$OUT"
if [ -f "$DATA/orders.sqlite" ]; then
  # A consistent copy while the app runs (SQLite's online backup).
  python3 -c "import sqlite3, sys; sqlite3.connect(sys.argv[1]).backup(sqlite3.connect(sys.argv[2]))" \
    "$DATA/orders.sqlite" "$OUT/orders-$STAMP.sqlite"
fi
if [ -d "$DATA/reports" ]; then
  tar -czf "$OUT/reports-$STAMP.tar.gz" -C "$DATA" reports
fi
find "$OUT" -type f -mtime +14 -delete
