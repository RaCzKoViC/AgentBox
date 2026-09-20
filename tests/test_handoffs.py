#!/usr/bin/env python3
"""beta2: handoff engine lifecycle + deny random."""
from __future__ import annotations
import os, sys, tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "lib"))
# seed config path
os.environ.setdefault("AGENTBOX_V5_LIB", str(ROOT / "lib"))

from storage import db as dbmod  # noqa: E402
from agents.registry import register_agent  # noqa: E402
from handoffs.engine import (  # noqa: E402
    create_handoff, accept_handoff, start_handoff, complete_handoff,
    fail_handoff, reject_handoff, get_handoff,
)


def main() -> int:
    with tempfile.TemporaryDirectory() as td:
        db_path = str(Path(td) / "t.db")
        home = Path(td) / "home"
        (home / "config").mkdir(parents=True)
        # copy agents.toml
        src = ROOT / "config" / "agents.toml"
        if src.is_file():
            (home / "config" / "agents.toml").write_text(src.read_text())
        os.environ["AGENTBOX_V5_DB"] = db_path
        os.environ["AGENTBOX_V5_HOME"] = str(home)
        dbmod.init_db(db_path)
        register_agent("planner", "Planner", role="planner", db_path=db_path)
        register_agent("researcher", "Researcher", role="researcher", db_path=db_path)
        register_agent("tester", "Tester", role="tester", db_path=db_path)
        task = dbmod.create_task("/tmp/p", "h", db_path=db_path)

        h = create_handoff(task["id"], "planner", "researcher", "go", db_path=db_path)
        assert h["status"] == "pending"
        h = accept_handoff(h["id"], db_path=db_path)
        assert h["status"] == "accepted"
        h = start_handoff(h["id"], db_path=db_path)
        assert h["status"] == "running"
        h = complete_handoff(h["id"], result={"ok": True}, db_path=db_path)
        assert h["status"] == "completed"

        # deny tester → planner
        try:
            create_handoff(task["id"], "tester", "planner", "nope", db_path=db_path)
            raise AssertionError("expected PermissionError")
        except PermissionError:
            pass

        # fail with retries then block
        h2 = create_handoff(task["id"], "planner", "researcher", "retry", required=True, db_path=db_path)
        accept_handoff(h2["id"], db_path=db_path)
        start_handoff(h2["id"], db_path=db_path)
        # max_retries default 2 → first two fails retry, third permanent
        h2 = fail_handoff(h2["id"], "e1", db_path=db_path)
        assert h2["status"] == "pending" and int(h2["retries"]) == 1
        start_handoff(h2["id"], db_path=db_path)
        h2 = fail_handoff(h2["id"], "e2", db_path=db_path)
        assert h2["status"] == "pending" and int(h2["retries"]) == 2
        start_handoff(h2["id"], db_path=db_path)
        h2 = fail_handoff(h2["id"], "e3", db_path=db_path)
        assert h2["status"] == "failed"
        t = dbmod.get_task(task["id"], db_path=db_path)
        assert t["status"] == "blocked"

        print("OK: test_handoffs")
    return 0


if __name__ == "__main__":
    sys.exit(main())
