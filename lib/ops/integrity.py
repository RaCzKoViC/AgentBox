#!/usr/bin/env python3
"""SQLite integrity checks for AgentBox v5 Stable."""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any, Optional

_HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(_HERE.parent))

from ops.paths import db_path  # noqa: E402
from storage import db as dbmod  # noqa: E402


def quick_check(path: Optional[str] = None) -> dict[str, Any]:
    p = Path(path) if path else db_path()
    if not p.is_file():
        return {"ok": False, "check": "quick_check", "result": "missing", "path": str(p)}
    with dbmod.connect(str(p)) as conn:
        rows = conn.execute("PRAGMA quick_check").fetchall()
    result = rows[0][0] if rows else "unknown"
    return {"ok": result == "ok", "check": "quick_check", "result": result, "path": str(p)}


def integrity_check(path: Optional[str] = None, full: bool = True) -> dict[str, Any]:
    p = Path(path) if path else db_path()
    if not p.is_file():
        return {"ok": False, "check": "integrity_check", "result": "missing", "path": str(p)}
    pragma = "PRAGMA integrity_check" if full else "PRAGMA quick_check"
    with dbmod.connect(str(p)) as conn:
        rows = [r[0] for r in conn.execute(pragma).fetchall()]
    ok = len(rows) == 1 and rows[0] == "ok"
    return {
        "ok": ok,
        "check": "integrity_check" if full else "quick_check",
        "result": rows[0] if ok else rows[:20],
        "path": str(p),
    }


def schema_tables(path: Optional[str] = None) -> dict[str, Any]:
    p = Path(path) if path else db_path()
    required = {
        "tasks", "runs", "events", "approvals", "memories", "agents",
        "agent_handoffs", "metrics", "artifacts", "policies", "budgets",
        "budget_usage", "risk_assessments", "web_sessions", "migrations",
        "runtime_processes",
    }
    with dbmod.connect(str(p)) as conn:
        present = {r[0] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()}
    missing = sorted(required - present)
    return {"ok": not missing, "present": sorted(present & required), "missing": missing}


def main(argv: Optional[list[str]] = None) -> int:
    argv = list(argv or sys.argv[1:])
    cmd = argv[0] if argv else "check"
    if cmd in ("check", "quick"):
        out = quick_check()
    elif cmd in ("full", "integrity"):
        out = integrity_check(full=True)
    elif cmd == "schema":
        out = schema_tables()
    else:
        print("usage: integrity.py check|full|schema", file=sys.stderr)
        return 2
    print(json.dumps(out, indent=2))
    return 0 if out.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
