#!/usr/bin/env bash
# Upsert Personal Finance OS Tailscale Serve handlers without wiping other apps.
set -euo pipefail

if ! command -v tailscale >/dev/null 2>&1; then
  echo "tailscale CLI not found. Install Tailscale first."
  exit 1
fi

# Prefer plain tailscale; use sudo when the daemon rejects an unprivileged call.
ts() {
  if tailscale "$@" 2>/dev/null; then
    return 0
  fi
  if [[ "${EUID}" -ne 0 ]] && command -v sudo >/dev/null 2>&1; then
    sudo "$(command -v tailscale)" "$@"
    return $?
  fi
  # Surface the original error.
  tailscale "$@"
}

if ! ts status >/dev/null; then
  echo "Tailscale is not connected. Run: sudo tailscale up"
  exit 1
fi

# Local backends for this project (all bind 127.0.0.1).
DASHBOARD_URL="${FINANCE_TS_DASHBOARD_URL:-http://127.0.0.1:4173}"
API_URL="${FINANCE_TS_API_URL:-http://127.0.0.1:8000/api}"
DOCS_URL="${FINANCE_TS_DOCS_URL:-http://127.0.0.1:8080}"

# Paths under MagicDNS HTTPS (443). Override if they collide with other apps.
DASHBOARD_PATH="${FINANCE_TS_DASHBOARD_PATH:-/}"
API_PATH="${FINANCE_TS_API_PATH:-/api}"
DOCS_PATH="${FINANCE_TS_DOCS_PATH:-/guide}"

echo "Existing Tailscale Serve handlers (before — other apps preserved):"
ts serve status || true
echo ""

# Never `serve reset` — that would drop handlers for every other app on this host.

# Root `/` may belong to another product. Only claim it when free or already ours.
claim_root=1
if [[ "$DASHBOARD_PATH" == "/" ]]; then
  existing="$(ts serve status --json 2>/dev/null || true)"
  if [[ -n "$existing" ]]; then
    root_proxy="$(
      printf '%s' "$existing" | python3 -c '
import json, sys
try:
    data = json.load(sys.stdin)
except Exception:
    sys.exit(0)
web = data.get("Web") or data.get("web") or {}
if not isinstance(web, dict):
    sys.exit(0)
for _host, cfg in web.items():
    if not isinstance(cfg, dict):
        continue
    handlers = cfg.get("Handlers") or cfg.get("handlers") or {}
    if "/" in handlers and isinstance(handlers["/"], dict):
        h = handlers["/"]
        print(h.get("Proxy") or h.get("proxy") or "")
        break
'
    )"
    if [[ -n "$root_proxy" && "$root_proxy" != "$DASHBOARD_URL" && "$root_proxy" != "${DASHBOARD_URL}/" ]]; then
      echo "Skipping dashboard path '/' — already proxied to: ${root_proxy}"
      echo "  Set FINANCE_TS_DASHBOARD_PATH=/finance (or similar) if you want a dedicated path."
      claim_root=0
    fi
  fi
fi

if [[ "$claim_root" -eq 1 ]]; then
  echo "Upserting dashboard: ${DASHBOARD_PATH} → ${DASHBOARD_URL}"
  if [[ "$DASHBOARD_PATH" == "/" ]]; then
    ts serve --bg --https=443 "$DASHBOARD_URL"
  else
    ts serve --bg --https=443 --set-path="$DASHBOARD_PATH" "$DASHBOARD_URL"
  fi
fi

echo "Upserting API:  ${API_PATH} → ${API_URL}"
ts serve --bg --https=443 --set-path="$API_PATH" "$API_URL"

echo "Upserting docs: ${DOCS_PATH} → ${DOCS_URL}"
ts serve --bg --https=443 --set-path="$DOCS_PATH" "$DOCS_URL"

echo ""
echo "Tailscale Serve configured (full map — all apps):"
ts serve status || true

DNS="$(
  ts status --json 2>/dev/null | python3 -c '
import json, sys
data = json.load(sys.stdin)
print(data["Self"]["DNSName"].rstrip("."))
' 2>/dev/null || true
)"
if [[ -z "$DNS" ]]; then
  DNS="<your-machine>.ts.net"
fi

echo ""
echo "Personal Finance OS URLs:"
if [[ "$claim_root" -eq 1 ]]; then
  if [[ "$DASHBOARD_PATH" == "/" ]]; then
    echo "  Dashboard: https://${DNS}/"
  else
    echo "  Dashboard: https://${DNS}${DASHBOARD_PATH}/"
  fi
fi
echo "  API:       https://${DNS}${API_PATH}"
echo "  Docs:      https://${DNS}${DOCS_PATH}/"
echo ""
echo "Other apps on this host keep their existing Serve handlers (no reset)."
