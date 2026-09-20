#!/usr/bin/env python3
"""Unit tests for AgentBox v5 SQLite module (alpha3)."""
from __future__ import annotations

import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "lib" / "storage"))

import db  # noqa: E402


def main() -> int:
    with tempfile.TemporaryDirectory() as td:
        db_path = str(Path(td) / "test.db")
        path = db.init_db(db_path)
        assert Path(path).is_file(), "db file missing"

        task = db.create_task(
            project_id="/tmp/demo",
            title="unit-test",
            description="db self check",
            provider="codex",
            db_path=db_path,
        )
        assert task["id"].startswith("t_")
        assert task["status"] == "created"

        task = db.set_task_status(task["id"], "queued", db_path=db_path)
        assert task["status"] == "queued"

        picked = db.pick_queued_task(db_path=db_path)
        assert picked and picked["id"] == task["id"]

        run = db.create_run(task["id"], worker_id="test", db_path=db_path)
        assert run["status"] == "running"
        assert db.count_running(db_path=db_path) == 1

        eid = db.emit_event(
            kind="plan.stub",
            message="hello",
            task_id=task["id"],
            run_id=run["id"],
            db_path=db_path,
        )
        assert eid > 0

        db.finish_run(run["id"], status="completed", exit_code=0, db_path=db_path)
        task2 = db.get_task(task["id"], db_path=db_path)
        assert task2["status"] == "completed"

        events = db.list_events(task_id=task["id"], limit=20, db_path=db_path)
        assert len(events) >= 3

        # --- depends_on / ready ---
        a = db.create_task("/tmp/demo", "A", db_path=db_path)
        b = db.create_task("/tmp/demo", "B", db_path=db_path)
        c = db.create_task("/tmp/demo", "C", db_path=db_path)
        db.set_depends_on(c["id"], [a["id"], b["id"]], db_path=db_path)
        try:
            db.add_depends_on(a["id"], [c["id"]], db_path=db_path)
            raise AssertionError("cycle not detected")
        except ValueError:
            pass

        db.set_task_status(a["id"], "queued", db_path=db_path)
        db.set_task_status(b["id"], "queued", db_path=db_path)
        db.set_task_status(c["id"], "queued", db_path=db_path)
        ready = db.list_ready_queued(limit=10, db_path=db_path)
        ready_ids = {t["id"] for t in ready}
        assert a["id"] in ready_ids and b["id"] in ready_ids
        assert c["id"] not in ready_ids

        db.set_task_status(a["id"], "completed", db_path=db_path)
        db.set_task_status(b["id"], "completed", db_path=db_path)
        ready2 = db.list_ready_queued(limit=10, db_path=db_path)
        assert any(t["id"] == c["id"] for t in ready2)

        g = db.graph_show(c["id"], db_path=db_path)
        assert len(g["dependencies"]) == 2

        # priority ordering
        hi = db.create_task("/tmp/demo", "hi", priority=100, db_path=db_path)
        lo = db.create_task("/tmp/demo", "lo", priority=1, db_path=db_path)
        db.set_task_status(hi["id"], "queued", db_path=db_path)
        db.set_task_status(lo["id"], "queued", db_path=db_path)
        # complete leftover C so it doesn't confuse — already ready but leave it
        first = db.list_ready_queued(limit=1, db_path=db_path)
        # Among newly queued hi/lo, hi should come first when both ready —
        # but C may still be queued ready. Filter.
        ordered = [t["id"] for t in db.list_ready_queued(limit=50, db_path=db_path)
                   if t["id"] in (hi["id"], lo["id"])]
        assert ordered == [hi["id"], lo["id"]], ordered


        # --- approvals table + budget fields (alpha3) ---
        conn = db.connect(db_path)
        row = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='approvals'"
        ).fetchone()
        conn.close()
        assert row, "approvals table missing"
        task_u = db.create_task("/tmp/demo", "usage", budget_tokens=5, db_path=db_path)
        assert task_u.get("budget_tokens") == 5
        assert "usage_tokens" in task_u

        print(f"OK test_db.py: deps+ready+priority events={len(events)}")
        return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as e:
        print(f"FAIL: {e}", file=sys.stderr)
        raise
