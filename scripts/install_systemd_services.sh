#!/usr/bin/env bash
set -euo pipefail

if [[ "${EUID}" -ne 0 ]]; then
  echo "Run with sudo: sudo bash scripts/install_systemd_services.sh"
  exit 1
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
SERVICE_USER="${SUDO_USER:-$(logname)}"
SERVICE_HOME="$(getent passwd "$SERVICE_USER" | cut -d: -f6)"

nvm_bin_dirs() {
  local extra="" d
  shopt -s nullglob
  for d in "${SERVICE_HOME}/.nvm/versions/node/"*/bin; do
    if [[ -d "$d" ]]; then
      extra="${extra:+$extra:}$d"
    fi
  done
  shopt -u nullglob
  printf '%s' "$extra"
}

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

discover_npm() {
  local p extra
  shopt -s nullglob
  for p in "${SERVICE_HOME}/.nvm/versions/node/"*/bin/npm; do
    if [[ -x "$p" ]]; then
      printf '%s' "$p"
      shopt -u nullglob
      return 0
    fi
  done
  shopt -u nullglob
  for p in /usr/bin/npm /usr/local/bin/npm; do
    if [[ -x "$p" ]]; then
      printf '%s' "$p"
      return 0
    fi
  done
  extra="$(nvm_bin_dirs)"
  sudo -u "$SERVICE_USER" env \
    "PATH=${extra:+$extra:}${SERVICE_HOME}/.local/bin:/usr/local/bin:/usr/bin:/bin" \
    bash -c 'command -v npm' 2>/dev/null || true
}

UV_BIN="$(discover_uv)"
NPM_BIN="$(discover_npm)"
NODE_BIN="$(dirname "$NPM_BIN")/node"

if [[ -z "$UV_BIN" || ! -x "$UV_BIN" ]]; then
  echo "error: could not find uv for user ${SERVICE_USER}."
  echo "Install uv (https://docs.astral.sh/uv/) or ensure ${SERVICE_HOME}/.local/bin/uv exists."
  exit 1
fi
if [[ -z "$NPM_BIN" || ! -x "$NPM_BIN" ]]; then
  echo "error: could not find npm for user ${SERVICE_USER}."
  echo "Install Node.js/npm or ensure nvm’s npm is under ${SERVICE_HOME}/.nvm/versions/node/"
  exit 1
fi
if [[ ! -x "$NODE_BIN" ]]; then
  echo "error: could not find node beside npm at ${NODE_BIN}."
  echo "Install Node.js properly or ensure npm/node come from the same bin directory."
  exit 1
fi

echo "Using UV_BIN=${UV_BIN}"
echo "Using NPM_BIN=${NPM_BIN}"
echo "Using NODE_BIN=${NODE_BIN}"

export REPO_ROOT SERVICE_USER UV_BIN NPM_BIN NODE_BIN
python3 <<'PY'
import os
import pathlib

repo = pathlib.Path(os.environ["REPO_ROOT"])
user = os.environ["SERVICE_USER"]
uv = os.environ["UV_BIN"]
npm = os.environ["NPM_BIN"]
node_bin = os.environ["NODE_BIN"]
node_bin_dir = str(pathlib.Path(node_bin).parent)

subs = {
    "__SERVICE_USER__": user,
    "__REPO_ROOT__": str(repo),
    "__UV_BIN__": uv,
    "__NPM_BIN__": npm,
    "__NODE_BIN_DIR__": node_bin_dir,
}

def render(name: str) -> str:
    text = (repo / "scripts" / "systemd" / name).read_text()
    for k, v in subs.items():
        if k not in text:
            continue
        text = text.replace(k, v)
    return text

out_dir = pathlib.Path("/etc/systemd/system")
out_dir.joinpath("finance-api.service").write_text(render("finance-api.service"))
out_dir.joinpath("finance-dashboard.service").write_text(render("finance-dashboard.service"))
out_dir.joinpath("finance-bot.service").write_text(render("finance-bot.service"))
PY

chmod 0644 /etc/systemd/system/finance-api.service /etc/systemd/system/finance-dashboard.service /etc/systemd/system/finance-bot.service

systemctl daemon-reload
systemctl enable --now finance-api.service
systemctl enable --now finance-dashboard.service
systemctl enable --now finance-bot.service

for svc in finance-api.service finance-dashboard.service finance-bot.service; do
  if ! systemctl is-active --quiet "$svc"; then
    echo "error: $svc is not active after install."
    systemctl status "$svc" --no-pager || true
    exit 1
  fi
done

echo "Services installed and started."
echo "Check status with:"
echo "  systemctl status finance-api.service finance-dashboard.service finance-bot.service"
