#!/usr/bin/env python3
"""beta3: handoff create goes through enforcement."""
from __future__ import annotations
import os, sys, tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "lib"))
os.environ.setdefault("AGENTBOX_V5_LIB", str(ROOT / "lib"))

from storage import db as dbmod  # noqa: E402
from agents.registry import register_agent  # noqa: E402
from handoffs.engine import create_handoff  # noqa: E402
from policy.budgets import record_usage, seed_budgets_table  # noqa: E402


def main() -> int:
    with tempfile.TemporaryDirectory() as td:
        db_path = str(Path(td) / "t.db")
        home = Path(td)
        (home / "config").mkdir()
        for name in ("agents.toml", "budgets.toml", "policies.toml"):
            src = ROOT / "config" / name
            if src.is_file():
                (home / "config" / name).write_text(src.read_text())
        ini = home / "policies.ini"
        ini.write_text((ROOT / "config" / "policies.ini").read_text())
        os.environ["AGENTBOX_POLICIES_INI"] = str(ini)
        os.environ["AGENTBOX_V5_DB"] = db_path
        os.environ["AGENTBOX_V5_HOME"] = str(home)
        os.environ["AGENTBOX_AUTO_APPROVE"] = "1"
        dbmod.init_db(db_path)
        seed_budgets_table(db_path=db_path)
        register_agent("planner", "Planner", role="planner", db_path=db_path)
        register_agent("researcher", "Researcher", role="researcher", db_path=db_path)
        register_agent("tester", "Tester", role="tester", db_path=db_path)
        task = dbmod.create_task("/tmp/p", "hp", db_path=db_path)

        h = create_handoff(task["id"], "planner", "researcher", "go", db_path=db_path)
        assert h["status"] == "pending"

        # deny random
        try:
            create_handoff(task["id"], "tester", "planner", "nope", db_path=db_path)
            raise AssertionError("expected deny")
        except PermissionError:
            pass

        # exceed handoff budget
        for _ in range(12):
            record_usage("task", task["id"], "max_handoffs", 1.0, task_id=task["id"], db_path=db_path)
        try:
            create_handoff(task["id"], "planner", "researcher", "over", db_path=db_path)
            raise AssertionError("expected budget deny")
        except PermissionError as e:
            assert "budget" in str(e).lower() or "DENIED" in str(e) or "enforcement" in str(e).lower()
    print("OK: test_handoff_policy")
    return 0


if __name__ == "__main__":
    sys.exit(main())
