#!/usr/bin/env bash
set -euo pipefail

PACKAGE_NAME="discord-component-v2"
SERVICE_BROKER="${PACKAGE_NAME}-broker.service"
SERVICE_WORKER="${PACKAGE_NAME}-worker.service"

SRC_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
OPENCLAW_HOME="${OPENCLAW_HOME:-$HOME/.openclaw}"
INSTALL_DIR="${INSTALL_DIR:-$OPENCLAW_HOME/workspace/skills/$PACKAGE_NAME}"
SYSTEMD_USER_DIR="${XDG_CONFIG_HOME:-$HOME/.config}/systemd/user"
MANIFEST_PATH="$INSTALL_DIR/.install-manifest"
BACKUP_SUFFIX="$(date +%Y%m%d-%H%M%S)"
AUTO_DEPS=0
SKIP_SERVICES=0
FORCE_PIP=0

usage() {
  cat <<USAGE
Usage: ./install.sh [--install-system-deps] [--skip-services] [--force-pip]

Options:
  --install-system-deps   Try to install Debian/Ubuntu packages with sudo apt
  --skip-services         Do not register or start user systemd services
  --force-pip             Skip uv even if uv is installed
USAGE
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --install-system-deps) AUTO_DEPS=1; shift ;;
    --skip-services) SKIP_SERVICES=1; shift ;;
    --force-pip) FORCE_PIP=1; shift ;;
    -h|--help) usage; exit 0 ;;
    *) echo "Unknown option: $1" >&2; usage; exit 1 ;;
  esac
done

info() { echo "[install] $*"; }
warn() { echo "[install][warn] $*" >&2; }
die() { echo "[install][error] $*" >&2; exit 1; }
need_cmd() { command -v "$1" >/dev/null 2>&1 || die "Missing required command: $1"; }

check_package_layout() {
  local missing=0
  for path in install.sh manage.sh uninstall.sh validate.sh requirements.txt schema/init.sql scripts/broker_gateway.py scripts/worker.py lib/db.py; do
    if [[ ! -e "$SRC_DIR/$path" ]]; then
      echo "Package layout check failed: missing $path" >&2
      missing=1
    fi
  done
  [[ "$missing" -eq 0 ]] || exit 1
}

python_minor_hint() {
  python3 - <<'PY'
import sys
print(f"python{sys.version_info.major}.{sys.version_info.minor}-venv")
PY
}

maybe_install_system_deps() {
  local pkg_hint
  pkg_hint="$(python_minor_hint)"
  if [[ "$AUTO_DEPS" -eq 1 ]] && command -v sudo >/dev/null 2>&1 && command -v apt-get >/dev/null 2>&1; then
    info "Installing Debian/Ubuntu system packages..."
    sudo apt-get update
    sudo apt-get install -y "$pkg_hint" python3-pip sqlite3
    return 0
  fi
  cat >&2 <<HELP
Missing required system support for Python virtual environments.

Typical Debian/Ubuntu fix:
  sudo apt update
  sudo apt install -y $pkg_hint python3-pip sqlite3

Then rerun:
  ./install.sh

Or rerun with:
  ./install.sh --install-system-deps
HELP
  exit 1
}

ensure_base_tools() {
  need_cmd python3
  need_cmd tar
  if ! python3 -c "import sqlite3" >/dev/null 2>&1; then
    die "Python sqlite3 support is missing from this interpreter."
  fi
  if ! command -v openclaw >/dev/null 2>&1; then
    warn "The openclaw binary is not on PATH. Installation can continue, but card sending and CLI reinjection will not work until OPENCLAW_BIN or PATH is fixed."
  fi
}

select_python_strategy() {
  if [[ "$FORCE_PIP" -eq 0 ]] && command -v uv >/dev/null 2>&1; then
    echo "uv"
    return 0
  fi
  if python3 -c "import venv" >/dev/null 2>&1; then
    echo "venv"
    return 0
  fi
  maybe_install_system_deps
  if python3 -c "import venv" >/dev/null 2>&1; then
    echo "venv"
    return 0
  fi
  die "Python venv support is still unavailable after dependency installation."
}

