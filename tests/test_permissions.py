#!/usr/bin/env python3
"""beta3: permission profiles."""
from __future__ import annotations
import os, sys, tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "lib"))
os.environ.setdefault("AGENTBOX_V5_LIB", str(ROOT / "lib"))

from storage import db as dbmod  # noqa: E402
from agents.registry import register_agent  # noqa: E402
from policy.permissions import get_agent_permissions, check_permission  # noqa: E402


def main() -> int:
    with tempfile.TemporaryDirectory() as td:
        db_path = str(Path(td) / "t.db")
        home = Path(td)
        (home / "config").mkdir()
        (home / "config" / "agents.toml").write_text((ROOT / "config" / "agents.toml").read_text())
        os.environ["AGENTBOX_V5_DB"] = db_path
        os.environ["AGENTBOX_V5_HOME"] = str(home)
        dbmod.init_db(db_path)
        register_agent("coder", "Coder", role="coder", db_path=db_path)
        register_agent("planner", "Planner", role="planner", db_path=db_path)
        p = get_agent_permissions("coder", db_path=db_path)
        assert p.get("write_files") is True
        r = check_permission("planner", "filesystem.write", db_path=db_path)
        assert r["allowed"] is False
        r = check_permission("coder", "filesystem.write", db_path=db_path)
        assert r["allowed"] is True
        r = check_permission("planner", "agent.delegate", context={"target_agent": "researcher"}, db_path=db_path)
        assert r["allowed"] is True
    print("OK: test_permissions")
    return 0


if __name__ == "__main__":
    sys.exit(main())
