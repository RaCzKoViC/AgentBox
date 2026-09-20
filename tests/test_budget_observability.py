#!/usr/bin/env python3
"""beta3: budget/policy/risk events + metrics."""
from __future__ import annotations
import os, sys, tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "lib"))
os.environ.setdefault("AGENTBOX_V5_LIB", str(ROOT / "lib"))

from storage import db as dbmod  # noqa: E402
from policy.policies import evaluate_policy  # noqa: E402
from policy.risk import assess_risk, persist_assessment  # noqa: E402
from policy.budgets import record_usage, check_budget, seed_budgets_table  # noqa: E402
from observability.metrics import list_metrics  # noqa: E402


def main() -> int:
    with tempfile.TemporaryDirectory() as td:
        db_path = str(Path(td) / "t.db")
        home = Path(td)
        (home / "config").mkdir()
        (home / "config" / "budgets.toml").write_text((ROOT / "config" / "budgets.toml").read_text())
        ini = home / "policies.ini"
        ini.write_text((ROOT / "config" / "policies.ini").read_text())
        os.environ["AGENTBOX_POLICIES_INI"] = str(ini)
        os.environ["AGENTBOX_V5_DB"] = db_path
        os.environ["AGENTBOX_V5_HOME"] = str(home)
        dbmod.init_db(db_path)
        seed_budgets_table(db_path=db_path)
        evaluate_policy("git.force_push", db_path=db_path)
        persist_assessment(assess_risk("git.push"), db_path=db_path)
        record_usage("global", None, "max_tokens", 100, db_path=db_path)
        check_budget("global", None, "max_tokens", 1, db_path=db_path)
        ev = dbmod.list_events(limit=50, db_path=db_path)
        kinds = {e["kind"] for e in ev}
        assert "policy.evaluated" in kinds or "policy.denied" in kinds
        assert "risk.assessed" in kinds
        mets = list_metrics(limit=50, db_path=db_path)
        names = {m["metric_name"] for m in mets}
        assert any("policy" in n or "risk" in n or "budget" in n for n in names), names
    print("OK: test_budget_observability")
    return 0


if __name__ == "__main__":
    sys.exit(main())
