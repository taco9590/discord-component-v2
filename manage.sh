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
      PYTHON_BIN=".venv/bin/python"
    else
      echo "Virtual environment: missing"
      PYTHON_BIN="python3"
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
    echo "Bridge state summary:"
    if [[ -f state/bridge.db ]]; then
      "$PYTHON_BIN" - <<'PY'
import sqlite3
from pathlib import Path
p = Path('state/bridge.db')
conn = sqlite3.connect(p)
cur = conn.cursor()
queries = {
    'messages': "select count(*) from messages",
    'components_total': "select count(*) from components",
    'components_active': "select count(*) from components where status='active'",
    'components_used': "select count(*) from components where status='used'",
    'interactions_total': "select count(*) from interaction_events",
    'queued': "select count(*) from interaction_events where process_state='queued'",
    'processing': "select count(*) from interaction_events where process_state='processing'",
    'done': "select count(*) from interaction_events where process_state='done'",
    'done_fallback': "select count(*) from interaction_events where process_state='done_fallback'",
    'failed': "select count(*) from interaction_events where process_state='failed'",
}
for k, q in queries.items():
    try:
        print(f"  {k}: {cur.execute(q).fetchone()[0]}")
    except Exception as e:
        print(f"  {k}: error ({e})")
try:
    row = cur.execute("select interaction_id, custom_id, process_state, error_text, created_at from interaction_events order by created_at desc limit 5").fetchall()
    if row:
        print("  recent interactions:")
        for iid, custom_id, state, error_text, created_at in row:
            note = f" | {error_text}" if error_text else ""
            print(f"    - {created_at} | {state} | {custom_id} | {iid}{note}")
except Exception as e:
    print(f"  recent interactions: error ({e})")
conn.close()
PY
    else
      echo "  state database: missing"
    fi
    echo
    ./validate.sh --quick || true
    ;;
  *)
    usage
    exit 1
    ;;
esac
