#!/usr/bin/env python3
"""AgentBox v5 scheduler — pick ready queued tasks (alpha2)."""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Optional

_HERE = Path(__file__).resolve().parent
_CANDIDATES = [
    _HERE.parent / "storage",
    _HERE.parent.parent / "lib" / "storage",
]
for _c in _CANDIDATES:
    if (_c / "db.py").is_file():
        sys.path.insert(0, str(_c))
        break

import db  # noqa: E402


def pick_ready(max_n: int = 1, db_path: Optional[str] = None) -> list[dict]:
    """Return up to max_n ready queued tasks (deps satisfied).
    Honors priority DESC, created_at ASC (via list_ready_queued).
    """
    if max_n < 1:
        return []
    return db.list_ready_queued(limit=max_n, db_path=db_path)


def slots_available(max_workers: int = 2, db_path: Optional[str] = None) -> int:
    running = db.count_running(db_path=db_path)
    return max(0, max_workers - running)


def pick_for_workers(max_workers: int = 2, db_path: Optional[str] = None) -> list[dict]:
    """Pick as many ready tasks as free worker slots allow."""
    n = slots_available(max_workers=max_workers, db_path=db_path)
    if n <= 0:
        return []
    return pick_ready(max_n=n, db_path=db_path)


def main(argv: Optional[list[str]] = None) -> int:
    argv = list(argv if argv is not None else sys.argv[1:])
    db_path = os.environ.get("AGENTBOX_V5_DB")
    if not argv:
        print("usage: scheduler.py pick-ready [--max N] | pick-for-workers [--max-workers N]",
              file=sys.stderr)
        return 2
    cmd = argv[0]
    try:
        if cmd == "pick-ready":
            max_n = 1
            if "--max" in argv:
                i = argv.index("--max")
                max_n = int(argv[i + 1])
            print(json.dumps(pick_ready(max_n=max_n, db_path=db_path), indent=2, default=str))
            return 0
        if cmd == "pick-for-workers":
            mw = 2
            if "--max-workers" in argv:
                i = argv.index("--max-workers")
                mw = int(argv[i + 1])
            print(json.dumps(pick_for_workers(max_workers=mw, db_path=db_path), indent=2, default=str))
            return 0
        if cmd == "slots":
            mw = 2
            if "--max-workers" in argv:
                i = argv.index("--max-workers")
                mw = int(argv[i + 1])
            print(slots_available(max_workers=mw, db_path=db_path))
            return 0
        print(f"unknown: {cmd}", file=sys.stderr)
        return 2
    except Exception as e:
        print(f"error: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
