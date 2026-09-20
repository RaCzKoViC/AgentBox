#!/usr/bin/env python3
"""AgentBox v5 memory store — SQLite + filesystem mirror under ~/.local/share/agentbox/v5/memory/."""
from __future__ import annotations

import hashlib
import json
import os
import sys
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Optional

SCOPES = frozenset({"user", "project", "agent", "task"})
KINDS = frozenset({"note", "fact", "preference"})

DEFAULT_DATA_ROOT = Path.home() / ".local" / "share" / "agentbox" / "v5"


def utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def _data_root() -> Path:
    env = os.environ.get("AGENTBOX_V5_HOME")
    if env:
        return Path(env)
    return DEFAULT_DATA_ROOT


def memory_fs_root() -> Path:
    root = _data_root() / "memory"
    root.mkdir(parents=True, exist_ok=True)
    return root


def project_key(project_path: str) -> str:
    """Stable hash key for a project path."""
    p = str(Path(project_path).expanduser().resolve()) if project_path else ""
    return hashlib.sha256(p.encode("utf-8")).hexdigest()[:16]


def _lib_storage():
    here = Path(__file__).resolve().parent
    lib = here.parent
    if str(lib) not in sys.path:
        sys.path.insert(0, str(lib))
    from storage import db as dbmod  # type: ignore

    return dbmod


def _safe_segment(s: str) -> str:
    out = "".join(c if c.isalnum() or c in "-_." else "_" for c in (s or "default"))
    return out[:80] or "default"


def _fs_path(scope: str, scope_key: str, mem_id: str) -> Path:
    return memory_fs_root() / scope / _safe_segment(scope_key or "_") / f"{mem_id}.json"


