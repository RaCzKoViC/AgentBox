#!/usr/bin/env python3
"""beta3: budget check/record/exceed."""
from __future__ import annotations
import os, sys, tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "lib"))
os.environ.setdefault("AGENTBOX_V5_LIB", str(ROOT / "lib"))

from storage import db as dbmod  # noqa: E402
from policy.budgets import (  # noqa: E402
    seed_budgets_table, check_budget, record_usage, pause_budget, show_task,
)


def main() -> int:
    with tempfile.TemporaryDirectory() as td:
        db_path = str(Path(td) / "t.db")
        os.environ["AGENTBOX_V5_DB"] = db_path
        os.environ["AGENTBOX_V5_HOME"] = td
        (Path(td) / "config").mkdir()
        (Path(td) / "config" / "budgets.toml").write_text(
            (ROOT / "config" / "budgets.toml").read_text()
        )
        dbmod.init_db(db_path)
        seed_budgets_table(db_path=db_path)
        task = dbmod.create_task("/tmp/p", "b", db_path=db_path)
        tid = task["id"]
        for _ in range(10):
            record_usage("task", tid, "max_handoffs", 1.0, task_id=tid, db_path=db_path)
        chk = check_budget("task", tid, "max_handoffs", 1.0, db_path=db_path)
        assert not chk["ok"], chk
        pause_budget(tid, "test", db_path=db_path)
        t = dbmod.get_task(tid, db_path=db_path)
        assert t["status"] in ("budget_paused", "paused_budget")
        st = show_task(tid, db_path=db_path)
        assert st["handoffs"]["used"] >= 10
    print("OK: test_budget")
    return 0


if __name__ == "__main__":
    sys.exit(main())
