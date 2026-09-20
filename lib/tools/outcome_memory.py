#!/usr/bin/env python3
"""Record tool call outcomes for reliability + experience."""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any, Optional

_HERE = Path(__file__).resolve().parent


def _ensure_path() -> None:
    lib = str(_HERE.parent)
    if lib not in sys.path:
        sys.path.insert(0, lib)


def record_outcome(
    tool_id: str,
    *,
    call_id: Optional[str] = None,
    capability: str = "",
    task_type: str = "",
    input_class: str = "",
    success: bool = False,
    failure_type: Optional[str] = None,
    latency_ms: Optional[int] = None,
    worker_id: Optional[str] = None,
    provider: str = "builtin",
    meta: Optional[dict] = None,
    db_path: Optional[str] = None,
) -> dict[str, Any]:
    _ensure_path()
    from storage import db as dbmod
    from tools.registry import ensure_schema
    from tools import reliability

    ensure_schema(db_path)
    oid = dbmod.new_id("to_")
    now = dbmod.utc_now()
    with dbmod.connect(db_path) as conn:
        conn.execute(
            """
            INSERT INTO tool_outcomes (
                id, tool_id, call_id, capability, task_type, input_class,
                success, failure_type, latency_ms, worker_id, provider, meta_json, created_at
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)
            """,
            (
                oid, tool_id, call_id, capability, task_type, input_class,
                1 if success else 0, failure_type, latency_ms, worker_id, provider,
                json.dumps(meta or {}), now,
            ),
        )
        conn.commit()
    reliability.update_from_outcome(
        tool_id,
        success=success,
        latency_ms=latency_ms,
        timeout=(failure_type == "timeout"),
        validation_failure=(failure_type == "validation"),
        db_path=db_path,
    )
    # soft wire to experience memory
    try:
        from intelligence.experience_memory import record_experience
        record_experience(
            task_type=task_type or "tool_call",
            provider=provider,
            model=tool_id,
            outcome="success" if success else "failure",
            notes=f"tool={tool_id} cap={capability} fail={failure_type or ''}",
            runtime_seconds=(latency_ms or 0) / 1000.0,
            db_path=db_path,
        )
    except Exception:
        pass
    return {"id": oid, "tool_id": tool_id, "success": success}


def list_outcomes(tool_id: Optional[str] = None, limit: int = 50, db_path: Optional[str] = None) -> list[dict]:
    _ensure_path()
    from storage import db as dbmod
    from tools.registry import ensure_schema
    ensure_schema(db_path)
    with dbmod.connect(db_path) as conn:
        if tool_id:
            rows = conn.execute(
                "SELECT * FROM tool_outcomes WHERE tool_id=? ORDER BY created_at DESC LIMIT ?",
                (tool_id, limit),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM tool_outcomes ORDER BY created_at DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [dict(r) for r in rows]
