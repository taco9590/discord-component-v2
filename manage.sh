#!/usr/bin/env bash
set -euo pipefail

PACKAGE_NAME="discord-component-v2"
SRC_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
WORKSPACE_ID="${DISCORD_COMPONENT_V2_WORKSPACE_ID:-$SRC_DIR}"
WORKSPACE_SLUG="$(WORKSPACE_ID="$WORKSPACE_ID" python3 - <<'PY'
import hashlib, os
raw = os.environ.get('WORKSPACE_ID') or ''
base = os.path.basename(raw) or 'workspace'
safe = ''.join(ch if ch.isalnum() or ch in '-_' else '-' for ch in base).strip('-') or 'workspace'
print(f"{safe}-{hashlib.sha1(raw.encode('utf-8')).hexdigest()[:10]}")
PY
)"
SERVICE_BROKER="${PACKAGE_NAME}-${WORKSPACE_SLUG}-broker.service"
SERVICE_WORKER="${PACKAGE_NAME}-${WORKSPACE_SLUG}-worker.service"
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
    echo "Workspace id: $WORKSPACE_ID"
    echo "Workspace slug: $WORKSPACE_SLUG"
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
    echo "Expected broker service: $SERVICE_BROKER"
    echo "Expected worker service: $SERVICE_WORKER"
    if [[ -f "$SYSTEMD_USER_DIR/$SERVICE_BROKER" ]]; then
      echo "Broker service file: present"
    else
      echo "Broker service file: missing"
    fi
    if [[ -f "$SYSTEMD_USER_DIR/$SERVICE_WORKER" ]]; then
      echo "Worker service file: present"
    else
      echo "Worker service file: missing"
    fi
    if [[ -f ".install-manifest" ]]; then
      echo "Install manifest: present"
    else
      echo "Install manifest: missing"
    fi
    echo
    "$PYTHON_BIN" - <<'PY'
from lib.config import STATE_DIR, DB_PATH, INBOX_PATH, RUNTIME_DIR, load_discord_token, token_lock_path
print(f"Resolved state dir: {STATE_DIR}")
print(f"Resolved db path: {DB_PATH}")
print(f"Resolved inbox path: {INBOX_PATH}")
print(f"Resolved runtime dir: {RUNTIME_DIR}")
token = load_discord_token()
if token:
    print(f"Token lock path: {token_lock_path(token)}")
else:
    print("Token lock path: unavailable (missing token)")
PY
    echo
    echo "Bridge state summary:"
    "$PYTHON_BIN" - <<'PY'
import json
import sqlite3
from pathlib import Path
from lib.config import DB_PATH, load_discord_token, token_lock_path
p = Path(DB_PATH)
if not p.exists():
    print("  state database: missing")
    raise SystemExit(0)
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
    'blocked_not_allowed': "select count(*) from interaction_events where error_text='blocked:not-allowed'",
    'blocked_single_use': "select count(*) from interaction_events where error_text='blocked:single_use'",
    'modal_opened': "select count(*) from interaction_events where normalized_text='modal-opened'",
    'fallback_inbox': "select count(*) from interaction_events where error_text='inbox'",
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
try:
    row = cur.execute("select raw_json from interaction_events where custom_id like 'ocm:%' order by id desc limit 1").fetchone()
    if row and row[0]:
        raw = json.loads(row[0])
        fields = ((raw.get('bridge_component') or {}).get('fields') or []) if isinstance(raw, dict) else []
        print(f"  last_modal_fields_count: {len(fields)}")
        if not fields:
            print("  warning: last modal submit had zero normalized fields")
except Exception as e:
    print(f"  last_modal_fields_count: error ({e})")
token = load_discord_token()
if token:
    lock = token_lock_path(token)
    if lock.exists():
        try:
            data = json.loads(lock.read_text(encoding='utf-8'))
            print(f"  token_lock: present | workspace={data.get('workspace')} pid={data.get('pid')}")
        except Exception as e:
            print(f"  token_lock: unreadable ({e})")
    else:
        print("  token_lock: missing")
conn.close()
PY
    echo
    if pgrep -af 'broker_gateway.py' >/dev/null 2>&1; then
      echo "Broker processes on host:"
      pgrep -af 'broker_gateway.py' || true
    fi
    if pgrep -af 'worker.py' >/dev/null 2>&1; then
      echo "Worker processes on host:"
      pgrep -af 'worker.py' || true
    fi
    echo
    ./validate.sh --quick || true
    ;;
  *)
    usage
    exit 1
    ;;
esac
