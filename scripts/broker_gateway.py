#!/usr/bin/env python3
from __future__ import annotations

import asyncio
import json
import os
import sys
import time
from typing import Any, Dict, List, Optional, Tuple

import aiohttp

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE)

from lib import db
from lib.config import discord_user_agent, load_discord_token
from lib.runtime_lock import acquire_token_lock, release_token_lock

COMPONENT_PREFIXES = ("ocb:", "occomp:", "ocm:")
EPHEMERAL_FLAG = 1 << 6
COMPONENT_KIND_NAME = {
    2: "button",
    3: "string_select",
    5: "user_select",
    6: "role_select",
    7: "mentionable_select",
    8: "channel_select",
}


async def discord_api(session: aiohttp.ClientSession, token: str, method: str, url: str, json_body=None):
    headers = {
        "Authorization": f"Bot {token}",
        "Content-Type": "application/json",
        "User-Agent": discord_user_agent(),
    }
    async with session.request(method, url, headers=headers, json=json_body) as resp:
        text = await resp.text()
        try:
            data = json.loads(text) if text else None
        except Exception:
            data = {"raw": text}
        return resp.status, data


async def interaction_callback(session, token, interaction_id, interaction_token, body):
    url = f"https://discord.com/api/v10/interactions/{interaction_id}/{interaction_token}/callback"
    return await discord_api(session, token, "POST", url, body)


async def ack_defer(session, token, interaction_id, interaction_token):
    body = {"type": 5}
    status, data = await interaction_callback(session, token, interaction_id, interaction_token, body)
    db.log_callback_attempt(interaction_id, "defer", json.dumps(body, ensure_ascii=False), json.dumps({"status": status, "data": data}, ensure_ascii=False), "success" if status in (200, 204) else "fail")
    return status, data


async def ack_ephemeral_message(session, token, interaction_id, interaction_token, content: str):
    body = {"type": 4, "data": {"content": content, "flags": EPHEMERAL_FLAG}}
    status, data = await interaction_callback(session, token, interaction_id, interaction_token, body)
    db.log_callback_attempt(interaction_id, "ephemeral", json.dumps(body, ensure_ascii=False), json.dumps({"status": status, "data": data}, ensure_ascii=False), "success" if status in (200, 204) else "fail")
    return status, data