copy_package() {
  mkdir -p "$(dirname "$INSTALL_DIR")"
  if [[ "$SRC_DIR" != "$INSTALL_DIR" && -e "$INSTALL_DIR" ]]; then
    mv "$INSTALL_DIR" "${INSTALL_DIR}.bak-${BACKUP_SUFFIX}"
    info "Backed up existing install to ${INSTALL_DIR}.bak-${BACKUP_SUFFIX}"
  fi
  if [[ "$SRC_DIR" != "$INSTALL_DIR" ]]; then
    rm -rf "$INSTALL_DIR"
    mkdir -p "$INSTALL_DIR"
    tar --exclude='.venv' --exclude='state/bridge.db' --exclude='state/openclaw_inbox.jsonl' --exclude='__pycache__' --exclude='.DS_Store' -C "$SRC_DIR" -cf - . | tar -C "$INSTALL_DIR" -xf -
    info "Copied package to $INSTALL_DIR"
  else
    info "Installing in place from $INSTALL_DIR"
  fi
}

setup_python_env() {
  cd "$INSTALL_DIR"
  mkdir -p state
  local strategy="$1"
  local python_path="$INSTALL_DIR/.venv/bin/python"

  if [[ "$strategy" == "uv" ]]; then
    info "Using uv to create the virtual environment and install dependencies."
    rm -rf .venv
    uv venv .venv
    uv pip install --python "$python_path" -r requirements.txt
  else
    info "Using python3 -m venv to create the virtual environment."
    rm -rf .venv
    python3 -m venv .venv || maybe_install_system_deps
    "$python_path" -m pip install --upgrade pip
    "$INSTALL_DIR/.venv/bin/pip" install -r requirements.txt
  fi

  "$python_path" - <<'PY'
from lib import db
db.init_db()
print("Initialized SQLite database")
PY
}

can_manage_user_services() {
  command -v systemctl >/dev/null 2>&1 || return 1
  systemctl --user show-environment >/dev/null 2>&1 || return 1
  return 0
}

install_services() {
  if [[ "$SKIP_SERVICES" -eq 1 ]]; then
    info "Skipping service installation (--skip-services)"
    return 0
  fi
  if ! can_manage_user_services; then
    warn "User systemd is not available in this shell. Services were not registered."
    warn "You can still run manually:"
    warn "  $INSTALL_DIR/.venv/bin/python $INSTALL_DIR/scripts/broker_gateway.py"
    warn "  $INSTALL_DIR/.venv/bin/python $INSTALL_DIR/scripts/worker.py"
    return 0
  fi
  mkdir -p "$SYSTEMD_USER_DIR"
  local python_path="$INSTALL_DIR/.venv/bin/python"
  sed -e "s#__INSTALL_DIR__#$INSTALL_DIR#g" -e "s#__PYTHON__#$python_path#g" "$INSTALL_DIR/systemd/$SERVICE_BROKER.template" > "$SYSTEMD_USER_DIR/$SERVICE_BROKER"
  sed -e "s#__INSTALL_DIR__#$INSTALL_DIR#g" -e "s#__PYTHON__#$python_path#g" "$INSTALL_DIR/systemd/$SERVICE_WORKER.template" > "$SYSTEMD_USER_DIR/$SERVICE_WORKER"
  systemctl --user daemon-reload
  systemctl --user enable --now "$SERVICE_BROKER"
  systemctl --user enable --now "$SERVICE_WORKER"
  info "Registered and started user services."
}

write_manifest() {
  cat > "$MANIFEST_PATH" <<MANIFEST
PACKAGE_NAME=$PACKAGE_NAME
INSTALL_DIR=$INSTALL_DIR
SERVICE_BROKER=$SERVICE_BROKER
SERVICE_WORKER=$SERVICE_WORKER
SYSTEMD_USER_DIR=$SYSTEMD_USER_DIR
INSTALLED_AT=$(date -Iseconds)
MANIFEST
}

run_post_install_validation() {
  info "Running package validation..."
  "$INSTALL_DIR/validate.sh" --quick
}

check_package_layout
ensure_base_tools
STRATEGY="$(select_python_strategy)"
copy_package
setup_python_env "$STRATEGY"
install_services
write_manifest
run_post_install_validation

echo
echo "Installation complete."
echo "Install dir: $INSTALL_DIR"
echo "Python strategy: $STRATEGY"
echo "Next steps:"
echo "  cd $INSTALL_DIR"
echo "  ./manage.sh doctor"
echo "  ./manage.sh status"
echo "  ./manage.sh logs"
echo "  ./.venv/bin/python scripts/send_action.py demo-hello --channel-id <CHANNEL_ID>"
