#!/usr/bin/env python3
from __future__ import annotations

import sqlite3
from pathlib import Path

from lib.config import DB_PATH, ensure_state_dir

ensure_state_dir()

def get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(str(DB_PATH), timeout=10)
    conn.row_factory = sqlite3.Row
    return conn

def ensure_migrations() -> None:
    conn = get_conn(); cur = conn.cursor()
    def ensure_col(table: str, col: str, ddl: str) -> None:
        cur.execute(f"PRAGMA table_info({table})")
        cols = [r["name"] for r in cur.fetchall()]
        if col not in cols:
            try:
                cur.execute(ddl)
            except Exception:
                pass
    ensure_col("actions", "agent_hint", "ALTER TABLE actions ADD COLUMN agent_hint TEXT")
    ensure_col("actions", "session_hint", "ALTER TABLE actions ADD COLUMN session_hint TEXT")
    ensure_col("interaction_events", "channel_id", "ALTER TABLE interaction_events ADD COLUMN channel_id TEXT")
    ensure_col("interaction_events", "followup_message_id", "ALTER TABLE interaction_events ADD COLUMN followup_message_id TEXT")
    ensure_col("single_use_claims", "custom_id", "ALTER TABLE single_use_claims ADD COLUMN custom_id TEXT")
    conn.commit(); conn.close()

def init_db() -> None:
    sqlfile = Path(__file__).resolve().parent.parent / "schema" / "init.sql"
    sql = sqlfile.read_text(encoding="utf-8")
    conn = get_conn(); conn.executescript(sql); conn.commit(); conn.close()
    ensure_migrations()

def upsert_interaction(interaction_id, message_id, custom_id, user_id, raw_json, channel_id=None):
    conn=get_conn(); cur=conn.cursor()
    cur.execute('''INSERT OR IGNORE INTO interaction_events(interaction_id,message_id,custom_id,user_id,raw_json) VALUES(?,?,?,?,?)''',
                (interaction_id,message_id,custom_id,user_id,raw_json))
    try:
        cur.execute('''UPDATE interaction_events SET message_id=COALESCE(NULLIF(?, ''), message_id), custom_id=?, user_id=COALESCE(NULLIF(?, ''), user_id), raw_json=?, channel_id=COALESCE(NULLIF(?, ''), channel_id) WHERE interaction_id=?''',
                    (message_id, custom_id, user_id, raw_json, channel_id, interaction_id))
    except Exception:
        pass
    conn.commit(); conn.close()

def enqueue_normalized(interaction_id, normalized_text):
    conn=get_conn(); cur=conn.cursor()
    cur.execute("""UPDATE interaction_events SET normalized_text=?, process_state='queued' WHERE interaction_id=?""",
                (normalized_text, interaction_id))
    conn.commit(); conn.close()

def mark_acked(interaction_id):
    conn=get_conn(); cur=conn.cursor()
    cur.execute("""UPDATE interaction_events SET acked_at=datetime('now') WHERE interaction_id=?""", (interaction_id,))
    conn.commit(); conn.close()

def set_done(interaction_id, note=None):
    conn=get_conn(); cur=conn.cursor()
    cur.execute("UPDATE interaction_events SET process_state='done', error_text=? WHERE interaction_id=?", (note, interaction_id))
    conn.commit(); conn.close()

def set_done_fallback(interaction_id, note=None):
    conn=get_conn(); cur=conn.cursor()
    cur.execute("UPDATE interaction_events SET process_state='done_fallback', error_text=? WHERE interaction_id=?", (note, interaction_id))
    conn.commit(); conn.close()

def set_failed(interaction_id, error):
    conn=get_conn(); cur=conn.cursor()
    cur.execute("UPDATE interaction_events SET process_state='failed', error_text=? WHERE interaction_id=?", (error, interaction_id))
    conn.commit(); conn.close()

def log_delivery_attempt(interaction_id, adapter, attempt_no, request_payload, response_payload, result):
    conn=get_conn(); cur=conn.cursor()
    cur.execute(
        "INSERT INTO delivery_attempts(interaction_id,adapter,attempt_no,request_payload,response_payload,result) VALUES(?,?,?,?,?,?)",
        (interaction_id, adapter, attempt_no, request_payload, response_payload, result),
    )
    conn.commit(); conn.close()
