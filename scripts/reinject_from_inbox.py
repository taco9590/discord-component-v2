#!/usr/bin/env python3
"""Reinject queued inbox events through injector.inject()."""
from __future__ import annotations

import argparse
import json
import os
import sys

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE)

from lib import db
from lib.config import INBOX_PATH
from scripts import injector


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=100)
    args = parser.parse_args()

    if not INBOX_PATH.exists():
        print(f"inbox not found: {INBOX_PATH}")
        return 0

    lines = INBOX_PATH.read_text(encoding="utf-8").splitlines()
    if not lines:
        print("inbox is empty")
        return 0

    replay = lines[: args.limit]
    kept = lines[args.limit :]
    success = 0
    failed = 0

    for line in replay:
        item = json.loads(line)
        iid = item.get("interaction_id")
        text = item.get("text")
        if not iid or not text:
            failed += 1
            kept.append(line)
            continue

        result = injector.inject(iid, text)
        if result.get("ok"):
            db.set_done(iid, note="reinject-ok")
            success += 1
        else:
            db.set_done_fallback(iid, note=str(result))
            kept.append(line)
            failed += 1

    INBOX_PATH.write_text(("\n".join(kept) + ("\n" if kept else "")), encoding="utf-8")
    print(f"reinject complete: success={success} failed={failed}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
