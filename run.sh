#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")"
ROOT="$(pwd)"
VENV_PY="$ROOT/.venv/bin/python"
PORT="${VIBRATO_PORT:-8765}"
MODE="app"
OPEN="--open"

for arg in "$@"; do
  case "$arg" in
    --dev) MODE="dev" ;;
    --no-browser) OPEN="" ;;
    --help|-h)
      echo "Usage: ./run.sh [--dev] [--no-browser]"
      echo "  (default)     serve the built interface and the analysis server on http://127.0.0.1:$PORT"
      echo "  --dev         hot-reloading interface on http://127.0.0.1:5173 plus an auto-reloading backend"
      echo "  --no-browser  do not open a browser window"
      exit 0
      ;;
    *) echo "Unknown option: $arg (see ./run.sh --help)" >&2; exit 2 ;;
  esac
done

if [ ! -x "$VENV_PY" ]; then
  echo "Vibrato is not set up yet. Run ./setup.sh first." >&2
  exit 1
fi

export VIBRATO_PORT="$PORT"

if [ "$MODE" = "dev" ]; then
  cleanup() {
    trap - INT TERM EXIT
    kill 0 2>/dev/null || true
  }
  trap cleanup INT TERM EXIT
  "$VENV_PY" -m vibrato --reload &
  (cd "$ROOT/frontend" && VIBRATO_API="http://127.0.0.1:$PORT" npx vite --host 127.0.0.1 --port 5173 ${OPEN:+--open}) &
  wait
  exit 0
fi

if [ ! -f "$ROOT/frontend/dist/index.html" ]; then
  echo "==> Building the interface (first run)"
  (cd "$ROOT/frontend" && npm run build)
fi

echo "Vibrato is starting on http://127.0.0.1:$PORT  (Ctrl+C to stop)"
exec "$VENV_PY" -m vibrato $OPEN
