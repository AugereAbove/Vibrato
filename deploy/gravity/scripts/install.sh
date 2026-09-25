#!/usr/bin/env bash
set -euo pipefail

if [ "$(id -u)" -ne 0 ]; then
  echo "Run this with sudo: sudo deploy/gravity/scripts/install.sh" >&2
  exit 1
fi

APP_DIR="$(cd "$(dirname "$0")/../../.." && pwd)"
BASE_DIR="/opt/vibrato"
DATA_DIR="$BASE_DIR/data"
SHARED_DIR="$BASE_DIR/shared"
BACKUP_DIR="$BASE_DIR/host-backups"

if [ "$APP_DIR" != "$BASE_DIR/app" ]; then
  echo "This script expects the repository to be checked out at $BASE_DIR/app (found: $APP_DIR)." >&2
  echo "Move or re-clone it there, then run this script again." >&2
  exit 1
fi

if ! id -u vibrato >/dev/null 2>&1; then
  echo "==> Creating the vibrato system user"
  useradd --system --home-dir "$BASE_DIR" --shell /usr/sbin/nologin --create-home vibrato
fi

echo "==> Creating $DATA_DIR, $SHARED_DIR and $BACKUP_DIR"
mkdir -p "$DATA_DIR" "$SHARED_DIR" "$BACKUP_DIR"
chown -R vibrato:vibrato "$BASE_DIR"
chmod 750 "$DATA_DIR" "$SHARED_DIR" "$BACKUP_DIR"

if [ ! -f "$SHARED_DIR/vibrato.env" ]; then
  echo "==> Writing a starting $SHARED_DIR/vibrato.env"
  cp "$APP_DIR/deploy/gravity/vibrato.env.example" "$SHARED_DIR/vibrato.env"
  chown vibrato:vibrato "$SHARED_DIR/vibrato.env"
  chmod 640 "$SHARED_DIR/vibrato.env"
else
  echo "==> $SHARED_DIR/vibrato.env already exists, leaving it as is"
fi

echo "==> Installing the backend and building the interface as the vibrato user"
sudo -u vibrato -H bash -lc "cd '$APP_DIR' && ./setup.sh"

echo "==> Installing the systemd service"
cp "$APP_DIR/deploy/gravity/systemd/vibrato.service" /etc/systemd/system/vibrato.service
systemctl daemon-reload
systemctl enable vibrato
systemctl restart vibrato

echo
echo "Vibrato is now running under systemd. Check it with: systemctl status vibrato"
echo "It is only reachable from this machine so far, on 127.0.0.1:8765."
echo "Point a reverse proxy at it next; see deploy/gravity/Caddyfile."
