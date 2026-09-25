#!/usr/bin/env python3
"""Pending user decisions ("Czeka na Macieja") — small persisted list in SQLite.

CLI:
  pending.py list [--all|--status open|resolved] [--json]
  pending.py add TEXT [--context C] [--source S]
  pending.py resolve ID [--note N]
  pending.py reopen ID
"""
from __future__ import annotations

import argparse
import json
import secrets
import sys
from pathlib import Path
from typing import Any, Optional

_HERE = Path(__file__).resolve().parent
if str(_HERE.parent) not in sys.path:
    sys.path.insert(0, str(_HERE.parent))

from storage import db as dbmod  # noqa: E402

STATUSES = ("open", "resolved")

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS pending_decisions (
    id TEXT PRIMARY KEY,
    text TEXT NOT NULL,
    context TEXT NOT NULL DEFAULT '',
    source TEXT NOT NULL DEFAULT 'cli',
    status TEXT NOT NULL DEFAULT 'open',
    resolution TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    resolved_at TEXT,
    resolved_by TEXT NOT NULL DEFAULT ''
);
CREATE INDEX IF NOT EXISTS idx_pending_decisions_status ON pending_decisions(status, created_at);
"""


def ensure_schema(conn) -> None:
    conn.executescript(SCHEMA_SQL)


def _row(r) -> dict[str, Any]:
    return dict(r) if r is not None else {}


def _conn(db_path: Optional[str] = None):
    conn = dbmod.connect(db_path)
    ensure_schema(conn)
    return conn


def list_items(status: Optional[str] = "open", db_path: Optional[str] = None) -> list[dict[str, Any]]:
    with _conn(db_path) as conn:
        if status and status != "all":
            rows = conn.execute(
                "SELECT * FROM pending_decisions WHERE status=? ORDER BY created_at ASC", (status,)
            ).fetchall()
        else:
            rows = conn.execute("SELECT * FROM pending_decisions ORDER BY created_at ASC").fetchall()
    return [_row(r) for r in rows]


def get(item_id: str, db_path: Optional[str] = None) -> dict[str, Any]:
    with _conn(db_path) as conn:
        return _row(conn.execute("SELECT * FROM pending_decisions WHERE id=?", (item_id,)).fetchone())


def add(text: str, context: str = "", source: str = "cli", db_path: Optional[str] = None) -> dict[str, Any]:
    text = (text or "").strip()
    if not text:
        raise ValueError("text must not be empty")
    now = dbmod.utc_now()
    item_id = "pnd_" + secrets.token_hex(5)
    with _conn(db_path) as conn:
        conn.execute(
            "INSERT INTO pending_decisions (id, text, context, source, status, created_at, updated_at)"
            " VALUES (?,?,?,?, 'open', ?, ?)",
            (item_id, text, context or "", source or "cli", now, now),
        )
        conn.commit()
    return get(item_id, db_path)


def set_status(item_id: str, status: str, resolution: str = "", actor: str = "cli",
               db_path: Optional[str] = None) -> dict[str, Any]:
    if status not in STATUSES:
        raise ValueError(f"status must be one of {STATUSES}")
    now = dbmod.utc_now()
    with _conn(db_path) as conn:
        if status == "resolved":
            cur = conn.execute(
                "UPDATE pending_decisions SET status='resolved', resolution=?, resolved_at=?, resolved_by=?,"
                " updated_at=? WHERE id=?",
                (resolution or "", now, actor or "", now, item_id),
            )
        else:
            cur = conn.execute(
                "UPDATE pending_decisions SET status='open', resolved_at=NULL, resolved_by='', updated_at=?"
                " WHERE id=?",
                (now, item_id),
            )
        conn.commit()
        if cur.rowcount == 0:
            return {}
    return get(item_id, db_path)


def main(argv: Optional[list[str]] = None) -> int:
    ap = argparse.ArgumentParser(prog="agent5 pending")
    sub = ap.add_subparsers(dest="cmd")
    pl = sub.add_parser("list")
    pl.add_argument("--all", action="store_true")
    pl.add_argument("--status", default="open", choices=["open", "resolved", "all"])
    pl.add_argument("--json", action="store_true")
    pa = sub.add_parser("add")
    pa.add_argument("text")
    pa.add_argument("--context", default="")
    pa.add_argument("--source", default="cli")
    pr = sub.add_parser("resolve")
    pr.add_argument("id")
    pr.add_argument("--note", default="")
    po = sub.add_parser("reopen")
    po.add_argument("id")
    sub.add_parser("init")
    a = ap.parse_args(argv)

    if a.cmd in (None, "list"):
        status = "all" if getattr(a, "all", False) else getattr(a, "status", "open")
        items = list_items(status)
        if getattr(a, "json", False):
            print(json.dumps(items, indent=2, ensure_ascii=False))
            return 0
        if not items:
            print(f"(no {status} items)")
            return 0
        for it in items:
            mark = "[ ]" if it["status"] == "open" else "[x]"
            print(f"{mark} {it['id']}  {it['text']}")
            if it.get("context"):
                print(f"      context: {it['context']}")
            if it["status"] == "resolved" and it.get("resolution"):
                print(f"      resolution: {it['resolution']}")
        return 0
    if a.cmd == "add":
        try:
            print(json.dumps(add(a.text, a.context, a.source), indent=2, ensure_ascii=False))
        except ValueError as e:
            print(f"error: {e}", file=sys.stderr)
            return 2
        return 0
    if a.cmd in ("resolve", "reopen"):
        out = set_status(a.id, "resolved" if a.cmd == "resolve" else "open", getattr(a, "note", ""), "cli")
        if not out:
            print(f"error: pending item not found: {a.id}", file=sys.stderr)
            return 1
        print(json.dumps(out, indent=2, ensure_ascii=False))
        return 0
    if a.cmd == "init":
        with _conn() as conn:
            pass
        print(json.dumps({"ok": True, "table": "pending_decisions"}))
        return 0
    ap.print_help()
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
