#!/usr/bin/env python3
from __future__ import annotations

import json
import subprocess
import sys
import os

BASE = os.path.dirname(os.path.dirname(__file__))
sys.path.insert(0, BASE)

from lib import db
from lib import inbox as inbox_lib
from lib.config import openclaw_binary


def inject(interaction_id: str, normalized_text: str) -> dict:
    channel_id = user_id = message_id = custom_id = None
    try:
        conn = db.get_conn()
        cur = conn.cursor()
        cur.execute("SELECT channel_id, user_id, message_id, custom_id FROM interaction_events WHERE interaction_id=?", (interaction_id,))
        row = cur.fetchone()
        conn.close()
        if row:
            channel_id, user_id, message_id, custom_id = row[0], row[1], row[2], row[3]
    except Exception:
        pass

    hint_meta = {}
    try:
        parsed = json.loads(normalized_text.split("```json", 1)[1].rsplit("```", 1)[0]) if "```json" in normalized_text else {}
        hints = parsed.get("hints") if isinstance(parsed.get("hints"), dict) else {}
        hint_meta = {
            "agent_hint": hints.get("agent_hint") or hints.get("agentHint"),
            "session_hint": hints.get("session_hint") or hints.get("sessionHint"),
            "thread_hint": hints.get("thread_hint") or hints.get("threadHint"),
        }
    except Exception:
        hint_meta = {}

    if not channel_id:
        inbox_lib.append_record(
            {
                "schema_v": 1,
                "source": "injector",
                "event_type": "component.click",
                "interaction_id": interaction_id,
                "message_id": message_id,
                "custom_id": custom_id,
                "user_id": user_id,
                "channel_id": channel_id,
                "reason": "no-channel-target",
                "text": normalized_text,
                "hints": hint_meta,
            }
        )
        db.set_done_fallback(interaction_id, note="no-channel-target")
        return {"ok": False, "mode": "inbox", "error": "no-channel-target"}

    target = f"channel:{channel_id}"
    cmd = [
        openclaw_binary(),
        "agent",
    ]
    if hint_meta.get("agent_hint"):
        cmd.extend(["--agent", str(hint_meta["agent_hint"])])
    session_hint = str(hint_meta.get("session_hint") or "").strip()
    if session_hint:
        if session_hint.startswith("session:"):
            session_hint = session_hint.split(":", 1)[1]
        cmd.extend(["--session-id", session_hint])
    else:
        cmd.extend(["--to", target])
    cmd.extend([
        "--message",
        normalized_text,
        "--deliver",
        "--reply-channel",
        "discord",
        "--reply-to",
        target,
    ])
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=int(os.environ.get("OPENCLAW_INJECT_FAST_TIMEOUT", "15")))
        db.log_delivery_attempt(
            interaction_id,
            "cli",
            1,
            json.dumps({"cmd": cmd, "text": normalized_text, "hints": hint_meta}, ensure_ascii=False),
            json.dumps({"rc": proc.returncode, "stdout": proc.stdout, "stderr": proc.stderr}, ensure_ascii=False),
            "success" if proc.returncode == 0 else "fail",
        )
        if proc.returncode == 0:
            db.set_done(interaction_id, note="injected-cli")
            return {"ok": True, "mode": "cli_success", "stdout": proc.stdout, "stderr": proc.stderr}
        raise RuntimeError(f"cli failed rc={proc.returncode}")
    except Exception as e:
        inbox_lib.append_record(
            {
                "schema_v": 1,
                "source": "injector",
                "event_type": "component.click",
                "interaction_id": interaction_id,
                "message_id": message_id,
                "custom_id": custom_id,
                "user_id": user_id,
                "channel_id": channel_id,
                "reason": "cli-failed",
                "cli_cmd": cmd,
                "text": normalized_text,
                "hints": hint_meta,
                "error": str(e),
            }
        )
        db.set_done_fallback(interaction_id, note="cli-failed")
        return {"ok": False, "mode": "inbox", "error": str(e)}


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("usage: injector.py <interaction_id> <normalized_text>")
        raise SystemExit(1)
    print(inject(sys.argv[1], sys.argv[2]))
