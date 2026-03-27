#!/usr/bin/env python3
from __future__ import annotations

import asyncio
import json
import os
import sys
import time
from typing import Any, Dict, Optional, Tuple

import aiohttp

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE)

from lib import db
from lib.config import discord_user_agent, load_discord_token
from scripts import injector

SUCCESS_TEXT = "✅ Accepted and delivered to OpenClaw."
DELAY_TEXT = "⚠️ Accepted, but delivery to OpenClaw was delayed."
FAIL_TEXT = "❌ An error occurred while processing the interaction."
DEFAULT_LOCAL_SUCCESS_TEXT = "✅ Completed."


def _load_component_payload(message_id: str, custom_id: str) -> tuple[str, Dict[str, Any]]:
    conn = db.get_conn()
    cur = conn.cursor()
    cur.execute("SELECT semantic_action, payload_json FROM components WHERE message_id=? AND custom_id=?", (message_id, custom_id))
    row = cur.fetchone()
    conn.close()
    if not row:
        return "", {}
    try:
        payload = json.loads(row["payload_json"]) if row["payload_json"] else {}
    except Exception:
        payload = {}
    return (row["semantic_action"] or ""), payload


def _load_message_summary(message_id: str) -> Optional[str]:
    conn = db.get_conn()
    cur = conn.cursor()
    cur.execute("SELECT content FROM messages WHERE message_id=?", (message_id,))
    row = cur.fetchone()
    conn.close()
    return (row["content"] if row and row["content"] else None)


def _parse_raw_json(row: Dict[str, Any]) -> Dict[str, Any]:
    try:
        return json.loads(row.get("raw_json") or "{}")
    except Exception:
        return {}


def _extract_component_context(raw_obj: Dict[str, Any]) -> Dict[str, Any]:
    return raw_obj.get("bridge_component") or {}


def build_openclaw_prompt(row: Dict[str, Any], semantic_action: str, payload_obj: Dict[str, Any]) -> str:
    raw_json_obj = _parse_raw_json(row)
    bridge_component = _extract_component_context(raw_json_obj)
    channel_id = row.get("channel_id") or str(raw_json_obj.get("channel_id") or "")
    message_id = row.get("message_id") or str((raw_json_obj.get("message") or {}).get("id") or "")
    source_summary = _load_message_summary(message_id or "")
    envelope = {
        "bridge": "discord-component-v2",
        "event": bridge_component.get("interaction_type") or payload_obj.get("event_kind") or "component.click",
        "interaction_id": row.get("interaction_id"),
        "message_id": message_id,
        "custom_id": row.get("custom_id"),
        "user_id": row.get("user_id"),
        "channel_id": channel_id,
        "semantic_action": semantic_action,
        "payload": payload_obj,
        "source_message_summary": source_summary,
        "component": bridge_component,
        "reply": {"channel": "discord", "target": f"channel:{channel_id}" if channel_id else None},
    }
    return (
        "A Discord bridge interaction was received. Perform the requested action or answer in the originating Discord channel.\n\n"
        "```json\n"
        + json.dumps(envelope, ensure_ascii=False, indent=2)
        + "\n```"
    )


def _parse_row_context(row: Dict[str, Any]) -> Tuple[Optional[dict], Optional[str], Optional[str], Optional[str]]:
    raw_json_obj = None
    app_id = interaction_token = channel_id = None
    try:
        if row.get("raw_json"):
            raw_json_obj = json.loads(row["raw_json"])
            app_id = str(raw_json_obj.get("application_id") or "") or None
            interaction_token = str(raw_json_obj.get("token") or "") or None
            channel_id = row.get("channel_id") or str(raw_json_obj.get("channel_id") or "") or None
    except Exception:
        pass
    return raw_json_obj, app_id, interaction_token, channel_id


async def _patch_original(app_id: str, interaction_token: str, patch_body: dict) -> tuple[int, Any]:
    bot_token = load_discord_token()
    if not bot_token:
        return 0, {"error": "missing bot token"}
    headers = {"Authorization": f"Bot {bot_token}", "Content-Type": "application/json", "User-Agent": discord_user_agent()}
    url = f"https://discord.com/api/v10/webhooks/{app_id}/{interaction_token}/messages/@original"
    async with aiohttp.ClientSession() as session:
        async with session.patch(url, headers=headers, json=patch_body) as resp:
            text = await resp.text()
            try:
                return resp.status, json.loads(text) if text else {}
            except Exception:
                return resp.status, {"raw": text}


