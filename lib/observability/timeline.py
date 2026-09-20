#!/usr/bin/env python3
"""AgentBox v5 task timeline — ordered events for CLI (beta2)."""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any, Optional


def _ensure_path() -> None:
    lib = str(Path(__file__).resolve().parent.parent)
    if lib not in sys.path:
        sys.path.insert(0, lib)


def timeline(task_id: str, limit: int = 200, db_path: Optional[str] = None) -> list[dict]:
    """Return chronological events for a task (oldest first)."""
    _ensure_path()
    from storage import db as dbmod  # type: ignore

    with dbmod.connect(db_path) as conn:
        rows = conn.execute(
            """
            SELECT id, ts, task_id, run_id, kind, message, payload_json
            FROM events
            WHERE task_id = ?
            ORDER BY id ASC
            LIMIT ?
            """,
            (task_id, limit),
        ).fetchall()
        return [dict(r) for r in rows]


def format_timeline(events: list[dict]) -> str:
    lines = []
    for e in events:
        ts = (e.get("ts") or "")[:19]
        kind = e.get("kind") or ""
        msg = e.get("message") or ""
        lines.append(f"{ts}  {kind:<28}  {msg}")
    return "\n".join(lines) if lines else "(no events)"


def main(argv: Optional[list[str]] = None) -> int:
    argv = list(argv if argv is not None else sys.argv[1:])
    db_path = os.environ.get("AGENTBOX_V5_DB")
    if not argv:
        print("usage: timeline.py TASK_ID [--limit N] [--text]", file=sys.stderr)
        return 2
    tid = argv[0]
    limit = 200
    text = False
    i = 1
    while i < len(argv):
        if argv[i] == "--limit" and i + 1 < len(argv):
            limit = int(argv[i + 1])
            i += 2
        elif argv[i] == "--text":
            text = True
            i += 1
        else:
            i += 1
    events = timeline(tid, limit=limit, db_path=db_path)
    if text:
        print(format_timeline(events))
    else:
        print(json.dumps(events, indent=2, default=str))
    return 0


if __name__ == "__main__":
    sys.exit(main())
