#!/usr/bin/env python3
"""beta2: build_handoff_context pack."""
from __future__ import annotations
import os, sys, tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "lib"))

from storage import db as dbmod  # noqa: E402
from memory.store import add_memory  # noqa: E402
from memory.context import build_handoff_context  # noqa: E402


def main() -> int:
    with tempfile.TemporaryDirectory() as td:
        db_path = str(Path(td) / "t.db")
        home = Path(td) / "home"
        (home / "memory").mkdir(parents=True)
        os.environ["AGENTBOX_V5_DB"] = db_path
        os.environ["AGENTBOX_V5_HOME"] = str(home)
        dbmod.init_db(db_path)
        task = dbmod.create_task("/tmp/p", "goal-title", description="do research", db_path=db_path)
        add_memory("task", task["id"], "focus APIs", kind="note", db_path=db_path)
        dbmod.emit_event("task.created", "created", task_id=task["id"], db_path=db_path)
        pack = build_handoff_context(task["id"], "planner", "researcher", reason="need info", db_path=db_path)
        for key in ("task_goal", "source_summary", "memories", "files", "artifacts", "findings", "constraints"):
            assert key in pack, pack.keys()
        assert "goal-title" in pack["task_goal"]
        assert pack["memories"]
        assert "no_full_history" in pack["constraints"]
        print("OK: test_context_handoff")
    return 0


if __name__ == "__main__":
    sys.exit(main())
