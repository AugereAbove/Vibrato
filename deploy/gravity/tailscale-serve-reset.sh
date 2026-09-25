#!/usr/bin/env bash
set -euo pipefail

if ! command -v tailscale >/dev/null 2>&1; then
  echo "tailscale is not installed on this machine." >&2
  exit 1
fi

echo "==> Serve configuration before reset:"
tailscale serve status || true

echo
echo "==> Clearing all Tailscale Serve (and Funnel) configuration on this node"
if ! tailscale serve reset; then
  echo >&2
  echo "tailscale serve reset failed. If this is a permission error, re-run with sudo," >&2
  echo "or once run: sudo tailscale set --operator=\$USER" >&2
  exit 1
fi

echo
echo "Done. This node no longer serves anything over https://<name>.ts.net/."
echo "The app is still reachable the normal ways (localhost, LAN/Caddy) - only the"
echo "Tailscale HTTPS path was removed. Funnel was never enabled, so nothing changes there."
echo
tailscale serve status || true
