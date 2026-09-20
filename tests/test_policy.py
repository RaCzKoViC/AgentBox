#!/usr/bin/env python3
"""beta3: policy evaluate + force_push deny."""
from __future__ import annotations
import os, sys, tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "lib"))
os.environ.setdefault("AGENTBOX_V5_LIB", str(ROOT / "lib"))

from storage import db as dbmod  # noqa: E402
from policy.policies import (  # noqa: E402
    check_action, evaluate_policy, seed_ini_from_defaults, seed_policies_table, list_policies_config,
)


def main() -> int:
    with tempfile.TemporaryDirectory() as td:
        home = Path(td)
        (home / "config").mkdir()
        # point ini elsewhere
        ini = home / "policies.ini"
        src = ROOT / "config" / "policies.ini"
        ini.write_text(src.read_text() if src.is_file() else "[git]\nforce_push=deny\n")
        os.environ["AGENTBOX_POLICIES_INI"] = str(ini)
        os.environ["AGENTBOX_V5_HOME"] = str(home)
        os.environ["AGENTBOX_V5_DB"] = str(home / "t.db")
        os.environ["AGENTBOX_AUTO_APPROVE"] = "1"
        dbmod.init_db(str(home / "t.db"))
        seed_ini_from_defaults()
        seed_policies_table(db_path=str(home / "t.db"))

        d = check_action("git.force_push")
        assert d["decision"] == "deny", d

        # AUTO_APPROVE: non-critical approval becomes allow
        e = evaluate_policy("git.push", db_path=str(home / "t.db"))
        assert e["decision"] in ("allow", "approval"), e
        # CRITICAL stays deny
        e = evaluate_policy("git.force_push", db_path=str(home / "t.db"))
        assert e["decision"] == "deny", e

        os.environ["AGENTBOX_AUTO_APPROVE"] = "0"
        e = evaluate_policy("git.push", db_path=str(home / "t.db"))
        assert e["decision"] in ("approval", "deny"), e

        assert list_policies_config()
    print("OK: test_policy")
    return 0


if __name__ == "__main__":
    sys.exit(main())
