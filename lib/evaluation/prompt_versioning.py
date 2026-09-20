"""Prompt versioning."""
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path
from typing import Any, Optional

_HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(_HERE.parent))

from storage import db as dbmod  # noqa: E402
from evaluation import store  # noqa: E402

STATUSES = ("draft", "candidate", "canary", "active", "deprecated", "rejected")


def _hash(content: str) -> str:
    return hashlib.sha256(content.encode()).hexdigest()[:16]


def create_version(prompt_name: str, content: str, *, status: str = "draft",
                   parent_id: Optional[str] = None) -> dict[str, Any]:
    with dbmod.connect() as conn:
        store.ensure_schema(conn)
        row = conn.execute(
            "SELECT COALESCE(MAX(version),0) FROM prompt_versions WHERE prompt_name=?",
            (prompt_name,),
        ).fetchone()
        ver = int(row[0]) + 1
        pid = dbmod.new_id("pv_")
        conn.execute(
            """INSERT INTO prompt_versions
               (id, prompt_name, version, content, content_hash, status, parent_id, created_at)
               VALUES (?,?,?,?,?,?,?,?)""",
            (pid, prompt_name, ver, content, _hash(content), status, parent_id, dbmod.utc_now()),
        )
        conn.commit()
    return get_version(pid)  # type: ignore


def get_version(version_id: str) -> Optional[dict[str, Any]]:
    with dbmod.connect() as conn:
        store.ensure_schema(conn)
        r = conn.execute("SELECT * FROM prompt_versions WHERE id=?", (version_id,)).fetchone()
        return dict(r) if r else None


def list_versions(prompt_name: Optional[str] = None) -> list[dict[str, Any]]:
    with dbmod.connect() as conn:
        store.ensure_schema(conn)
        if prompt_name:
            rows = conn.execute(
                "SELECT * FROM prompt_versions WHERE prompt_name=? ORDER BY version DESC",
                (prompt_name,),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM prompt_versions ORDER BY prompt_name, version DESC"
            ).fetchall()
        return [dict(r) for r in rows]


def set_status(version_id: str, status: str) -> dict[str, Any]:
    if status not in STATUSES:
        raise ValueError(status)
    with dbmod.connect() as conn:
        store.ensure_schema(conn)
        conn.execute("UPDATE prompt_versions SET status=? WHERE id=?", (status, version_id))
        # if activating, deprecate other active for same name
        if status == "active":
            row = conn.execute("SELECT prompt_name FROM prompt_versions WHERE id=?", (version_id,)).fetchone()
            if row:
                conn.execute(
                    "UPDATE prompt_versions SET status='deprecated' WHERE prompt_name=? AND id!=? AND status='active'",
                    (row[0], version_id),
                )
        conn.commit()
    return get_version(version_id)  # type: ignore