def _write_fs(row: dict) -> None:
    path = _fs_path(row["scope"], row.get("scope_key") or "", row["id"])
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(row, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def _delete_fs(scope: str, scope_key: str, mem_id: str) -> None:
    path = _fs_path(scope, scope_key or "", mem_id)
    if path.is_file():
        path.unlink()


def add_memory(
    scope: str,
    scope_key: str,
    content: str,
    kind: str = "note",
    meta: Optional[dict] = None,
    expires_at: Optional[str] = None,
    ttl_secs: Optional[int] = None,
    db_path: Optional[str] = None,
) -> dict:
    scope = (scope or "").strip().lower()
    if scope not in SCOPES:
        raise ValueError(f"invalid scope: {scope}; allowed: {sorted(SCOPES)}")
    kind = (kind or "note").strip().lower()
    if kind not in KINDS:
        raise ValueError(f"invalid kind: {kind}; allowed: {sorted(KINDS)}")
    scope_key = scope_key or ""
    if scope == "project" and scope_key and not scope_key.startswith("p_") and len(scope_key) != 16:
        # Accept raw path → hash
        if "/" in scope_key or scope_key.startswith("~") or scope_key.startswith("."):
            scope_key = project_key(scope_key)
    if scope == "user" and not scope_key:
        scope_key = "default"

    now = utc_now()
    exp = expires_at
    if exp is None and ttl_secs is not None and int(ttl_secs) > 0:
        exp = (
            datetime.now(timezone.utc) + timedelta(seconds=int(ttl_secs))
        ).strftime("%Y-%m-%dT%H:%M:%S.%fZ")
    if exp is None and scope == "task":
        # Default task TTL 24h
        exp = (datetime.now(timezone.utc) + timedelta(seconds=86400)).strftime(
            "%Y-%m-%dT%H:%M:%S.%fZ"
        )

    mid = f"m_{uuid.uuid4().hex[:12]}"
    meta_json = json.dumps(meta or {})
    db = _lib_storage()
    with db.connect(db_path) as conn:
        conn.execute(
            """
            INSERT INTO memories (
                id, scope, scope_key, kind, content, meta_json,
                created_at, updated_at, expires_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (mid, scope, scope_key, kind, content, meta_json, now, now, exp),
        )
        conn.commit()
    row = get_memory(mid, db_path=db_path)
    if row:
        _write_fs(row)
    return row  # type: ignore[return-value]


def get_memory(mem_id: str, db_path: Optional[str] = None) -> Optional[dict]:
    db = _lib_storage()
    with db.connect(db_path) as conn:
        row = conn.execute("SELECT * FROM memories WHERE id = ?", (mem_id,)).fetchone()
        return dict(row) if row else None


def list_memories(
    scope: Optional[str] = None,
    scope_key: Optional[str] = None,
    include_expired: bool = False,
    limit: int = 200,
    db_path: Optional[str] = None,
) -> list[dict]:
    db = _lib_storage()
    now = utc_now()
    clauses: list[str] = []
    params: list[Any] = []
    if scope:
        clauses.append("scope = ?")
        params.append(scope)
    if scope_key is not None and scope_key != "":
        clauses.append("scope_key = ?")
        params.append(scope_key)
    if not include_expired:
        clauses.append("(expires_at IS NULL OR expires_at > ?)")
        params.append(now)
    where = (" WHERE " + " AND ".join(clauses)) if clauses else ""
    sql = f"SELECT * FROM memories{where} ORDER BY updated_at DESC LIMIT ?"
    params.append(int(limit))
    with db.connect(db_path) as conn:
        rows = conn.execute(sql, params).fetchall()
        return [dict(r) for r in rows]


def forget_memory(mem_id: str, db_path: Optional[str] = None) -> bool:
    row = get_memory(mem_id, db_path=db_path)
    if not row:
        return False
    db = _lib_storage()
    with db.connect(db_path) as conn:
        conn.execute("DELETE FROM memories WHERE id = ?", (mem_id,))
        conn.commit()
    _delete_fs(row["scope"], row.get("scope_key") or "", mem_id)
    return True


def _print_json(obj: Any) -> None:
    print(json.dumps(obj, indent=2, ensure_ascii=False, default=str))


def main(argv: Optional[list[str]] = None) -> int:
    argv = list(argv if argv is not None else sys.argv[1:])
    if not argv:
        print(
            "usage: store.py add|list|get|forget|project-key ...",
            file=sys.stderr,
        )
        return 2
    cmd = argv[0]
    db_path = os.environ.get("AGENTBOX_V5_DB")
    try:
        if cmd == "add":
            import argparse

            p = argparse.ArgumentParser()
            p.add_argument("--scope", required=True)
            p.add_argument("--key", default="")
            p.add_argument("--content", required=True)
            p.add_argument("--kind", default="note")
            p.add_argument("--ttl", type=int, default=None)
            args = p.parse_args(argv[1:])
            row = add_memory(
                scope=args.scope,
                scope_key=args.key,
                content=args.content,
                kind=args.kind,
                ttl_secs=args.ttl,
                db_path=db_path,
            )
            _print_json(row)
            return 0
        if cmd == "list":
            import argparse

            p = argparse.ArgumentParser()
            p.add_argument("--scope", default=None)
            p.add_argument("--key", default=None)
            p.add_argument("--limit", type=int, default=200)
            args = p.parse_args(argv[1:])
            _print_json(
                list_memories(
                    scope=args.scope,
                    scope_key=args.key,
                    limit=args.limit,
                    db_path=db_path,
                )
            )
            return 0
        if cmd == "get":
            if len(argv) < 2:
                print("get ID", file=sys.stderr)
                return 2
            row = get_memory(argv[1], db_path=db_path)
            if not row:
                print(f"not found: {argv[1]}", file=sys.stderr)
                return 1
            _print_json(row)
            return 0
        if cmd == "forget":
            if len(argv) < 2:
                print("forget ID", file=sys.stderr)
                return 2
            ok = forget_memory(argv[1], db_path=db_path)
            if not ok:
                print(f"not found: {argv[1]}", file=sys.stderr)
                return 1
            print(json.dumps({"forgotten": argv[1]}))
            return 0
        if cmd == "project-key":
            if len(argv) < 2:
                print("project-key PATH", file=sys.stderr)
                return 2
            print(project_key(argv[1]))
            return 0
        print(f"unknown: {cmd}", file=sys.stderr)
        return 2
    except Exception as e:
        print(f"error: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
