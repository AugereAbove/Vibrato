#!/usr/bin/env bash
set -euo pipefail

DATA_DIR="/opt/vibrato/data"
BACKUP_DIR="/opt/vibrato/host-backups"
KEEP="${VIBRATO_BACKUP_KEEP:-14}"
STAMP="$(date -u +%Y%m%d-%H%M%S)"
DEST="$BACKUP_DIR/vibrato-$STAMP.tar.gz"

if [ "$(id -u)" -eq 0 ]; then
  RUN_AS="sudo -u vibrato -H"
else
  RUN_AS=""
fi

mkdir -p "$BACKUP_DIR"
echo "==> Backing up $DATA_DIR to $DEST"
$RUN_AS tar -C "$(dirname "$DATA_DIR")" -czf "$DEST" "$(basename "$DATA_DIR")"

echo "==> Keeping the newest $KEEP backups"
ls -1t "$BACKUP_DIR"/vibrato-*.tar.gz 2>/dev/null | tail -n "+$((KEEP + 1))" | xargs -r rm -f

echo "Backup written to $DEST"
