"""Performance baselines."""
from __future__ import annotations

import json
import sys
from typing import Any, Optional

from pathlib import Path
_HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(_HERE.parent))

from storage import db as dbmod  # noqa: E402
from evaluation import store  # noqa: E402


def set_baseline(suite_id: str, summary: dict[str, Any], *,
                 subject_type: str = "platform", subject_id: str = "agentbox",
                 version: str = "1", evaluation_run_id: Optional[str] = None) -> dict[str, Any]:
    bid = dbmod.new_id("bl_")
    with dbmod.connect() as conn:
        store.ensure_schema(conn)
        # keep latest: soft-replace by deleting older for same suite+subject
        conn.execute(
            "DELETE FROM baselines WHERE suite_id=? AND subject_type=? AND subject_id=?",
            (suite_id, subject_type, subject_id),
        )
        conn.execute(
            """INSERT INTO baselines
               (id, suite_id, subject_type, subject_id, version, summary_json, evaluation_run_id, created_at)
               VALUES (?,?,?,?,?,?,?,?)""",
            (bid, suite_id, subject_type, subject_id, version,
             json.dumps(summary, default=str), evaluation_run_id, dbmod.utc_now()),
        )
        conn.commit()
    return get_baseline(suite_id, subject_type=subject_type, subject_id=subject_id) or {"id": bid}


def get_baseline(suite_id: Optional[str] = None, *,
                 subject_type: str = "platform", subject_id: str = "agentbox") -> Optional[dict[str, Any]]:
    with dbmod.connect() as conn:
        store.ensure_schema(conn)
        if suite_id:
            r = conn.execute(
                """SELECT * FROM baselines WHERE suite_id=? AND subject_type=? AND subject_id=?
                   ORDER BY created_at DESC LIMIT 1""",
                (suite_id, subject_type, subject_id),
            ).fetchone()
        else:
            r = conn.execute(
                "SELECT * FROM baselines ORDER BY created_at DESC LIMIT 1"
            ).fetchone()
        if not r:
            return None
        d = dict(r)
        d["summary"] = json.loads(d.pop("summary_json") or "{}")
        return d


def list_baselines(limit: int = 20) -> list[dict[str, Any]]:
    with dbmod.connect() as conn:
        store.ensure_schema(conn)
        rows = conn.execute(
            "SELECT * FROM baselines ORDER BY created_at DESC LIMIT ?", (limit,)
        ).fetchall()
        out = []
        for r in rows:
            d = dict(r)
            d["summary"] = json.loads(d.pop("summary_json") or "{}")
            out.append(d)
        return out
