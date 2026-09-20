#!/usr/bin/env python3
"""beta2: can_delegate matrix."""
from __future__ import annotations
import os, sys, tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "lib"))

from storage import db as dbmod  # noqa: E402
from agents.registry import (  # noqa: E402
    register_agent, can_delegate, load_delegate_matrix, seed_from_config,
)


def main() -> int:
    with tempfile.TemporaryDirectory() as td:
        db_path = str(Path(td) / "t.db")
        home = Path(td) / "home"
        (home / "config").mkdir(parents=True)
        src = ROOT / "config" / "agents.toml"
        (home / "config" / "agents.toml").write_text(src.read_text())
        os.environ["AGENTBOX_V5_DB"] = db_path
        os.environ["AGENTBOX_V5_HOME"] = str(home)
        dbmod.init_db(db_path)
        matrix = load_delegate_matrix()
        assert "planner" in matrix and "researcher" in matrix["planner"]
        register_agent("planner", "P", role="planner", db_path=db_path)
        register_agent("coder", "C", role="coder", db_path=db_path)
        ok = can_delegate("planner", "researcher", db_path=db_path)
        assert ok["allowed"] is True
        bad = can_delegate("planner", "coder", db_path=db_path)
        assert bad["allowed"] is False
        rows = seed_from_config(db_path=db_path)
        assert len(rows) >= 5
        print("OK: test_agent_registry")
    return 0


if __name__ == "__main__":
    sys.exit(main())
