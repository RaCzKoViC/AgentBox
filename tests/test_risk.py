#!/usr/bin/env python3
"""beta3: risk scoring levels."""
from __future__ import annotations
import os, sys, tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "lib"))
os.environ.setdefault("AGENTBOX_V5_LIB", str(ROOT / "lib"))

from storage import db as dbmod  # noqa: E402
from policy.risk import assess_risk, risk_level, persist_assessment, list_history  # noqa: E402


def main() -> int:
    assert risk_level(0) == "LOW"
    assert risk_level(25) == "MODERATE"
    assert risk_level(50) == "ELEVATED"
    assert risk_level(70) == "HIGH"
    assert risk_level(90) == "CRITICAL"

    a = assess_risk("filesystem.write", resource="/workspace/foo.py")
    assert a["risk_level"] in ("LOW", "MODERATE")
    assert a["decision"] == "allow"

    a = assess_risk("git.force_push")
    assert a["risk_score"] == 100 and a["risk_level"] == "CRITICAL" and a["decision"] == "deny"

    a = assess_risk("docker.privileged")
    assert a["decision"] == "deny"

    with tempfile.TemporaryDirectory() as td:
        db_path = str(Path(td) / "t.db")
        os.environ["AGENTBOX_V5_DB"] = db_path
        os.environ["AGENTBOX_V5_HOME"] = td
        dbmod.init_db(db_path)
        r = persist_assessment(assess_risk("git.push"), task_id=None, db_path=db_path)
        assert r.get("id")
        hist = list_history(db_path=db_path)
        assert hist
    print("OK: test_risk")
    return 0


if __name__ == "__main__":
    sys.exit(main())
