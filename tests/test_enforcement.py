#!/usr/bin/env python3
"""beta3: enforce_action pipeline."""
from __future__ import annotations
import os, sys, tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "lib"))
os.environ.setdefault("AGENTBOX_V5_LIB", str(ROOT / "lib"))

from storage import db as dbmod  # noqa: E402
from agents.registry import register_agent  # noqa: E402
from policy.enforcement import enforce_action  # noqa: E402


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
        register_agent("coder", "Coder", role="coder", db_path=db_path)
        task = dbmod.create_task("/tmp/p", "e", db_path=db_path)

        r = enforce_action("filesystem.write", resource="/workspace/a.py",
                           task_id=task["id"], agent_name="coder", db_path=db_path)
        assert r["decision"] == "allow", r

        executed = {"ok": False}
        r = enforce_action(
            "filesystem.write", resource="/workspace/b.py",
            task_id=task["id"], agent_name="coder",
            execute=lambda: executed.__setitem__("ok", True) or "done",
            db_path=db_path,
        )
        assert r["decision"] == "allow" and executed["ok"]

        r = enforce_action("git.force_push", agent_name="coder",
                           context={"force": True}, db_path=db_path)
        assert r["decision"] == "deny"
        # ensure execute not called on deny
        flag = {"ran": False}
        try:
            enforce_action("git.force_push", execute=lambda: flag.__setitem__("ran", True),
                           context={"force": True}, db_path=db_path)
        except Exception:
            pass
        assert flag["ran"] is False
    print("OK: test_enforcement")
    return 0


if __name__ == "__main__":
    sys.exit(main())
