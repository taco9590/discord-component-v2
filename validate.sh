#!/usr/bin/env bash
set -euo pipefail

MODE="full"
if [[ "${1:-}" == "--quick" ]]; then
  MODE="quick"
fi

fail=0
warn() { echo "[validate][warn] $*"; }
err() { echo "[validate][error] $*" >&2; fail=1; }
ok() { echo "[validate][ok] $*"; }

check_exists() {
  local path="$1"
  [[ -e "$path" ]] || err "Missing required path: $path"
}

echo "[validate] mode=$MODE"

for path in README.md SKILL.md install.sh manage.sh uninstall.sh validate.sh lib/config.py lib/db.py scripts/broker_gateway.py scripts/worker.py scripts/injector.py schema/init.sql requirements.txt scripts/systemd/discord-component-v2-broker.service.template scripts/systemd/discord-component-v2-worker.service.template; do
  check_exists "$path"
done

if bash -n install.sh manage.sh uninstall.sh validate.sh; then
  ok "Shell syntax"
else
  err "Shell syntax failed"
fi

pyfiles=$(find lib scripts tools -name '*.py' | tr '\n' ' ')
if python3 -m py_compile $pyfiles; then
  ok "Python syntax"
else
  err "Python syntax failed"
fi

exit_code=0
python3 - <<'PY' || exit_code=$?
import json, os, sys, tempfile
from pathlib import Path
root = Path('.')

for p in root.joinpath('examples').glob('*.json'):
    json.loads(p.read_text(encoding='utf-8'))

td = tempfile.TemporaryDirectory()
os.environ['DISCORD_COMPONENT_V2_STATE_DIR'] = td.name
sys.path.insert(0, str(root))
from lib import db
db.init_db()
conn = db.get_conn()
cur = conn.cursor()
cur.execute("SELECT name FROM sqlite_master WHERE type='table'")
names = {r[0] for r in cur.fetchall()}
required = {'messages','components','actions','interaction_events','delivery_attempts','single_use_claims'}
assert required.issubset(names), (required - names)
conn.close()

# content scan excluding this validator
bad_abs = []
bad_stale = []
for p in root.rglob('*'):
    if not p.is_file():
        continue
    if '.venv' in p.parts:
        continue
    if p.name == 'validate.sh':
        continue
    if p.suffix in {'.py','.sh','.md','.json','.txt','.template','.sql'} or p.name in {'.gitignore','requirements.txt','README.md','SKILL.md'}:
        text = p.read_text(encoding='utf-8', errors='ignore')
        if '/home/' in text or '/Users/' in text:
            bad_abs.append(str(p))

        if '__pycache__' in p.parts or p.suffix == '.pyc':
            bad_stale.append(str(p))
        if '1484475394219573348' in text or 'discord-cv2-sqlite-bridge' in text or 'cite' in text or 'filecite' in text or 'turn308978' in text:
            bad_stale.append(str(p))
assert not bad_abs, bad_abs
assert not bad_stale, bad_stale
print("python-validation-ok")
PY
if [[ "${exit_code:-0}" -eq 0 ]]; then
  ok "JSON examples, SQLite schema, and static content scan"
else
  err "JSON examples, SQLite schema, or static content scan failed"
fi

if [[ -f .venv/bin/python ]]; then
  if [[ "$MODE" == "full" ]]; then
    if ./.venv/bin/python tools/test_local_worker.py >/dev/null; then
      ok "Local smoke test"
    else
      err "Local smoke test failed"
    fi
  fi
else
  warn "Skipping local smoke test because .venv is not present"
fi

if [[ "$fail" -ne 0 ]]; then
  echo "[validate] failed"
  exit 1
fi
echo "[validate] passed"
