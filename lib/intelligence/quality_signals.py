#!/usr/bin/env python3
"""Quality signals — model/agent/task_type success heuristics for routing."""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any, Optional

_HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(_HERE.parent))

from storage import db as dbmod  # noqa: E402


def ensure_schema(conn) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS model_quality (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            provider TEXT NOT NULL,
            model TEXT NOT NULL,
            agent_name TEXT,
            task_type TEXT,
            success INTEGER,
            review_pass INTEGER,
            runtime_seconds REAL,
            cost REAL,
            retries INTEGER,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """
    )


def record(
    *,
    provider: str,
    model: str,
    agent_name: str = "",
    task_type: str = "coding",
    success: bool = True,
    review_pass: Optional[bool] = None,
    runtime_seconds: float = 0.0,
    cost: float = 0.0,
    retries: int = 0,
    db_path: Optional[str] = None,
) -> dict:
    with dbmod.connect(db_path) as conn:
        ensure_schema(conn)
        conn.execute(
            """
            INSERT INTO model_quality
              (provider, model, agent_name, task_type, success, review_pass,
               runtime_seconds, cost, retries, created_at)
            VALUES (?,?,?,?,?,?,?,?,?,?)
            """,
            (
                provider, model, agent_name, task_type,
                1 if success else 0,
                None if review_pass is None else (1 if review_pass else 0),
                runtime_seconds, cost, retries, dbmod.utc_now(),
            ),
        )
        conn.commit()
    return {"ok": True, "provider": provider, "model": model, "success": success}


def summary(db_path: Optional[str] = None) -> dict[str, Any]:
    with dbmod.connect(db_path) as conn:
        ensure_schema(conn)
        rows = conn.execute(
            """
            SELECT provider, model, task_type,
                   COUNT(*) as n,
                   AVG(success) as success_rate,
                   AVG(review_pass) as review_pass_rate,
                   AVG(runtime_seconds) as avg_runtime,
                   AVG(retries) as avg_retries,
                   SUM(cost) as total_cost
            FROM model_quality
            GROUP BY provider, model, task_type
            """
        ).fetchall()
        total = conn.execute("SELECT COUNT(*) FROM model_quality").fetchone()[0]
    return {
        "total_signals": total,
        "by_model": [dict(r) for r in rows],
    }


def main(argv=None) -> int:
    argv = list(argv or sys.argv[1:])
    cmd = argv[0] if argv else "summary"
    if cmd == "summary":
        print(json.dumps(summary(), indent=2, default=str))
        return 0
    print("usage: quality_signals.py summary", file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
