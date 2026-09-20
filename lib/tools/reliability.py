#!/usr/bin/env python3
"""Reliability scoring 0-100 from outcome history."""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Any, Optional

_HERE = Path(__file__).resolve().parent


def _ensure_path() -> None:
    lib = str(_HERE.parent)
    if lib not in sys.path:
        sys.path.insert(0, lib)


def update_from_outcome(
    tool_id: str,
    *,
    success: bool,
    latency_ms: Optional[int] = None,
    timeout: bool = False,
    validation_failure: bool = False,
    retried: bool = False,
    db_path: Optional[str] = None,
) -> dict[str, Any]:
    _ensure_path()
    from storage import db as dbmod
    from tools.registry import ensure_schema

    ensure_schema(db_path)
    now = dbmod.utc_now()
    with dbmod.connect(db_path) as conn:
        row = conn.execute("SELECT * FROM tool_reliability WHERE tool_id=?", (tool_id,)).fetchone()
        if not row:
            conn.execute(
                "INSERT INTO tool_reliability (tool_id, reliability_score, updated_at) VALUES (?, 50, ?)",
                (tool_id, now),
            )
            row = conn.execute("SELECT * FROM tool_reliability WHERE tool_id=?", (tool_id,)).fetchone()
        d = dict(row)
        succ = int(d.get("success_count") or 0) + (1 if success else 0)
        fail = int(d.get("failure_count") or 0) + (0 if success else 1)
        to = int(d.get("timeout_count") or 0) + (1 if timeout else 0)
        vf = int(d.get("validation_failure_count") or 0) + (1 if validation_failure else 0)
        rc = int(d.get("retry_count") or 0) + (1 if retried else 0)
        avg = d.get("avg_latency_ms")
        if latency_ms is not None:
            if avg is None:
                avg = float(latency_ms)
            else:
                n = succ + fail
                avg = ((float(avg) * max(n - 1, 0)) + float(latency_ms)) / max(n, 1)
        total = succ + fail
        if total == 0:
            score = 50.0
        else:
            score = 100.0 * succ / total
            score -= min(20.0, to * 5.0)
            score -= min(15.0, vf * 3.0)
            score = max(0.0, min(100.0, score))
        conn.execute(
            """
            UPDATE tool_reliability SET
                success_count=?, failure_count=?, timeout_count=?,
                validation_failure_count=?, retry_count=?,
                reliability_score=?, avg_latency_ms=?, updated_at=?
            WHERE tool_id=?
            """,
            (succ, fail, to, vf, rc, score, avg, now, tool_id),
        )
        conn.commit()
        return {
            "tool_id": tool_id,
            "reliability_score": score,
            "success_count": succ,
            "failure_count": fail,
            "avg_latency_ms": avg,
        }


def get_score(tool_id: str, db_path: Optional[str] = None) -> dict[str, Any]:
    _ensure_path()
    from storage import db as dbmod
    from tools.registry import ensure_schema
    ensure_schema(db_path)
    with dbmod.connect(db_path) as conn:
        row = conn.execute("SELECT * FROM tool_reliability WHERE tool_id=?", (tool_id,)).fetchone()
        return dict(row) if row else {"tool_id": tool_id, "reliability_score": 50}
