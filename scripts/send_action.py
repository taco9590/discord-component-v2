#!/usr/bin/env python3
from __future__ import annotations

import copy
import json
import os
import sys
import time
import urllib.error
import urllib.request
from typing import Any, Dict, List, Optional, Tuple

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE)

from lib import db
from lib.config import discord_user_agent, load_discord_token

USER_AGENT = discord_user_agent()
V2_FLAG = 1 << 15

BUTTON_STYLE_MAP = {
    "primary": 1,
    "secondary": 2,
    "success": 3,
    "danger": 4,
    "link": 5,
    "premium": 6,
}

SELECT_TYPE_MAP = {
    "string": 3,
    "user": 5,
    "role": 6,
    "mentionable": 7,
    "channel": 8,
}


def discord_request(method: str, endpoint: str, body: Optional[dict] = None) -> tuple[int, dict]:
    token = load_discord_token()
    if not token:
        return 401, {"error": "No Discord token configured"}
    url = f"https://discord.com/api/v10{endpoint}"
    headers = {
        "Authorization": f"Bot {token}",
        "Content-Type": "application/json",
        "User-Agent": USER_AGENT,
    }
    data = json.dumps(body, ensure_ascii=False).encode("utf-8") if body is not None else None
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            text = resp.read().decode("utf-8")
            return resp.status, json.loads(text) if text else {}
    except urllib.error.HTTPError as e:
        raw = e.read().decode("utf-8")
        try:
            return e.code, json.loads(raw)
        except Exception:
            return e.code, {"raw": raw}
    except Exception as e:
        return 500, {"error": str(e)}


def _make_card_id() -> str:
    return f"card_{int(time.time() * 1000)}"


def _discord_error_hint(status: int, resp: dict) -> Optional[str]:
    code = resp.get("code") if isinstance(resp, dict) else None
    if status == 400:
        return "Discord rejected the payload. Check component field limits, types, and V2-only rules."
    if status == 401:
        return "Discord bot token is missing or invalid."
    if status == 403 and code in {1010, 40333}:
        return "Cloudflare blocked the request. Use a valid DiscordBot-style User-Agent and retry."
    if status == 403:
        return "Discord denied access. Check bot permissions, channel access, and token/account alignment."
    if status == 404:
        return "Target channel or resource was not found. Verify the channel ID and bot access."
    if status == 429:
        return "Discord rate limited the request. Retry after the server's reset window."
    return None


def _normalize_allowed_users(value: Any) -> List[str]:
    if value is None:
        return []
    if isinstance(value, (str, int)):
        return [str(value)]
    if isinstance(value, list):
        return [str(v) for v in value if str(v).strip()]
    return []


def _normalize_single_use(raw: Dict[str, Any], default_reusable: bool) -> int:
    if raw.get("reusable") is True:
        return 0
    if raw.get("reusable") is False:
        return 1
    if "single_use" in raw and raw.get("single_use") is not None:
        return 1 if int(raw.get("single_use", 1)) else 0
    return 0 if default_reusable else 1


def _style_value(style: Any) -> int:
    if isinstance(style, int):
        return style
    return BUTTON_STYLE_MAP.get(str(style or "primary").lower(), 1)


def _summary_from_spec(spec: Dict[str, Any]) -> str:
    parts: List[str] = []
    if spec.get("content"):
        parts.append(str(spec["content"]))
    if spec.get("text"):
        parts.append(str(spec["text"]))
    for block in spec.get("blocks") or []:
        if not isinstance(block, dict):
            continue
        if block.get("type") == "text" and block.get("text"):
            parts.append(str(block["text"]))
        if block.get("type") == "section":
            for item in block.get("components") or []:
                if isinstance(item, dict) and item.get("type") == "text" and item.get("text"):
                    parts.append(str(item["text"]))
    return "\n".join(p for p in parts if p).strip()


def _payload_base(action_data: Optional[dict], raw: Dict[str, Any], event_kind: str) -> Dict[str, Any]:
    payload = copy.deepcopy(action_data or {})
    per_control = copy.deepcopy(raw.get("payload") or {})
    payload.update(per_control)
    payload.setdefault("kind", payload.get("kind") or "dispatch")
    target = raw.get("target") or raw.get("action") or payload.get("target") or raw.get("label") or raw.get("placeholder")
    if target:
        payload["target"] = target
    base_args = payload.get("args") if isinstance(payload.get("args"), dict) else {}
    raw_args = raw.get("args") if isinstance(raw.get("args"), dict) else {}
    payload["args"] = {**base_args, **raw_args}
    allowed_users = _normalize_allowed_users(raw.get("allowed_users") or raw.get("allowedUsers") or payload.get("allowed_users"))
    if allowed_users:
        payload["allowed_users"] = allowed_users
    payload["event_kind"] = event_kind
    return payload


