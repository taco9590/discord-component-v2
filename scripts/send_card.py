#!/usr/bin/env python3
from __future__ import annotations

import copy
import json
import subprocess
import sys
import os

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE)

from lib.config import openclaw_binary

def send_v2_card(channel_id: str, components: dict) -> dict:
    comps = copy.deepcopy(components)
    filtered = []
    removed_any = False
    for block in comps.get("blocks") or []:
        if isinstance(block, dict) and block.get("type") == "actions":
            items = block.get("buttons") or block.get("components") or []
            keep = []
            for item in items:
                if item.get("url") or item.get("style") == 5:
                    keep.append(item)
                else:
                    removed_any = True
            if keep:
                filtered.append({"type": "actions", "buttons": keep})
            else:
                removed_any = True
            continue
        filtered.append(block)
    comps["blocks"] = filtered
    if removed_any:
        print("send_card.py: interactive buttons were removed; use send_action.py for click handling.", file=sys.stderr)

    cmd = [
        openclaw_binary(), "message", "send",
        "--channel", "discord",
        "--target", f"channel:{channel_id}",
        "--components", json.dumps(comps, ensure_ascii=False),
    ]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        return {"ok": result.returncode == 0, "returncode": result.returncode, "stdout": result.stdout, "stderr": result.stderr}
    except Exception as e:
        return {"ok": False, "error": str(e)}

def send_from_file(channel_id: str, json_file: str) -> dict:
    with open(json_file, "r", encoding="utf-8") as f:
        components = json.load(f)
    return send_v2_card(channel_id, components)

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Send a read-only Components v2 card")
    sub = parser.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("file", help="Send a card from JSON")
    p.add_argument("--channel-id", required=True)
    p.add_argument("--json-file", required=True)
    args = parser.parse_args()
    print(json.dumps(send_from_file(args.channel_id, args.json_file), ensure_ascii=False, indent=2))
