#!/usr/bin/env python3
"""beta2: timeline ordered events."""
from __future__ import annotations
import os, sys, tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "lib"))

from storage import db as dbmod  # noqa: E402
from observability.timeline import timeline, format_timeline  # noqa: E402


def main() -> int:
    with tempfile.TemporaryDirectory() as td:
        db_path = str(Path(td) / "t.db")
        os.environ["AGENTBOX_V5_DB"] = db_path
        dbmod.init_db(db_path)
        task = dbmod.create_task("/tmp/p", "tl", db_path=db_path)
        for k in ("task.created", "handoff.created", "handoff.completed"):
            dbmod.emit_event(k, k, task_id=task["id"], db_path=db_path)
        ev = timeline(task["id"], db_path=db_path)
        assert len(ev) >= 3
        ids = [e["id"] for e in ev]
        assert ids == sorted(ids)
        text = format_timeline(ev)
        assert "handoff.created" in text
        print("OK: test_timeline")
    return 0


if __name__ == "__main__":
    sys.exit(main())
