#!/usr/bin/env python3
"""AgentBox v5 dependency graph helpers (alpha2)."""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Optional

# Allow import of storage.db whether installed or from source tree
_HERE = Path(__file__).resolve().parent
_CANDIDATES = [
    _HERE.parent / "storage",  # installed: lib/core -> lib/storage
    _HERE.parent.parent / "lib" / "storage",
]
for _c in _CANDIDATES:
    if (_c / "db.py").is_file():
        sys.path.insert(0, str(_c))
        break

import db  # noqa: E402


def show(task_id: str, db_path: Optional[str] = None) -> dict:
    return db.graph_show(task_id, db_path=db_path)


def depend(task_id: str, on_ids: list[str], db_path: Optional[str] = None) -> dict:
    return db.add_depends_on(task_id, on_ids, db_path=db_path)


def main(argv: Optional[list[str]] = None) -> int:
    argv = list(argv if argv is not None else sys.argv[1:])
    db_path = os.environ.get("AGENTBOX_V5_DB")
    if not argv:
        print("usage: graph.py show TASK | depend TASK --on OTHER [...]", file=sys.stderr)
        return 2
    cmd = argv[0]
    try:
        if cmd == "show":
            if len(argv) < 2:
                print("show TASK required", file=sys.stderr)
                return 2
            print(json.dumps(show(argv[1], db_path=db_path), indent=2, ensure_ascii=False))
            return 0
        if cmd == "depend":
            if len(argv) < 2:
                print("depend TASK --on OTHER", file=sys.stderr)
                return 2
            tid = argv[1]
            ons: list[str] = []
            i = 2
            while i < len(argv):
                if argv[i] == "--on" and i + 1 < len(argv):
                    ons.append(argv[i + 1])
                    i += 2
                else:
                    i += 1
            if not ons:
                print("at least one --on required", file=sys.stderr)
                return 2
            print(json.dumps(depend(tid, ons, db_path=db_path), indent=2, ensure_ascii=False))
            return 0
        print(f"unknown: {cmd}", file=sys.stderr)
        return 2
    except Exception as e:
        print(f"error: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
