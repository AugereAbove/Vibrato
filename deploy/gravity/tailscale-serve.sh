#!/usr/bin/env bash
set -euo pipefail

ENV_FILE="/opt/vibrato/shared/vibrato.env"
HOST="127.0.0.1"
PORT="8765"

if [ -f "$ENV_FILE" ]; then
  set -a
  source "$ENV_FILE"
  set +a
  HOST="${VIBRATO_HOST:-127.0.0.1}"
  PORT="${VIBRATO_PORT:-8765}"
fi

PORT="${1:-$PORT}"
TARGET="$HOST:$PORT"

if ! command -v tailscale >/dev/null 2>&1; then
  echo "tailscale is not installed on this machine." >&2
  echo "Install it with: curl -fsSL https://tailscale.com/install.sh | sh" >&2
  exit 1
fi

if ! tailscale status >/dev/null 2>&1; then
  echo "tailscaled is not running or this node is not logged in yet." >&2
  echo "Run: sudo tailscale up" >&2
  exit 1
fi

echo "==> Pointing Tailscale Serve at http://$TARGET (tailnet-only HTTPS on 443)"
if ! tailscale serve --bg --https=443 "$TARGET"; then
  echo >&2
  echo "tailscale serve failed. Common causes:" >&2
  echo "  permission denied  - re-run with sudo, or once run: sudo tailscale set --operator=\$USER" >&2
  echo "  HTTPS not enabled  - turn on HTTPS Certificates for your tailnet at:" >&2
  echo "                       https://login.tailscale.com/admin/dns" >&2
  exit 1
fi

echo
tailscale serve status

DNS_NAME="$(tailscale status --json 2>/dev/null | python3 -c '
import json, sys
try:
    data = json.load(sys.stdin)
    name = data.get("Self", {}).get("DNSName", "").rstrip(".")
    print(name)
except Exception:
    pass
' 2>/dev/null || true)"

echo
if [ -n "$DNS_NAME" ]; then
  echo "Vibrato is now reachable, only within your tailnet, at:"
  echo "  https://$DNS_NAME/"
else
  echo "Run 'tailscale status' and look for this node's name under Self > DNSName,"
  echo "then browse to https://<that name>/ from any device on your tailnet."
fi
echo
echo "This uses Tailscale Serve, not Funnel. Nothing here is reachable from the public"
echo "internet, and Funnel has not been touched. The app is still bound to 127.0.0.1"
echo "and unreachable directly from any other machine, on or off your tailnet."
