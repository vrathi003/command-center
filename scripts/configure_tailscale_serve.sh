#!/usr/bin/env bash
set -euo pipefail

if ! command -v tailscale >/dev/null 2>&1; then
  echo "tailscale CLI not found. Install Tailscale first."
  exit 1
fi

TS="tailscale"
if [[ "${EUID}" -ne 0 ]] && command -v sudo >/dev/null 2>&1; then
  TS="sudo tailscale"
fi

if ! ${TS} status >/dev/null 2>&1; then
  echo "Tailscale is not connected. Run: sudo tailscale up"
  exit 1
fi

${TS} serve reset
${TS} serve --bg --https=443 http://127.0.0.1:4173
${TS} serve --bg --https=443 --set-path=/api http://127.0.0.1:8000/api

echo "Tailscale Serve configured."
echo "Open this on any device in your tailnet:"
${TS} serve status
${TS} status --json | python3 -c "import json,sys; data=json.load(sys.stdin); print('https://' + data['Self']['DNSName'].rstrip('.'))"
