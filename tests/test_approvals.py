#!/usr/bin/env python3
"""beta3: approval create/approve/reject with new columns."""
from __future__ import annotations
import os, sys, tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "lib"))
os.environ.setdefault("AGENTBOX_V5_LIB", str(ROOT / "lib"))

from storage import db as dbmod  # noqa: E402
from policy.approvals import create_approval, resolve_approval, list_approvals, get_approval  # noqa: E402


def main() -> int:
    with tempfile.TemporaryDirectory() as td:
        db_path = str(Path(td) / "t.db")
        os.environ["AGENTBOX_V5_DB"] = db_path
        dbmod.init_db(db_path)
        task = dbmod.create_task("/tmp/p", "a", db_path=db_path)
        ap = create_approval(
            task["id"], gate="git.push", reason="need push",
            risk_score=50, payload={"action": "git.push"}, db_path=db_path,
        )
        assert ap["status"] == "pending"
        assert ap.get("approval_type") or ap.get("gate")
        t = dbmod.get_task(task["id"], db_path=db_path)
        assert t["status"] == "awaiting_approval"
        ap = resolve_approval(ap["id"], "approved", reason="ok", db_path=db_path)
        assert ap["status"] == "approved"
        t = dbmod.get_task(task["id"], db_path=db_path)
        assert t["status"] == "queued"
        assert list_approvals(db_path=db_path)
        # reject path
        task2 = dbmod.create_task("/tmp/p", "a2", db_path=db_path)
        ap2 = create_approval(task2["id"], gate="packages.install", db_path=db_path)
        resolve_approval(ap2["id"], "rejected", reason="no", db_path=db_path)
        t2 = dbmod.get_task(task2["id"], db_path=db_path)
        assert t2["status"] == "rejected"
    print("OK: test_approvals")
    return 0


if __name__ == "__main__":
    sys.exit(main())
