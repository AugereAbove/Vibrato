#!/usr/bin/env bash
set -euo pipefail

if [ "$(id -u)" -ne 0 ]; then
  echo "Run this with sudo: sudo deploy/gravity/scripts/deploy.sh [ref]" >&2
  exit 1
fi

APP_DIR="/opt/vibrato/app"
REF="${1:-}"

cd "$APP_DIR"

echo "==> Fetching the latest history"
sudo -u vibrato -H git -C "$APP_DIR" fetch --all --tags

if [ -n "$REF" ]; then
  echo "==> Checking out $REF"
  sudo -u vibrato -H git -C "$APP_DIR" checkout "$REF"
else
  BRANCH="$(sudo -u vibrato -H git -C "$APP_DIR" rev-parse --abbrev-ref HEAD)"
  echo "==> Fast-forwarding $BRANCH"
  sudo -u vibrato -H git -C "$APP_DIR" merge --ff-only "origin/$BRANCH"
fi

echo "==> Reinstalling dependencies and rebuilding the interface"
sudo -u vibrato -H bash -lc "cd '$APP_DIR' && ./setup.sh"

echo "==> Restarting the service"
systemctl restart vibrato
systemctl --no-pager status vibrato

echo
echo "Deployed $(sudo -u vibrato -H git -C "$APP_DIR" rev-parse --short HEAD)."