async def _post_channel(channel_id: str, content: str) -> tuple[int, Any]:
    bot_token = load_discord_token()
    if not bot_token:
        return 0, {"error": "missing bot token"}
    headers = {"Authorization": f"Bot {bot_token}", "Content-Type": "application/json", "User-Agent": discord_user_agent()}
    url = f"https://discord.com/api/v10/channels/{channel_id}/messages"
    async with aiohttp.ClientSession() as session:
        async with session.post(url, headers=headers, json={"content": content}) as resp:
            text = await resp.text()
            try:
                return resp.status, json.loads(text) if text else {}
            except Exception:
                return resp.status, {"raw": text}



async def _delete_original(app_id: str, interaction_token: str) -> tuple[int, Any]:
    url = f"https://discord.com/api/v10/webhooks/{app_id}/{interaction_token}/messages/@original"
    headers = {"Content-Type": "application/json", "User-Agent": discord_user_agent()}
    async with aiohttp.ClientSession() as session:
        async with session.delete(url, headers=headers) as resp:
            text = await resp.text()
            try:
                return resp.status, json.loads(text) if text else {}
            except Exception:
                return resp.status, {"raw": text}


def _status_mode() -> str:
    return str(os.environ.get("DISCORD_COMPONENT_V2_INTERACTION_STATUS", "full")).strip().lower() or "full"


def _response_policy(payload_obj: Dict[str, Any]) -> Dict[str, Any]:
    interaction = payload_obj.get("interaction") if isinstance(payload_obj.get("interaction"), dict) else {}
    response = interaction.get("response") if isinstance(interaction.get("response"), dict) else {}
    return response


def _status_text(payload_obj: Dict[str, Any], default_text: str, *, outcome: str) -> str:
    response = _response_policy(payload_obj)
    if outcome == "success_local":
        return str(response.get("local_success_text") or response.get("success_text") or DEFAULT_LOCAL_SUCCESS_TEXT)
    if outcome == "success_transport":
        return str(response.get("transport_success_text") or response.get("success_text") or default_text)
    if outcome == "delayed":
        return str(response.get("delayed_text") or response.get("warning_text") or default_text)
    if outcome == "error":
        return str(response.get("error_text") or default_text)
    return default_text


def complete_interaction(app_id: Optional[str], interaction_token: Optional[str], channel_id: Optional[str], text: str, *, payload_obj: Optional[Dict[str, Any]] = None, outcome: str = "success_transport") -> bool:
    payload_obj = payload_obj or {}
    response = _response_policy(payload_obj)
    policy_mode = str(response.get("mode") or "").strip().lower()
    mode = policy_mode or _status_mode()
    show_success = bool(response.get("show_success", True))
    final_text = _status_text(payload_obj, text, outcome=outcome)

    if outcome in {"success_transport", "success_local"} and not show_success:
        mode = "silent"

    if mode == "silent":
        if app_id and interaction_token:
            status, _ = asyncio.run(_delete_original(app_id, interaction_token))
            if status in (200, 202, 204):
                return True
        return True

    if mode == "errors-only" and outcome in {"success_transport", "success_local"}:
        if app_id and interaction_token:
            status, _ = asyncio.run(_delete_original(app_id, interaction_token))
            if status in (200, 202, 204):
                return True
        return True

    if app_id and interaction_token:
        status, _ = asyncio.run(_patch_original(app_id, interaction_token, {"content": final_text}))
        if status in (200, 204):
            return True
    if channel_id and mode != "silent":
        status, _ = asyncio.run(_post_channel(channel_id, final_text))
        return status in (200, 201)
    return False