def _modal_component_from_field(field: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    field_type = str(field.get("type") or "text").lower()
    label = str(field.get("label") or "Field")
    description = field.get("description")
    custom_id = str(field.get("custom_id") or field.get("id") or "field")[:100]
    required = bool(field.get("required", field_type == "text"))

    if field_type == "text":
        return {
            "type": 18,
            "label": label,
            "description": description,
            "component": {
                "type": 4,
                "custom_id": custom_id,
                "style": int(field.get("style", 2)),
                "required": required,
                "placeholder": field.get("placeholder", ""),
                "min_length": int(field.get("min_length", 0)),
                "max_length": int(field.get("max_length", 4000)),
                **({"value": field["value"]} if field.get("value") is not None else {}),
            },
        }

    select_type_map = {"select": 3, "string": 3, "user-select": 5, "user": 5, "role-select": 6, "role": 6, "mentionable-select": 7, "mentionable": 7, "channel-select": 8, "channel": 8}
    if field_type in select_type_map:
        component: Dict[str, Any] = {
            "type": select_type_map[field_type],
            "custom_id": custom_id,
            "placeholder": str(field.get("placeholder") or label)[:150],
            "min_values": int(field.get("min_values", 1)),
            "max_values": int(field.get("max_values", 1)),
            "required": required,
        }
        if component["type"] == 3:
            component["options"] = field.get("options") or []
        else:
            if field.get("default_values") is not None:
                component["default_values"] = field["default_values"]
            if component["type"] == 8 and field.get("channel_types") is not None:
                component["channel_types"] = field["channel_types"]
        return {"type": 18, "label": label, "description": description, "component": component}

    return None


async def ack_modal(session, token, interaction_id, interaction_token, title="Input", custom_id="ocb_modal", fields=None):
    fields = fields or [{"type": "text", "label": "Details", "custom_id": "details", "style": 2, "required": False}]
    components = []
    for field in fields[:5]:
        component = _modal_component_from_field(field)
        if component:
            components.append(component)
    body = {"type": 9, "data": {"title": title[:45], "custom_id": custom_id[:100], "components": components[:5]}}
    status, data = await interaction_callback(session, token, interaction_id, interaction_token, body)
    db.log_callback_attempt(interaction_id, "modal", json.dumps(body, ensure_ascii=False), json.dumps({"status": status, "data": data}, ensure_ascii=False), "success" if status in (200, 204) else "fail")
    return status, data


def lookup_component(message_id: Optional[str], custom_id: str) -> Optional[Dict[str, Any]]:
    conn = db.get_conn()
    cur = conn.cursor()
    row = None
    if message_id:
        cur.execute("SELECT message_id, semantic_action, payload_json, single_use, expires_at, status, component_type, label FROM components WHERE message_id=? AND custom_id=?", (message_id, custom_id))
        row = cur.fetchone()
    if not row:
        cur.execute("SELECT message_id, semantic_action, payload_json, single_use, expires_at, status, component_type, label FROM components WHERE custom_id=? ORDER BY id DESC LIMIT 1", (custom_id,))
        row = cur.fetchone()
    conn.close()
    if not row:
        return None

    payload_obj: Dict[str, Any] = {}
    try:
        payload_obj = json.loads(row["payload_json"]) if row["payload_json"] else {}
    except Exception:
        payload_obj = {}

    return {
        "message_id": row["message_id"],
        "semantic_action": row["semantic_action"],
        "payload_json": row["payload_json"],
        "payload": payload_obj,
        "single_use": int(row["single_use"] or 0),
        "expires_at": row["expires_at"],
        "status": row["status"] or "active",
        "component_type": row["component_type"] or "unknown",
        "label": row["label"] or custom_id,
    }


def is_expired(expires_at: Optional[str]) -> bool:
    if not expires_at:
        return False
    try:
        t = time.strptime(expires_at.split(".")[0], "%Y-%m-%d %H:%M:%S")
        return time.mktime(t) < time.time()
    except Exception:
        return False


def _normalize_allowed_user(value: str) -> str:
    value = value.strip()
    if value == "*":
        return value
    if value.startswith("user:"):
        return value.split(":", 1)[1]
    if value.startswith("<@") and value.endswith(">"):
        return value[2:-1].lstrip("!")
    return value


def is_user_allowed(user_id: str, payload: Dict[str, Any]) -> bool:
    allowed = payload.get("allowed_users") or payload.get("allowedUsers")
    if not allowed:
        return True
    normalized = {_normalize_allowed_user(str(v)) for v in allowed}
    return "*" in normalized or user_id in normalized


def claim_component(message_id: str, custom_id: str, single_use: int, interaction_id: str) -> Tuple[bool, str]:
    conn = db.get_conn()
    cur = conn.cursor()
    try:
        cur.execute("BEGIN IMMEDIATE")
        row = cur.execute("SELECT status FROM components WHERE message_id=? AND custom_id=? LIMIT 1", (message_id, custom_id)).fetchone()
        if not row:
            conn.commit()
            return False, "missing-component"
        if row["status"] != "active":
            conn.commit()
            return False, f"blocked:{row['status']}"
        if single_use:
            cur.execute(
                "INSERT OR IGNORE INTO single_use_claims(message_id, custom_id, first_interaction_id) VALUES(?,?,?)",
                (message_id, custom_id, interaction_id),
            )
            if cur.rowcount != 1:
                conn.commit()
                return False, "blocked:single_use"
            cur.execute("UPDATE components SET status='used' WHERE message_id=? AND custom_id=?", (message_id, custom_id))
        conn.commit()
        return True, "claimed"
    except Exception:
        try:
            conn.rollback()
        except Exception:
            pass
        return False, "claim-error"
    finally:
        conn.close()


def _flatten_modal_components(nodes: Any, out: Optional[List[Dict[str, Any]]] = None) -> List[Dict[str, Any]]:
    if out is None:
        out = []
    if isinstance(nodes, list):
        for item in nodes:
            _flatten_modal_components(item, out)
        return out
    if not isinstance(nodes, dict):
        return out

    nested = nodes.get("component") if isinstance(nodes.get("component"), dict) else None
    if nested and nested.get("custom_id"):
        entry = {
            "custom_id": nested.get("custom_id"),
            "type": nested.get("type"),
        }
        if nested.get("value") is not None:
            entry["value"] = nested.get("value")
        if nested.get("values") is not None:
            entry["values"] = nested.get("values")
        out.append(entry)
    elif nodes.get("custom_id") and nodes.get("type") not in {18}:
        entry = {
            "custom_id": nodes.get("custom_id"),
            "type": nodes.get("type"),
        }
        if nodes.get("value") is not None:
            entry["value"] = nodes.get("value")
        if nodes.get("values") is not None:
            entry["values"] = nodes.get("values")
        out.append(entry)

    if isinstance(nodes.get("components"), list):
        _flatten_modal_components(nodes["components"], out)
    return out


def _enrich_payload_for_enqueue(info: Dict[str, Any], payload: dict) -> dict:
    enriched = dict(payload)
    if payload.get("type") == 3:
        data = payload.get("data") or {}
        enriched["bridge_component"] = {
            "interaction_type": "message_component",
            "component_type": data.get("component_type"),
            "component_kind": COMPONENT_KIND_NAME.get(int(data.get("component_type") or 0), info.get("component_type") or "unknown"),
            "custom_id": data.get("custom_id"),
            "values": data.get("values") or [],
            "resolved": data.get("resolved") or payload.get("resolved") or {},
            "label": info.get("label"),
        }
    elif payload.get("type") == 5:
        data = payload.get("data") or {}
        enriched["bridge_component"] = {
            "interaction_type": "modal_submit",
            "custom_id": data.get("custom_id"),
            "fields": _flatten_modal_components(data.get("components") or []),
            "resolved": data.get("resolved") or payload.get("resolved") or {},
            "label": info.get("label"),
        }
    return enriched


def _try_local_result(info: Dict[str, Any], payload: dict) -> Optional[str]:
    payload_obj = info.get("payload") or {}
    target = str(payload_obj.get("target") or info.get("semantic_action") or "").strip()
    args = payload_obj.get("args") if isinstance(payload_obj.get("args"), dict) else {}
    bridge_component = (payload.get("bridge_component") or {}) if isinstance(payload, dict) else {}

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


async def handle_message_component(session: aiohttp.ClientSession, token: str, payload: dict) -> None:
    interaction_id = str(payload.get("id"))
    interaction_token = payload.get("token")
    user_id = str((payload.get("member") or {}).get("user", {}).get("id") or (payload.get("user") or {}).get("id") or "")
    channel_id = str(payload.get("channel_id") or "")
    message_id = str((payload.get("message") or {}).get("id") or "")
    data_obj = payload.get("data") or {}
    custom_id = data_obj.get("custom_id")

    if not custom_id or not custom_id.startswith(COMPONENT_PREFIXES):
        return

    info = lookup_component(message_id or None, custom_id)
    raw = json.dumps(_enrich_payload_for_enqueue(info or {}, payload), ensure_ascii=False)
    db.upsert_interaction(interaction_id, message_id or (info or {}).get("message_id") or "", custom_id, user_id, raw, channel_id=channel_id)

    if not info:
        await ack_ephemeral_message(session, token, interaction_id, interaction_token, "This action is no longer available.")
        db.mark_acked(interaction_id)
        db.set_failed(interaction_id, "missing-component-record")
        return

    message_id = message_id or str(info.get("message_id") or "")
    if not message_id:
        await ack_ephemeral_message(session, token, interaction_id, interaction_token, "This action is no longer available.")
        db.mark_acked(interaction_id)
        db.set_failed(interaction_id, "missing_message_id")
        return

    if not is_user_allowed(user_id, info["payload"]):
        await ack_ephemeral_message(session, token, interaction_id, interaction_token, "You are not allowed to use this component.")
        db.mark_acked(interaction_id)
        db.set_done(interaction_id, note="blocked:not-allowed")
        return

    if is_expired(info.get("expires_at")):
        await ack_ephemeral_message(session, token, interaction_id, interaction_token, "This action has expired.")
        db.mark_acked(interaction_id)
        db.set_done(interaction_id, note="blocked:expired")
        return

    claimed, reason = claim_component(message_id, custom_id, info.get("single_use", 1), interaction_id)
    if not claimed:
        await ack_ephemeral_message(session, token, interaction_id, interaction_token, "This action was already used.")
        db.mark_acked(interaction_id)
        db.set_done(interaction_id, note=reason)
        return

    if info.get("component_type") == "modal_trigger":
        modal = (info.get("payload") or {}).get("modal") or {}
        status, _ = await ack_modal(
            session,
            token,
            interaction_id,
            interaction_token,
            title=str(modal.get("title") or "Form"),
            custom_id=str(modal.get("custom_id") or f"ocm:{custom_id}"),
            fields=list(modal.get("fields") or []),
        )
        db.mark_acked(interaction_id)
        if status in (200, 204):
            db.enqueue_normalized(interaction_id, "modal-opened")
            db.set_done(interaction_id, note="modal-opened")
        else:
            db.set_failed(interaction_id, f"modal-open-failed:{status}")
        return

    local_result = _try_local_result(info, json.loads(raw))
    if local_result is not None:
        status, _ = await ack_ephemeral_message(session, token, interaction_id, interaction_token, local_result)
        db.mark_acked(interaction_id)
        if status in (200, 204):
            db.set_done(interaction_id, note="local-dispatch")
        else:
            db.set_failed(interaction_id, f"local-ephemeral-failed:{status}")
        return

    status, _ = await ack_defer(session, token, interaction_id, interaction_token)
    db.mark_acked(interaction_id)
    if status in (200, 204):
        db.enqueue_normalized(interaction_id, "queued")
    else:
        db.set_failed(interaction_id, f"defer-failed:{status}")


async def handle_modal_submit(session: aiohttp.ClientSession, token: str, payload: dict) -> None:
    interaction_id = str(payload.get("id"))
    interaction_token = payload.get("token")
    user_id = str((payload.get("member") or {}).get("user", {}).get("id") or (payload.get("user") or {}).get("id") or "")
    channel_id = str(payload.get("channel_id") or "")
    data_obj = payload.get("data") or {}
    custom_id = str(data_obj.get("custom_id") or "")
    message_id = str((payload.get("message") or {}).get("id") or "")

    if not custom_id.startswith("ocm:"):
        return

    info = lookup_component(message_id or None, custom_id)
    raw = json.dumps(_enrich_payload_for_enqueue(info or {}, payload), ensure_ascii=False)
    db.upsert_interaction(interaction_id, message_id or (info or {}).get("message_id") or "", custom_id, user_id, raw, channel_id=channel_id)

    if not info:
        await ack_ephemeral_message(session, token, interaction_id, interaction_token, "This form is no longer available.")
        db.mark_acked(interaction_id)
        db.set_failed(interaction_id, "missing-modal-record")
        return

    if not is_user_allowed(user_id, info["payload"]):
        await ack_ephemeral_message(session, token, interaction_id, interaction_token, "You are not allowed to use this form.")
        db.mark_acked(interaction_id)
        db.set_done(interaction_id, note="blocked:not-allowed")
        return

    if is_expired(info.get("expires_at")):
        await ack_ephemeral_message(session, token, interaction_id, interaction_token, "This form has expired.")
        db.mark_acked(interaction_id)
        db.set_done(interaction_id, note="blocked:expired")
        return

    message_id = message_id or str(info.get("message_id") or "")
    if not message_id:
        await ack_ephemeral_message(session, token, interaction_id, interaction_token, "This form is no longer available.")
        db.mark_acked(interaction_id)
        db.set_failed(interaction_id, "missing_message_id")
        return

    claimed, reason = claim_component(message_id, custom_id, info.get("single_use", 1), interaction_id)
    if not claimed:
        await ack_ephemeral_message(session, token, interaction_id, interaction_token, "This form was already submitted.")
        db.mark_acked(interaction_id)
        db.set_done(interaction_id, note=reason)
        return

    # Stability-first modal submit strategy:
    # do not send an additional interaction-native callback here.
    # Persist and hand off to the worker/downstream path instead.
    db.mark_acked(interaction_id)
    db.enqueue_normalized(interaction_id, "queued")


async def run_once_gateway() -> None:
    token = load_discord_token()
    if not token:
        raise SystemExit("No Discord token found in config or DISCORD_BOT_TOKEN")
    db.init_db()

    timeout = aiohttp.ClientTimeout(total=None, sock_connect=30, sock_read=None)
    async with aiohttp.ClientSession(timeout=timeout) as session:
        st, data = await discord_api(session, token, "GET", "https://discord.com/api/v10/gateway/bot")
        if st != 200:
            raise RuntimeError(f"gateway/bot failed: {st} {data}")

        ws_url = f"{data['url']}/?v=10&encoding=json"
        async with session.ws_connect(ws_url, heartbeat=30) as ws:
            hello = await ws.receive_json()
            hb_interval = hello["d"]["heartbeat_interval"] / 1000.0

            async def heartbeat_loop():
                while True:
                    await asyncio.sleep(hb_interval)
                    await ws.send_json({"op": 1, "d": None})

            hb_task = asyncio.create_task(heartbeat_loop())
            try:
                await ws.send_json(
                    {
                        "op": 2,
                        "d": {
                            "token": token,
                            "intents": 0,
                            "properties": {"$os": "linux", "$browser": "discord-component-v2", "$device": "discord-component-v2"},
                        },
                    }
                )

                async for msg in ws:
                    if msg.type == aiohttp.WSMsgType.TEXT:
                        ev = json.loads(msg.data)
                        if ev.get("op") == 7:
                            raise RuntimeError("Discord requested reconnect (op 7)")
                        if ev.get("op") == 9:
                            raise RuntimeError("Discord invalidated the session (op 9)")
                        if ev.get("t") == "INTERACTION_CREATE":
                            body = ev.get("d") or {}
                            interaction_type = int(body.get("type") or 0)
                            if interaction_type == 3:
                                await handle_message_component(session, token, body)
                            elif interaction_type == 5:
                                await handle_modal_submit(session, token, body)
                    elif msg.type in (aiohttp.WSMsgType.ERROR, aiohttp.WSMsgType.CLOSED, aiohttp.WSMsgType.CLOSE):
                        raise RuntimeError(f"gateway websocket closed: type={msg.type} data={getattr(msg, 'data', None)}")
            finally:
                hb_task.cancel()
                with contextlib.suppress(Exception):
                    await hb_task


async def run_forever() -> None:
    backoff = 2
    while True:
        try:
            await run_once_gateway()
            backoff = 2
        except asyncio.CancelledError:
            raise
        except Exception as e:
            print(f"[broker] reconnecting after error: {e}", file=sys.stderr, flush=True)
            await asyncio.sleep(backoff)
            backoff = min(backoff * 2, 30)


if __name__ == "__main__":
    import contextlib

    token = load_discord_token()
    if not token:
        raise SystemExit("No Discord token found in config or DISCORD_BOT_TOKEN")
    ok, lock_path, existing = acquire_token_lock(token)
    if not ok:
        raise SystemExit(
            f"Another discord-component-v2 broker appears to be active for this Discord token: "
            f"workspace={existing.get('workspace')} pid={existing.get('pid')} lock={lock_path}"
        )
    try:
        asyncio.run(run_forever())
    finally:
        release_token_lock(token)
