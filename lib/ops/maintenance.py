#!/usr/bin/env python3
"""Maintenance mode flag for AgentBox v5 Stable."""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

_HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(_HERE.parent))

from ops.paths import maintenance_flag  # noqa: E402

# Global operational states
STATES = ("normal", "maintenance", "degraded", "read_only", "recovery")


def status() -> dict[str, Any]:
    flag = maintenance_flag()
    if not flag.is_file():
        return {"mode": "normal", "active": False, "flag": str(flag)}
    try:
        data = json.loads(flag.read_text(encoding="utf-8"))
    except Exception:
        data = {"mode": "maintenance", "reason": "flag present"}
    data["active"] = True
    data["flag"] = str(flag)
    return data


def enter(reason: str = "", mode: str = "maintenance") -> dict[str, Any]:
    if mode not in STATES:
        mode = "maintenance"
    payload = {
        "mode": mode,
        "reason": reason or "operator",
        "entered_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }
    flag = maintenance_flag()
    flag.parent.mkdir(parents=True, exist_ok=True)
    flag.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return status()


def exit_maintenance() -> dict[str, Any]:
    maintenance_flag().unlink(missing_ok=True)
    return status()


def is_maintenance() -> bool:
    return maintenance_flag().is_file()


def main(argv: Optional[list[str]] = None) -> int:
    argv = list(argv or sys.argv[1:])
    cmd = argv[0] if argv else "status"
    if cmd == "enter":
        reason = " ".join(argv[1:]) if len(argv) > 1 else "operator"
        out = enter(reason)
    elif cmd == "exit":
        out = exit_maintenance()
    elif cmd == "status":
        out = status()
    else:
        print("usage: maintenance.py enter|exit|status [reason]", file=sys.stderr)
        return 2
    print(json.dumps(out, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
