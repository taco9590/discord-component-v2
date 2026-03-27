#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import sys
import tempfile
import time
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE))

# Use a temporary state directory so the smoke test does not pollute production state.
tmpdir = tempfile.TemporaryDirectory()
os.environ["DISCORD_COMPONENT_V2_STATE_DIR"] = tmpdir.name

from lib import db
from scripts import worker

def main() -> int:
    db.init_db()
    iid = f"local-worker-{int(time.time())}"
    message_id = f"msg-{int(time.time())}"
    custom_id = "ocb:test:say_hello"
    payload = {"application_id": "app", "token": "tok", "channel_id": "chan"}
    conn = db.get_conn()
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO interaction_events(interaction_id, message_id, custom_id, user_id, raw_json, channel_id, process_state) VALUES(?,?,?,?,?,?,?)",
        (iid, message_id, custom_id, "user", json.dumps(payload), "chan", "queued"),
    )
    cur.execute(
        "INSERT INTO components(message_id, custom_id, component_type, label, semantic_action, payload_json, single_use, status) VALUES(?,?,?,?,?,?,?,?)",
        (message_id, custom_id, "button", "Say hello", "say_hello", json.dumps({"kind": "dispatch", "target": "say_hello", "args": {"text": "Hello."}}), 1, "active"),
    )
    conn.commit()
    conn.close()

    worker.run_once()

    conn = db.get_conn()
    cur = conn.cursor()
    cur.execute("SELECT process_state FROM interaction_events WHERE interaction_id=?", (iid,))
    row = cur.fetchone()
    conn.close()
    print(dict(row) if row else None)
    return 0 if row and row["process_state"] in {"done", "done_fallback", "failed"} else 1

if __name__ == "__main__":
    raise SystemExit(main())
