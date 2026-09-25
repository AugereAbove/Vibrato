#!/usr/bin/env bash
set -euo pipefail

if [ "$(id -u)" -ne 0 ]; then
  echo "Run this with sudo: sudo deploy/gravity/scripts/restore.sh <backup.tar.gz> [--yes]" >&2
  exit 1
fi

ARCHIVE="${1:-}"
CONFIRM="${2:-}"
DATA_DIR="/opt/vibrato/data"

if [ -z "$ARCHIVE" ] || [ ! -f "$ARCHIVE" ]; then
  echo "Usage: sudo deploy/gravity/scripts/restore.sh <backup.tar.gz> [--yes]" >&2
  exit 1
fi

if [ "$CONFIRM" != "--yes" ]; then
  echo "This replaces everything currently in $DATA_DIR with the contents of:"
  echo "  $ARCHIVE"
  read -r -p "Type yes to continue: " ANSWER
  if [ "$ANSWER" != "yes" ]; then
    echo "Cancelled."
    exit 1
  fi
fi

echo "==> Stopping the service"
systemctl stop vibrato

SAFETY="$DATA_DIR.before-restore-$(date -u +%Y%m%d-%H%M%S)"
echo "==> Moving the current data directory to $SAFETY"
mv "$DATA_DIR" "$SAFETY"

echo "==> Extracting $ARCHIVE"
mkdir -p "$(dirname "$DATA_DIR")"
tar -C "$(dirname "$DATA_DIR")" -xzf "$ARCHIVE"
chown -R vibrato:vibrato "$DATA_DIR"

echo "==> Starting the service"
systemctl start vibrato
systemctl --no-pager status vibrato

echo
echo "Restored. The previous data directory is kept at $SAFETY until you delete it."