class RegistryEntry(dict):
    pass


def _button_component(card_id: str, idx: int, raw: Dict[str, Any], action_data: Optional[dict], default_reusable: bool) -> Tuple[Dict[str, Any], Optional[RegistryEntry]]:
    label = str(raw.get("label") or f"Button {idx + 1}")[:80]
    style = _style_value(raw.get("style"))
    if style == 5 or raw.get("url"):
        component = {"type": 2, "label": label, "style": 5, "url": raw.get("url") or "https://discord.com"}
        return component, None

    control_token = raw.get("id") or raw.get("key") or raw.get("action") or f"btn_{idx}"
    control_token = str(control_token).replace(" ", "_")[:48]
    custom_id = f"ocb:{card_id}:{control_token}"
    payload = _payload_base(action_data, raw, event_kind="button")
    component = {"type": 2, "style": style, "label": label, "custom_id": custom_id}
    if raw.get("emoji"):
        component["emoji"] = raw["emoji"]
    if raw.get("disabled"):
        component["disabled"] = True

    entry = RegistryEntry(
        custom_id=custom_id,
        component_type="button",
        label=label,
        semantic_action=str(payload.get("target") or label),
        payload_json=json.dumps(payload, ensure_ascii=False),
        single_use=_normalize_single_use(raw, default_reusable),
        expires_at=raw.get("expires_at") or raw.get("expiresAt"),
        agent_hint=payload.get("agent_hint") or payload.get("agentHint"),
        session_hint=payload.get("session_hint") or payload.get("sessionHint"),
        thread_hint=payload.get("thread_hint") or payload.get("threadHint"),
    )
    return component, entry


def _select_component(card_id: str, idx: int, raw: Dict[str, Any], action_data: Optional[dict], default_reusable: bool) -> Tuple[Dict[str, Any], RegistryEntry]:
    select_type_name = str(raw.get("type") or "string").lower()
    select_type = SELECT_TYPE_MAP.get(select_type_name)
    if not select_type:
        raise ValueError(f"Unsupported select type: {select_type_name}")

    control_token = raw.get("id") or raw.get("key") or raw.get("action") or f"sel_{idx}"
    control_token = str(control_token).replace(" ", "_")[:48]
    custom_id = f"ocb:{card_id}:{control_token}"
    payload = _payload_base(action_data, raw, event_kind="select")

    component: Dict[str, Any] = {
        "type": select_type,
        "custom_id": custom_id,
        "placeholder": str(raw.get("placeholder") or "Choose...")[:150],
        "min_values": int(raw.get("min_values", raw.get("minValues", 1))),
        "max_values": int(raw.get("max_values", raw.get("maxValues", 1))),
        "disabled": bool(raw.get("disabled", False)),
    }
    if select_type == 3:
        component["options"] = copy.deepcopy(raw.get("options") or [])[:25]
    else:
        if raw.get("default_values") is not None:
            component["default_values"] = copy.deepcopy(raw["default_values"])
        if select_type == 8 and raw.get("channel_types") is not None:
            component["channel_types"] = copy.deepcopy(raw["channel_types"])

    entry = RegistryEntry(
        custom_id=custom_id,
        component_type=f"{select_type_name}_select",
        label=str(raw.get("placeholder") or raw.get("label") or custom_id),
        semantic_action=str(payload.get("target") or custom_id),
        payload_json=json.dumps(payload, ensure_ascii=False),
        single_use=_normalize_single_use(raw, default_reusable),
        expires_at=raw.get("expires_at") or raw.get("expiresAt"),
        agent_hint=payload.get("agent_hint") or payload.get("agentHint"),
        session_hint=payload.get("session_hint") or payload.get("sessionHint"),
        thread_hint=payload.get("thread_hint") or payload.get("threadHint"),
    )
    return component, entry


