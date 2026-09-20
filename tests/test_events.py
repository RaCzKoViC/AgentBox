#!/usr/bin/env python3
"""beta2: event taxonomy emit/list."""
from __future__ import annotations
import sys, tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "lib"))

from storage import db as dbmod  # noqa: E402


KINDS = [
    "task.created", "task.completed", "agent.registered",
    "handoff.created", "handoff.completed",
    "provider.request", "sandbox.created", "approval.created",
]


def main() -> int:
    with tempfile.TemporaryDirectory() as td:
        db_path = str(Path(td) / "t.db")
        dbmod.init_db(db_path)
        task = dbmod.create_task("/tmp/p", "ev", db_path=db_path)
        for k in KINDS:
            eid = dbmod.emit_event(k, f"msg-{k}", task_id=task["id"], db_path=db_path)
            assert eid > 0
        ev = dbmod.list_events(task_id=task["id"], limit=50, db_path=db_path)
        kinds = {e["kind"] for e in ev}
        for k in KINDS:
            assert k in kinds, (k, kinds)
        print("OK: test_events")
    return 0


if __name__ == "__main__":
    sys.exit(main())
