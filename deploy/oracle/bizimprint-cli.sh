#!/usr/bin/env bash
# Run a BizImprint command on the server with the app's settings, e.g.
#   bizimprint orders list
#   bizimprint orders link BI-XXXXXXXX
#   bizimprint orders approve BI-XXXXXXXX
#   bizimprint register "BizImprint" --class 42
#   bizimprint refresh
# Installed by setup.sh as /usr/local/bin/bizimprint.
set -euo pipefail
[ $# -ge 1 ] || { sed -n '2,8p' "$0" | sed 's/^# \{0,1\}//'; exit 1; }
module="tm_advisor.$1"; shift
exec sudo -u bizimprint -H bash -c 'set -a; . /etc/bizimprint.env; set +a; cd /opt/bizimprint/app; exec /opt/bizimprint/venv/bin/python -m "$@"' _ "$module" "$@"
