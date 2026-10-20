#!/usr/bin/env bash
# Set up BizImprint on a fresh Oracle Cloud Ubuntu server (Ampere A1 / Arm, or x86). Run once, as the ubuntu user:
#
#   bash setup.sh <domain> <git repo SSH URL> [branch]
#   bash setup.sh bizimprint.com.au git@github.com:successmeter/TM-Checker-and-advise.git main
#
# No domain yet? Use the server's IP with sslip.io, e.g. 203-0-113-5.sslip.io (it resolves to 203.0.113.5).
# Safe to run again: each step checks what is already done. Guide: docs/deploy-oracle.md
set -euo pipefail

DOMAIN="${1:?Usage: bash setup.sh <domain> <repo ssh url> [branch]}"
REPO="${2:?Usage: bash setup.sh <domain> <repo ssh url> [branch]}"
BRANCH="${3:-main}"
HOME_DIR=/opt/bizimprint
APP="$HOME_DIR/app"
VENV="$HOME_DIR/venv"
ENV_FILE=/etc/bizimprint.env
as_app() { sudo -u bizimprint -H "$@"; }

echo "==> System packages"
sudo apt-get update -y
sudo DEBIAN_FRONTEND=noninteractive apt-get upgrade -y
sudo DEBIAN_FRONTEND=noninteractive apt-get install -y git python3 python3-venv python3-pip sqlite3 curl gnupg \
  debian-keyring debian-archive-keyring apt-transport-https iptables-persistent

echo "==> Caddy (web server with automatic HTTPS)"
if ! command -v caddy >/dev/null; then
  curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/gpg.key' | sudo gpg --batch --yes --dearmor -o /usr/share/keyrings/caddy-stable-archive-keyring.gpg
  curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/debian.deb.txt' | sudo tee /etc/apt/sources.list.d/caddy-stable.list >/dev/null
  sudo apt-get update -y
  sudo apt-get install -y caddy
fi

echo "==> Firewall: open ports 80 and 443 (Oracle's Ubuntu image blocks them by default)"
for port in 80 443; do
  if ! sudo iptables -C INPUT -p tcp --dport "$port" -m conntrack --ctstate NEW -j ACCEPT 2>/dev/null; then
    sudo iptables -I INPUT 1 -p tcp --dport "$port" -m conntrack --ctstate NEW -j ACCEPT
  fi
done
sudo netfilter-persistent save

echo "==> App user and folders"
id bizimprint >/dev/null 2>&1 || sudo useradd --system --home-dir "$HOME_DIR" --create-home --shell /usr/sbin/nologin bizimprint
sudo mkdir -p "$HOME_DIR/backups" "$HOME_DIR/browsers"
sudo chown -R bizimprint:bizimprint "$HOME_DIR"

echo "==> GitHub access (a read-only deploy key)"
KEY="$HOME_DIR/.ssh/id_ed25519"
if ! sudo test -f "$KEY"; then
  as_app mkdir -p "$HOME_DIR/.ssh"
  as_app ssh-keygen -t ed25519 -N "" -C "bizimprint-server" -f "$KEY" >/dev/null
fi
as_app bash -c "ssh-keyscan -t ed25519 github.com >> '$HOME_DIR/.ssh/known_hosts' 2>/dev/null; sort -u -o '$HOME_DIR/.ssh/known_hosts' '$HOME_DIR/.ssh/known_hosts'"
if ! as_app git ls-remote "$REPO" >/dev/null 2>&1; then
  echo
  echo "Add this key in GitHub: repository > Settings > Deploy keys > Add deploy key (leave 'Allow write access' off):"
  echo
  sudo cat "$KEY.pub"
  echo
  read -r -p "Press Enter once you've added it... "
  as_app git ls-remote "$REPO" >/dev/null || { echo "GitHub still refuses the key. Check it was added to this repository."; exit 1; }
fi

echo "==> Code ($BRANCH)"
if sudo test -d "$APP/.git"; then
  as_app git -C "$APP" fetch origin "$BRANCH"
  as_app git -C "$APP" checkout "$BRANCH"
  as_app git -C "$APP" pull --ff-only origin "$BRANCH"
else
  as_app git clone --branch "$BRANCH" "$REPO" "$APP"
fi

echo "==> Python packages"
[ -x "$VENV/bin/python" ] || as_app python3 -m venv "$VENV"
as_app "$VENV/bin/pip" install --quiet --upgrade pip
as_app "$VENV/bin/pip" install --quiet -e "$APP"

echo "==> Chromium for PDF reports"
sudo "$VENV/bin/python" -m playwright install-deps chromium
as_app env PLAYWRIGHT_BROWSERS_PATH="$HOME_DIR/browsers" "$VENV/bin/python" -m playwright install chromium

echo "==> Settings ($ENV_FILE)"
if ! sudo test -f "$ENV_FILE"; then
  sudo cp "$APP/deploy/oracle/bizimprint.env.example" "$ENV_FILE"
  SECRET=$(openssl rand -hex 32)
  sudo sed -i "s|^TM_PUBLIC_URL=.*|TM_PUBLIC_URL=https://$DOMAIN|; s|^TM_SECRET=.*|TM_SECRET=$SECRET|" "$ENV_FILE"
fi
sudo chown root:bizimprint "$ENV_FILE"
sudo chmod 640 "$ENV_FILE"

echo "==> Service"
sudo cp "$APP/deploy/oracle/bizimprint.service" /etc/systemd/system/bizimprint.service
sudo systemctl daemon-reload
sudo systemctl enable bizimprint >/dev/null
sudo systemctl restart bizimprint

echo "==> HTTPS for $DOMAIN"
sudo tee /etc/caddy/Caddyfile >/dev/null <<CADDY
$DOMAIN {
	encode gzip
	reverse_proxy 127.0.0.1:8000
}
CADDY
sudo systemctl reload caddy || sudo systemctl restart caddy

echo "==> The 'bizimprint' command (orders, register checks, data refresh)"
sudo install -m 755 "$APP/deploy/oracle/bizimprint-cli.sh" /usr/local/bin/bizimprint

echo "==> Daily backups (orders database and reports, kept 14 days)"
sudo install -m 755 "$APP/deploy/oracle/backup.sh" /usr/local/bin/bizimprint-backup
echo "30 2 * * * bizimprint /usr/local/bin/bizimprint-backup" | sudo tee /etc/cron.d/bizimprint-backup >/dev/null

echo "==> Checking the app answers"
for i in $(seq 1 20); do
  if curl -fsS http://127.0.0.1:8000/api/disclaimers >/dev/null; then ok=1; break; fi
  sleep 2
done
if [ "${ok:-}" = 1 ]; then echo "The app is running."; else echo "The app didn't answer: see  sudo journalctl -u bizimprint -n 50"; fi

cat <<NEXT

Done. Next:
  1. Fill in your keys:        sudo nano $ENV_FILE
  2. Restart with them:        sudo systemctl restart bizimprint
  3. Check startup messages:   sudo journalctl -u bizimprint -n 30   (look for "Payments: ...")
  4. Open https://$DOMAIN      (the certificate can take a minute the first time)
NEXT
