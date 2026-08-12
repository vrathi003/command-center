#!/usr/bin/env bash
# Install or refresh only the Sphinx docs systemd unit (port 8080).
set -euo pipefail

if [[ "${EUID}" -ne 0 ]]; then
  echo "Run with sudo: sudo bash scripts/install_docs_service.sh"
  exit 1
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
SERVICE_USER="${SUDO_USER:-$(logname)}"
SERVICE_HOME="$(getent passwd "$SERVICE_USER" | cut -d: -f6)"

discover_uv() {
  local p
  for p in \
    "${SERVICE_HOME}/.local/bin/uv" \
    "${SERVICE_HOME}/.cargo/bin/uv" \
    /usr/local/bin/uv \
    /usr/bin/uv; do
    if [[ -x "$p" ]]; then
      printf '%s' "$p"
      return 0
    fi
  done
  sudo -u "$SERVICE_USER" env \
    "PATH=${SERVICE_HOME}/.local/bin:${SERVICE_HOME}/.cargo/bin:/usr/local/bin:/usr/bin:/bin" \
    bash -c 'command -v uv' 2>/dev/null || true
}

UV_BIN="$(discover_uv)"
if [[ -z "$UV_BIN" || ! -x "$UV_BIN" ]]; then
  echo "error: could not find uv for user ${SERVICE_USER}."
  exit 1
fi

echo "Using UV_BIN=${UV_BIN}"
echo "Ensuring docs dependency group is installed…"
sudo -u "$SERVICE_USER" "$UV_BIN" sync --group docs --project "$REPO_ROOT"

export REPO_ROOT SERVICE_USER UV_BIN
python3 <<'PY'
import os
import pathlib

repo = pathlib.Path(os.environ["REPO_ROOT"])
subs = {
    "__SERVICE_USER__": os.environ["SERVICE_USER"],
    "__REPO_ROOT__": str(repo),
    "__UV_BIN__": os.environ["UV_BIN"],
}
text = (repo / "scripts" / "systemd" / "finance-docs.service").read_text()
for k, v in subs.items():
    text = text.replace(k, v)
path = pathlib.Path("/etc/systemd/system/finance-docs.service")
path.write_text(text)
print(f"Wrote {path}")
PY

chmod 0644 /etc/systemd/system/finance-docs.service
systemctl daemon-reload
systemctl enable --now finance-docs.service
systemctl restart finance-docs.service

if ! systemctl is-active --quiet finance-docs.service; then
  echo "error: finance-docs.service is not active."
  systemctl status finance-docs.service --no-pager || true
  exit 1
fi

echo "Docs service is up: http://127.0.0.1:8080/guide/"
echo "After editing docs/guide/, run: sudo systemctl restart finance-docs.service"
echo "For MagicDNS access, run: make configure-tailscale"
echo "  → https://<your-machine>.ts.net/guide/"
