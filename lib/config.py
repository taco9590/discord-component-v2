#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from typing import Any, Dict, Optional

PACKAGE_NAME = "discord-component-v2"
SKILL_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_OPENCLAW_HOME = Path(os.environ.get("OPENCLAW_HOME", Path.home() / ".openclaw"))
DEFAULT_OPENCLAW_CONFIG = Path(os.environ.get("OPENCLAW_CONFIG_PATH") or os.environ.get("OPENCLAW_CONFIG") or (DEFAULT_OPENCLAW_HOME / "openclaw.json"))


def workspace_slug() -> str:
    raw = os.environ.get("DISCORD_COMPONENT_V2_WORKSPACE_ID") or str(SKILL_ROOT)
    digest = hashlib.sha1(raw.encode("utf-8")).hexdigest()[:10]
    base = Path(raw).name or "workspace"
    safe = "".join(ch if ch.isalnum() or ch in {"-", "_"} else "-" for ch in base).strip("-") or "workspace"
    return f"{safe}-{digest}"


WORKSPACE_SLUG = workspace_slug()
STATE_DIR = Path(
    os.environ.get("DISCORD_COMPONENT_V2_STATE_DIR")
    or os.environ.get("DISCORD_CV2_STATE_DIR")
    or (SKILL_ROOT / "state" / WORKSPACE_SLUG)
)
RUNTIME_DIR = STATE_DIR / "runtime"
DB_PATH = Path(
    os.environ.get("DISCORD_COMPONENT_V2_DB")
    or os.environ.get("DISCORD_CV2_DB")
    or (STATE_DIR / "bridge.db")
)
INBOX_PATH = Path(
    os.environ.get("DISCORD_COMPONENT_V2_INBOX")
    or os.environ.get("DISCORD_CV2_INBOX")
    or (STATE_DIR / "openclaw_inbox.jsonl")
)


def token_lock_path(token: str) -> Path:
    digest = hashlib.sha1(token.encode("utf-8")).hexdigest()[:16]
    return RUNTIME_DIR / f"token-lock-{digest}.json"

def ensure_state_dir() -> Path:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    RUNTIME_DIR.mkdir(parents=True, exist_ok=True)
    return STATE_DIR

def load_openclaw_config() -> Dict[str, Any]:
    if not DEFAULT_OPENCLAW_CONFIG.exists():
        return {}
    try:
        return json.loads(DEFAULT_OPENCLAW_CONFIG.read_text(encoding="utf-8"))
    except Exception:
        return {}

def get_nested(obj: Dict[str, Any], *keys: str) -> Optional[Any]:
    cur: Any = obj
    for key in keys:
        if not isinstance(cur, dict):
            return None
        cur = cur.get(key)
    return cur

def load_discord_token() -> Optional[str]:
    env_token = os.environ.get("DISCORD_BOT_TOKEN")
    if env_token:
        return env_token
    cfg = load_openclaw_config()
    token = get_nested(cfg, "channels", "discord", "token")
    return token if isinstance(token, str) and token else None

def openclaw_binary() -> str:
    return os.environ.get("OPENCLAW_BIN", "openclaw")


def discord_user_agent(version: str = "2.1.0") -> str:
    return f"DiscordBot (https://clawhub.ai, {version}) discord-component-v2"
