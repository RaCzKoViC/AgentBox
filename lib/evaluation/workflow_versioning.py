"""Workflow versioning."""
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


def _hash(definition: Any) -> str:
    raw = json.dumps(definition, sort_keys=True, default=str)
    return hashlib.sha256(raw.encode()).hexdigest()[:16]


def create_version(workflow_name: str, definition: Any, *, status: str = "draft",
                   parent_id: Optional[str] = None) -> dict[str, Any]:
    with dbmod.connect() as conn:
        store.ensure_schema(conn)
        row = conn.execute(
            "SELECT COALESCE(MAX(version),0) FROM workflow_versions WHERE workflow_name=?",
            (workflow_name,),
        ).fetchone()
        ver = int(row[0]) + 1
        wid = dbmod.new_id("wv_")
        conn.execute(
            """INSERT INTO workflow_versions
               (id, workflow_name, version, definition_json, content_hash, status, parent_id, created_at)
               VALUES (?,?,?,?,?,?,?,?)""",
            (wid, workflow_name, ver, json.dumps(definition, default=str),
             _hash(definition), status, parent_id, dbmod.utc_now()),
        )
        conn.commit()
    return get_version(wid)  # type: ignore


def get_version(version_id: str) -> Optional[dict[str, Any]]:
    with dbmod.connect() as conn:
        store.ensure_schema(conn)
        r = conn.execute("SELECT * FROM workflow_versions WHERE id=?", (version_id,)).fetchone()
        if not r:
            return None
        d = dict(r)
        d["definition"] = json.loads(d.pop("definition_json") or "{}")
        return d


def list_versions(workflow_name: Optional[str] = None) -> list[dict[str, Any]]:
    with dbmod.connect() as conn:
        store.ensure_schema(conn)
        if workflow_name:
            rows = conn.execute(
                "SELECT * FROM workflow_versions WHERE workflow_name=? ORDER BY version DESC",
                (workflow_name,),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM workflow_versions ORDER BY workflow_name, version DESC"
            ).fetchall()
        out = []
        for r in rows:
            d = dict(r)
            d["definition"] = json.loads(d.pop("definition_json") or "{}")
            out.append(d)
        return out