def try_local_dispatch(semantic_action: str, payload_obj: Dict[str, Any], row: Dict[str, Any]) -> Optional[str]:
    target = (payload_obj.get("target") or semantic_action or "").strip()
    args = payload_obj.get("args") if isinstance(payload_obj.get("args"), dict) else {}
    raw_obj = _parse_raw_json(row)
    bridge_component = _extract_component_context(raw_obj)

    if target in {"say_hello", "demo.say_hello"}:
        return args.get("text") or "Hello."
    if target in {"discord.reply_text", "reply_text"}:
        return args.get("text") or "Done."
    if target in {"demo.pick_option"}:
        values = bridge_component.get("values") or []
        return f"You selected: {', '.join(values) if values else 'nothing'}"
    if target in {"demo.submit_details"}:
        fields = bridge_component.get("fields") or []
        rendered = []
        for field in fields:
            if field.get("value") is not None:
                rendered.append(f"{field.get('custom_id')}: {field.get('value')}")
            elif field.get("values") is not None:
                rendered.append(f"{field.get('custom_id')}: {', '.join(field.get('values') or [])}")
        return "Submitted form:\n" + ("\n".join(rendered) if rendered else "(empty)")
    return None


def claim_one_queued() -> Optional[Dict[str, Any]]:
    conn = db.get_conn()
    cur = conn.cursor()
    cur.execute("BEGIN IMMEDIATE")
    row = cur.execute("SELECT interaction_id FROM interaction_events WHERE process_state='queued' ORDER BY created_at LIMIT 1").fetchone()
    if not row:
        conn.commit()
        conn.close()
        return None
    iid = row[0]
    cur.execute("UPDATE interaction_events SET process_state='processing', acked_at=DATETIME('now') WHERE interaction_id=? AND process_state='queued'", (iid,))
    conn.commit()
    conn.close()
    conn = db.get_conn()
    cur = conn.cursor()
    cur.execute("SELECT * FROM interaction_events WHERE interaction_id=?", (iid,))
    row = cur.fetchone()
    conn.close()
    return dict(row) if row else None


def process_one(row: Dict[str, Any]) -> None:
    iid = row.get("interaction_id")
    if not iid or not row.get("custom_id"):
        db.set_failed(iid or "UNKNOWN", "missing_custom_id")
        return

    raw_obj, app_id, interaction_token, channel_id = _parse_row_context(row)
    message_id = row.get("message_id") or str((raw_obj or {}).get("message", {}).get("id") or "")
    semantic_action, payload_obj = _load_component_payload(message_id, row["custom_id"]) if message_id else ("", {})
    if not semantic_action and not payload_obj and row.get("custom_id"):
        # Modal submit fallback: lookup by custom_id only was already embedded in broker, so pull directly from raw payload copy.
        conn = db.get_conn()
        cur = conn.cursor()
        cur.execute("SELECT semantic_action, payload_json FROM components WHERE custom_id=? ORDER BY id DESC LIMIT 1", (row["custom_id"],))
        found = cur.fetchone()
        conn.close()
        if found:
            semantic_action = found["semantic_action"] or ""
            try:
                payload_obj = json.loads(found["payload_json"]) if found["payload_json"] else {}
            except Exception:
                payload_obj = {}

    local = try_local_dispatch(semantic_action, payload_obj, row)
    if local is not None:
        ok = complete_interaction(app_id, interaction_token, channel_id, local, payload_obj=payload_obj, outcome="success_local")
        if ok:
            db.set_done(iid, note="local-dispatch")
        else:
            db.set_done_fallback(iid, note="local-dispatch-fallback-failed")
        return

    normalized = build_openclaw_prompt(row, semantic_action, payload_obj)
    res = injector.inject(iid, normalized)
    if res.get("ok"):
        complete_interaction(app_id, interaction_token, channel_id, SUCCESS_TEXT, payload_obj=payload_obj, outcome="success_transport")
        db.set_done(iid, note="delivered-to-openclaw")
        return
    complete_interaction(app_id, interaction_token, channel_id, DELAY_TEXT, payload_obj=payload_obj, outcome="delayed")
    db.set_done_fallback(iid, note=res.get("mode") or "inject-fallback")


def run_once() -> bool:
    row = claim_one_queued()
    if not row:
        return False
    try:
        process_one(row)
    except Exception as e:
        try:
            _, app_id, interaction_token, channel_id = _parse_row_context(row)
            complete_interaction(app_id, interaction_token, channel_id, FAIL_TEXT)
        except Exception:
            pass
        db.set_failed(row.get("interaction_id", "UNKNOWN"), str(e))
    return True


def run_loop(sleep_s: float = 0.5) -> None:
    while True:
        if not run_once():
            time.sleep(sleep_s)


if __name__ == "__main__":
    run_loop()