def _modal_fields_from_spec(fields: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for idx, raw in enumerate(fields[:5]):
        field_type = str(raw.get("type") or "text").lower()
        label = str(raw.get("label") or f"Field {idx + 1}")
        custom_id = str(raw.get("custom_id") or raw.get("id") or f"field_{idx + 1}")[:100]
        entry: Dict[str, Any] = {
            "type": field_type,
            "label": label,
            "custom_id": custom_id,
            "required": bool(raw.get("required", field_type == "text")),
        }
        for key in (
            "description",
            "placeholder",
            "style",
            "min_length",
            "max_length",
            "min_values",
            "max_values",
            "default_values",
            "channel_types",
            "options",
            "value",
        ):
            if raw.get(key) is not None:
                entry[key] = copy.deepcopy(raw[key])
        out.append(entry)
    return out


def _modal_trigger_component(card_id: str, modal_spec: Dict[str, Any], action_data: Optional[dict], default_reusable: bool) -> Tuple[Dict[str, Any], RegistryEntry, RegistryEntry]:
    label = str(modal_spec.get("triggerLabel") or modal_spec.get("trigger_label") or "Open form")[:80]
    style = _style_value(modal_spec.get("triggerStyle") or modal_spec.get("trigger_style") or "primary")
    control_token = str(modal_spec.get("id") or modal_spec.get("action") or "modal").replace(" ", "_")[:40]
    trigger_custom_id = f"ocb:{card_id}:modal:{control_token}"
    submit_custom_id = f"ocm:{card_id}:{control_token}"

    modal_payload = _payload_base(action_data, modal_spec, event_kind="modal_submit")
    modal_payload["modal"] = {
        "title": str(modal_spec.get("title") or "Form")[:45],
        "custom_id": submit_custom_id,
        "fields": _modal_fields_from_spec(list(modal_spec.get("fields") or [])),
    }

    trigger_single_use = 0 if modal_spec.get("trigger_reusable") is True else _normalize_single_use(
        {**modal_spec, "single_use": modal_spec.get("trigger_single_use", 0 if modal_spec.get("trigger_reusable") is True else modal_spec.get("single_use"))},
        default_reusable=True,
    )
    submit_single_use = _normalize_single_use(
        {**modal_spec, "single_use": modal_spec.get("submit_single_use", modal_spec.get("single_use", 1))},
        default_reusable=default_reusable,
    )

    trigger_component = {"type": 2, "style": style, "label": label, "custom_id": trigger_custom_id}
    trigger_entry = RegistryEntry(
        custom_id=trigger_custom_id,
        component_type="modal_trigger",
        label=label,
        semantic_action=str(modal_payload.get("target") or "modal.open"),
        payload_json=json.dumps(modal_payload, ensure_ascii=False),
        single_use=trigger_single_use,
        expires_at=modal_spec.get("expires_at") or modal_spec.get("expiresAt"),
        agent_hint=modal_payload.get("agent_hint") or modal_payload.get("agentHint"),
        session_hint=modal_payload.get("session_hint") or modal_payload.get("sessionHint"),
        thread_hint=modal_payload.get("thread_hint") or modal_payload.get("threadHint"),
    )
    submit_entry = RegistryEntry(
        custom_id=submit_custom_id,
        component_type="modal_submit",
        label=str(modal_spec.get("title") or "Form"),
        semantic_action=str(modal_payload.get("target") or "modal.submit"),
        payload_json=json.dumps(modal_payload, ensure_ascii=False),
        single_use=submit_single_use,
        expires_at=modal_spec.get("expires_at") or modal_spec.get("expiresAt"),
        agent_hint=modal_payload.get("agent_hint") or modal_payload.get("agentHint"),
        session_hint=modal_payload.get("session_hint") or modal_payload.get("sessionHint"),
        thread_hint=modal_payload.get("thread_hint") or modal_payload.get("threadHint"),
    )
    return trigger_component, trigger_entry, submit_entry


def _build_v2_from_rich_spec(spec: Dict[str, Any]) -> Tuple[List[Dict[str, Any]], List[RegistryEntry]]:
    card_id = spec.get("card_id") or _make_card_id()
    components: List[Dict[str, Any]] = []
    registry: List[RegistryEntry] = []
    default_reusable = bool(spec.get("reusable", False))
    action_data = spec.get("action_data") if isinstance(spec.get("action_data"), dict) else None

    if spec.get("text"):
        components.append({"type": 10, "content": str(spec["text"])})
    elif spec.get("content"):
        components.append({"type": 10, "content": str(spec["content"])})

    for idx, raw_block in enumerate(spec.get("blocks") or []):
        if not isinstance(raw_block, dict):
            continue
        block_type = str(raw_block.get("type") or "").lower()
        if block_type == "text":
            components.append({"type": 10, "content": str(raw_block.get("text") or "")})
            continue
        if block_type == "separator":
            components.append({"type": 14})
            continue
        if block_type == "actions":
            buttons = raw_block.get("buttons") or raw_block.get("components") or []
            select = raw_block.get("select")
            if buttons:
                row: Dict[str, Any] = {"type": 1, "components": []}
                for btn_idx, raw_btn in enumerate(list(buttons)[:5]):
                    component, entry = _button_component(card_id, idx * 10 + btn_idx, raw_btn, action_data, default_reusable)
                    row["components"].append(component)
                    if entry:
                        registry.append(entry)
                if row["components"]:
                    components.append(row)
                continue
            if isinstance(select, dict):
                component, entry = _select_component(card_id, idx, select, action_data, default_reusable)
                components.append({"type": 1, "components": [component]})
                registry.append(entry)
                continue
            continue
        if block_type == "section":
            section_components: List[Dict[str, Any]] = []
            for item in raw_block.get("components") or []:
                if isinstance(item, dict) and item.get("type") == "text":
                    section_components.append({"type": 10, "content": str(item.get("text") or "")})
            section: Dict[str, Any] = {"type": 9, "components": section_components[:3] or [{"type": 10, "content": ""}]}
            accessory = raw_block.get("accessory")
            if isinstance(accessory, dict):
                if accessory.get("type") == "button":
                    component, entry = _button_component(card_id, idx, accessory, action_data, default_reusable)
                    section["accessory"] = component
                    if entry:
                        registry.append(entry)
                elif accessory.get("type") == "thumbnail":
                    media = copy.deepcopy(accessory.get("media") or {})
                    if media:
                        section["accessory"] = {"type": 11, "media": media}
            if section.get("accessory"):
                components.append(section)
            else:
                components.extend(section["components"])
            continue
        # Unsupported rich blocks are ignored intentionally.

    modal_spec = spec.get("modal") if isinstance(spec.get("modal"), dict) else None
    if modal_spec:
        trigger_component, trigger_entry, submit_entry = _modal_trigger_component(card_id, modal_spec, action_data, default_reusable)
        components.append({"type": 1, "components": [trigger_component]})
        registry.extend([trigger_entry, submit_entry])

    return components, registry


def _build_v2_from_legacy_spec(spec: Dict[str, Any]) -> Tuple[List[Dict[str, Any]], List[RegistryEntry]]:
    card_id = spec.get("card_id") or _make_card_id()
    components: List[Dict[str, Any]] = []
    registry: List[RegistryEntry] = []
    default_reusable = bool(spec.get("reusable", False))
    action_data = spec.get("action_data") if isinstance(spec.get("action_data"), dict) else None

    content = str(spec.get("content") or "")
    if content:
        components.append({"type": 10, "content": content})

    buttons = spec.get("buttons") or []
    if buttons:
        row = {"type": 1, "components": []}
        for idx, raw_btn in enumerate(list(buttons)[:5]):
            component, entry = _button_component(card_id, idx, raw_btn, action_data, default_reusable)
            row["components"].append(component)
            if entry:
                registry.append(entry)
        components.append(row)

    modal_spec = spec.get("modal") if isinstance(spec.get("modal"), dict) else None
    if modal_spec:
        trigger_component, trigger_entry, submit_entry = _modal_trigger_component(card_id, modal_spec, action_data, default_reusable)
        components.append({"type": 1, "components": [trigger_component]})
        registry.extend([trigger_entry, submit_entry])

    return components, registry


def build_message_payload(spec: Dict[str, Any]) -> Tuple[Dict[str, Any], List[RegistryEntry], str]:
    if spec.get("blocks") or spec.get("text") or spec.get("modal"):
        components, registry = _build_v2_from_rich_spec(spec)
    else:
        components, registry = _build_v2_from_legacy_spec(spec)
    if not components:
        raise ValueError("No components were generated from the provided specification")
    return {"flags": V2_FLAG, "components": components}, registry, _summary_from_spec(spec)


def persist_message(channel_id: str, message_id: str, content_summary: str, registry: List[RegistryEntry]) -> None:
    db.init_db()
    conn = db.get_conn()
    cur = conn.cursor()
    cur.execute(
        "INSERT OR IGNORE INTO messages(message_id, channel_id, content) VALUES(?,?,?)",
        (message_id, channel_id, content_summary),
    )
    for entry in registry:
        cur.execute(
            """
            INSERT OR REPLACE INTO components
            (message_id, custom_id, component_type, label, semantic_action, payload_json, single_use, expires_at, status, agent_hint, session_hint, thread_hint)
            VALUES(?,?,?,?,?,?,?,?,?,?,?,?)
            """,
            (
                message_id,
                entry["custom_id"],
                entry["component_type"],
                entry["label"],
                entry["semantic_action"],
                entry["payload_json"],
                entry["single_use"],
                entry.get("expires_at"),
                "active",
                entry.get("agent_hint"),
                entry.get("session_hint"),
                entry.get("thread_hint"),
            ),
        )
    conn.commit()
    conn.close()


def send_action_spec(channel_id: str, spec: Dict[str, Any]) -> dict:
    payload, registry, summary = build_message_payload(spec)
    status, resp = discord_request("POST", f"/channels/{channel_id}/messages", payload)
    if status not in (200, 201):
        return {"ok": False, "status": status, "error": resp, "hint": _discord_error_hint(status, resp)}
    message_id = str(resp.get("id") or "")
    if message_id:
        persist_message(channel_id, message_id, summary, registry)
    return {
        "ok": True,
        "message_id": message_id,
        "component_count": len(registry),
        "mode": "discord-v2-direct",
    }


def send_action_message(channel_id: str, content: str, buttons: List[Dict[str, Any]], action_data: Optional[dict] = None, reusable: bool = False) -> dict:
    spec = {
        "content": content,
        "buttons": copy.deepcopy(buttons),
        "action_data": copy.deepcopy(action_data or {}),
        "reusable": reusable,
    }
    return send_action_spec(channel_id, spec)


def send_from_file(channel_id: str, json_file: str) -> dict:
    with open(json_file, "r", encoding="utf-8") as f:
        spec = json.load(f)
    return send_action_spec(channel_id, spec)


def send_demo_hello(channel_id: str) -> dict:
    spec = {
        "text": "🧪 **Bridge demo**",
        "blocks": [
            {"type": "text", "text": "Use the controls below to verify the local dispatch path and the OpenClaw bridge."},
            {
                "type": "actions",
                "buttons": [
                    {"label": "Say hello", "style": "primary", "action": "say_hello", "args": {"text": "Hello from discord-component-v2."}},
                    {"label": "Done", "style": "success", "action": "discord.reply_text", "args": {"text": "Done."}},
                ],
            },
            {
                "type": "actions",
                "select": {
                    "type": "string",
                    "action": "demo.pick_option",
                    "placeholder": "Pick an option",
                    "options": [
                        {"label": "Option A", "value": "a"},
                        {"label": "Option B", "value": "b"},
                    ],
                },
            },
        ],
        "modal": {
            "title": "Demo details",
            "triggerLabel": "Open form",
            "action": "demo.submit_details",
            "fields": [
                {"type": "text", "label": "Requester", "custom_id": "requester", "style": 1, "required": False},
                {"type": "text", "label": "Details", "custom_id": "details", "style": 2, "required": False},
            ],
        },
        "action_data": {"kind": "dispatch"},
        "reusable": True,
    }
    return send_action_spec(channel_id, spec)


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Send a Discord Components v2 action message with bridge-managed interactions")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("demo-hello", help="Send a deterministic local demo message")
    p.add_argument("--channel-id", required=True)

    p = sub.add_parser("file", help="Send an action message from JSON")
    p.add_argument("--channel-id", required=True)
    p.add_argument("--json-file", required=True)

    p = sub.add_parser("test", help="Send a basic approve / decline test message")
    p.add_argument("--channel-id", required=True)

    args = parser.parse_args()
    if args.cmd == "demo-hello":
        result = send_demo_hello(args.channel_id)
    elif args.cmd == "file":
        result = send_from_file(args.channel_id, args.json_file)
    else:
        result = send_action_spec(
            args.channel_id,
            {
                "content": "🧪 **Test action message**\n\nClick a control to verify the workflow.",
                "buttons": [
                    {"label": "Approve", "style": "success", "action": "workflow.approve", "args": {"decision": "approve"}},
                    {"label": "Decline", "style": "danger", "action": "discord.reply_text", "args": {"text": "Declined."}},
                ],
                "action_data": {"kind": "dispatch", "args": {"request_id": "demo-001"}},
            },
        )
    print(json.dumps(result, ensure_ascii=False, indent=2))
