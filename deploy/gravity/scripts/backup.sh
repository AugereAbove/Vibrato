#!/usr/bin/env bash
set -euo pipefail

BASE_DIR="/opt/vibrato"
DATA_DIR="$BASE_DIR/data"
BACKUP_DIR="$BASE_DIR/host-backups"
KEEP="${VIBRATO_BACKUP_KEEP:-14}"
STAMP="$(date -u +%Y%m%d-%H%M%S)"
DEST="$BACKUP_DIR/vibrato-$STAMP.tar.gz"
SNAPSHOT="$DATA_DIR/backups/host-snapshot.sqlite"

if [ "$(id -u)" -eq 0 ]; then
  RUN_AS="sudo -u vibrato -H"
else
  RUN_AS=""
fi

echo "==> Taking a consistent snapshot of the database"
$RUN_AS python3 - "$DATA_DIR/vibrato.db" "$SNAPSHOT" <<'PY'
import os
import sqlite3
import sys

source, target = sys.argv[1], sys.argv[2]
src = sqlite3.connect(source, timeout=60)
dst = sqlite3.connect(target + ".tmp")
with dst:
    src.backup(dst)
dst.close()
src.close()
os.replace(target + ".tmp", target)
PY

echo "==> Backing up $DATA_DIR to $DEST"
$RUN_AS tar -C "$BASE_DIR" -czf "$DEST.partial" \
  --exclude="data/vibrato.db" \
  --exclude="data/vibrato.db-wal" \
  --exclude="data/vibrato.db-shm" \
  --exclude="data/numba-cache" \
  --exclude="data/uploads" \
  data
$RUN_AS mv "$DEST.partial" "$DEST"

echo "==> Keeping the newest $KEEP backups"
ls -1t "$BACKUP_DIR"/vibrato-*.tar.gz 2>/dev/null | tail -n "+$((KEEP + 1))" | xargs -r rm -f

echo "Backup written to $DEST ($(du -h "$DEST" | cut -f1))"
