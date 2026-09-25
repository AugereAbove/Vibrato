#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")"
ROOT="$(pwd)"

pick_python() {
  for candidate in "${PYTHON:-}" python3.13 python3.12 python3.11 python3 python; do
    [ -z "$candidate" ] && continue
    if command -v "$candidate" >/dev/null 2>&1; then
      if "$candidate" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 11) else 1)' 2>/dev/null; then
        echo "$candidate"
        return 0
      fi
    fi
  done
  return 1
}

PY="$(pick_python)" || {
  echo "Vibrato needs Python 3.11 or newer. Install it and run ./setup.sh again (or set PYTHON=/path/to/python3.11)." >&2
  exit 1
}

if ! command -v node >/dev/null 2>&1; then
  echo "Node.js 20.19+ or 22.12+ is required for the interface. Install it from https://nodejs.org and run ./setup.sh again." >&2
  exit 1
fi

echo "==> Python: $("$PY" --version)"
echo "==> Node:   $(node --version)"

if [ ! -d "$ROOT/.venv" ]; then
  echo "==> Creating virtual environment in .venv"
  "$PY" -m venv "$ROOT/.venv"
fi

VENV_PY="$ROOT/.venv/bin/python"
"$VENV_PY" -m pip install --upgrade pip wheel >/dev/null

echo "==> Installing the analysis backend"
"$VENV_PY" -m pip install -e "$ROOT/backend[dev]"

echo "==> Installing optional decoders and the WORLD vocoder (skipped if they cannot be built)"
"$VENV_PY" -m pip install -e "$ROOT/backend[decoders]" || echo "    PyAV could not be installed: MP3/M4A/AAC import falls back to libsndfile and audioread."
"$VENV_PY" -m pip install -e "$ROOT/backend[world]" || echo "    pyworld could not be installed: the breathiness preview is disabled, everything else works."

if [ "${VIBRATO_NEURAL:-0}" = "1" ]; then
  echo "==> Installing optional neural pitch tracking (torch + torchcrepe)"
  "$VENV_PY" -m pip install -e "$ROOT/backend[neural]" || echo "    torch/torchcrepe could not be installed; CREPE stays unavailable."
fi

echo "==> Installing the interface"
cd "$ROOT/frontend"
if [ -f package-lock.json ]; then npm ci --no-audit --no-fund; else npm install --no-audit --no-fund; fi

echo "==> Building the interface"
npm run build

echo
echo "Setup complete. Start Vibrato with ./run.sh"
