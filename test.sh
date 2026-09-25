#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")"
ROOT="$(pwd)"
VENV="$ROOT/.venv/bin"
E2E=0

for arg in "$@"; do
  case "$arg" in
    --e2e) E2E=1 ;;
    --help|-h)
      echo "Usage: ./test.sh [--e2e]"
      echo "  Runs backend lint, type checks and tests, then frontend type checks, lint and unit tests."
      echo "  --e2e also builds the interface and runs the Playwright browser tests."
      exit 0
      ;;
    *) echo "Unknown option: $arg" >&2; exit 2 ;;
  esac
done

if [ ! -x "$VENV/python" ]; then
  echo "Run ./setup.sh first." >&2
  exit 1
fi

step() { printf '\n==> %s\n' "$1"; }

cd "$ROOT/backend"
step "backend: ruff"
"$VENV/ruff" check vibrato tests
"$VENV/ruff" format --check vibrato tests
step "backend: mypy"
"$VENV/mypy" vibrato
step "backend: pytest"
"$VENV/python" -m pytest

cd "$ROOT/frontend"
step "frontend: typecheck"
npm run --silent typecheck
step "frontend: eslint"
npm run --silent lint
step "frontend: prettier"
npm run --silent format:check
step "frontend: vitest"
npm run --silent test

if [ "$E2E" = "1" ]; then
  step "frontend: build"
  npm run --silent build
  step "frontend: playwright"
  VIBRATO_PYTHON="$VENV/python" npx playwright test
fi

printf '\nAll checks passed.\n'
