#!/usr/bin/env bash
set -euo pipefail

PACKAGE_NAME="discord-component-v2"
SERVICE_BROKER="${PACKAGE_NAME}-broker.service"
SERVICE_WORKER="${PACKAGE_NAME}-worker.service"
SYSTEMD_USER_DIR="${XDG_CONFIG_HOME:-$HOME/.config}/systemd/user"

usage() {
  cat <<USAGE
Usage: ./manage.sh <command>

Commands:
  start        Start both user services
  stop         Stop both user services
  restart      Restart both user services
  status       Show status for both user services
  logs         Tail logs for both user services
  smoke-test   Run the local worker smoke test
  validate     Run the package validator
  doctor       Run environment checks and summarize likely issues
USAGE
}

[[ $# -ge 1 ]] || { usage; exit 1; }

have_services() {
  [[ -f "$SYSTEMD_USER_DIR/$SERVICE_BROKER" || -f "$SYSTEMD_USER_DIR/$SERVICE_WORKER" ]]
}

require_venv() {
  if [[ ! -x ".venv/bin/python" ]]; then
    echo "No virtual environment found in $(pwd)." >&2
    echo "Run ./install.sh first." >&2
    exit 1
  fi
}

case "$1" in
  start)
    have_services || { echo "Service files are not installed yet. Run ./install.sh first."; exit 1; }
    systemctl --user start "$SERVICE_BROKER" "$SERVICE_WORKER"
    ;;
  stop)
    have_services || { echo "Service files are not installed yet."; exit 1; }
    systemctl --user stop "$SERVICE_BROKER" "$SERVICE_WORKER"
    ;;
  restart)
    have_services || { echo "Service files are not installed yet. Run ./install.sh first."; exit 1; }
    systemctl --user restart "$SERVICE_BROKER" "$SERVICE_WORKER"
    ;;
  status)
    if have_services; then
      systemctl --user status "$SERVICE_BROKER" "$SERVICE_WORKER" || true
    else
      echo "Service files are not installed yet."
      echo "Run ./install.sh successfully before checking status."
      exit 1
    fi
    ;;
  logs)
    if have_services; then
      journalctl --user -u "$SERVICE_BROKER" -u "$SERVICE_WORKER" -f
    else
      echo "Service files are not installed yet."
      echo "Run ./install.sh successfully before checking logs."
      exit 1
    fi
    ;;
  smoke-test)
    require_venv
    ./.venv/bin/python tools/test_local_worker.py
    ;;
  validate)
    ./validate.sh
    ;;
  doctor)
    echo "Package directory: $(pwd)"
    if [[ -x ".venv/bin/python" ]]; then
      echo "Virtual environment: present"
    else
      echo "Virtual environment: missing"
    fi
    if command -v uv >/dev/null 2>&1; then
      echo "uv: installed"
    else
      echo "uv: not installed"
    fi
    if command -v openclaw >/dev/null 2>&1; then
      echo "openclaw: $(command -v openclaw)"
    else
      echo "openclaw: not found on PATH"
    fi
    if command -v systemctl >/dev/null 2>&1; then
      if systemctl --user show-environment >/dev/null 2>&1; then
        echo "systemd user manager: available"
      else
        echo "systemd user manager: not available in this shell"
      fi
    else
      echo "systemctl: not installed"
    fi
    if [[ -f ".install-manifest" ]]; then
      echo "Install manifest: present"
    else
      echo "Install manifest: missing"
    fi
    echo
    ./validate.sh --quick || true
    ;;
  *)
    usage
    exit 1
    ;;
esac
