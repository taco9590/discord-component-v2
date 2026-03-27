#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import signal
import time
from pathlib import Path
from typing import Optional

from lib.config import WORKSPACE_SLUG, ensure_state_dir, token_lock_path


def _pid_alive(pid: int) -> bool:
    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def acquire_token_lock(token: str) -> tuple[bool, Path, Optional[dict]]:
    ensure_state_dir()
    path = token_lock_path(token)
    current = {
        "pid": os.getpid(),
        "workspace": WORKSPACE_SLUG,
        "started_at": int(time.time()),
    }
    if path.exists():
        try:
            existing = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            existing = None
        if isinstance(existing, dict):
            pid = int(existing.get("pid") or 0)
            if pid and _pid_alive(pid) and pid != os.getpid():
                return False, path, existing
    path.write_text(json.dumps(current, ensure_ascii=False, indent=2), encoding="utf-8")
    return True, path, None


def release_token_lock(token: str) -> None:
    path = token_lock_path(token)
    if not path.exists():
        return
    try:
        existing = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        existing = None
    if isinstance(existing, dict) and int(existing.get("pid") or 0) not in {0, os.getpid()}:
        return
    try:
        path.unlink()
    except FileNotFoundError:
        pass
