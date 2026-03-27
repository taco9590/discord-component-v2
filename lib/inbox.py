#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import time

from lib.config import INBOX_PATH, ensure_state_dir

REQUIRED_KEYS = ("schema_v", "source", "event_type", "interaction_id")

def _normalize_record(rec: dict) -> dict:
    out = dict(rec)
    out.setdefault("schema_v", 1)
    out.setdefault("timestamp", int(time.time()))
    out.setdefault("retries", 0)
    if "customid" in out and "custom_id" not in out:
        out["custom_id"] = out.pop("customid")
    out.setdefault("message_id", out.get("message_id"))
    out.setdefault("custom_id", out.get("custom_id"))
    out.setdefault("channel_id", out.get("channel_id"))
    out.setdefault("user_id", out.get("user_id"))
    out.setdefault("payload", out.get("payload"))
    out.setdefault("cli_cmd", out.get("cli_cmd"))
    return out

def validate_record(rec: dict) -> None:
    for k in REQUIRED_KEYS:
        if k not in rec:
            raise ValueError(f"missing required inbox field: {k}")
    if rec.get("schema_v") != 1:
        raise ValueError("unsupported schema_v (expect 1)")

def append_record(rec: dict) -> str:
    rec = _normalize_record(rec)
    validate_record(rec)
    ensure_state_dir()
    line = json.dumps(rec, ensure_ascii=False)
    with open(INBOX_PATH, "a", encoding="utf-8") as f:
        f.write(line + "\n")
        f.flush()
        os.fsync(f.fileno())
    return line
