#!/usr/bin/env python3
"""AgentBox v5 metrics recorder (beta2)."""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any, Optional


class MetricNames:
    """Canonical counter / gauge names."""

    TASKS_CREATED = "tasks.created"
    TASKS_COMPLETED = "tasks.completed"
    TASKS_FAILED = "tasks.failed"
    TASKS_BLOCKED = "tasks.blocked"
    RUNS_STARTED = "runs.started"
    RUNS_FINISHED = "runs.finished"
    AGENTS_ACTIVE = "agents.active"
    AGENTS_BUSY = "agents.busy"
    HANDOFFS_CREATED = "handoffs.created"
    HANDOFFS_COMPLETED = "handoffs.completed"
    HANDOFFS_FAILED = "handoffs.failed"
    HANDOFFS_REJECTED = "handoffs.rejected"
    PROVIDER_REQUESTS = "provider.requests"
    PROVIDER_ERRORS = "provider.errors"
    QUEUE_DEPTH = "queue.depth"
    QUEUE_READY = "queue.ready"
    # Resource gauges
    RES_CPU_PCT = "resource.cpu_pct"
    RES_RAM_PCT = "resource.ram_pct"
    RES_LOADAVG = "resource.loadavg"
    RES_DISK_PCT = "resource.disk_pct"
    RES_QUEUE_DEPTH = "resource.queue_depth"
    RES_RUNNING_AGENTS = "resource.running_agents"
    RES_RUNNING_TASKS = "resource.running_tasks"
    # beta3
    POLICY_CHECKS = "agentbox_policy_checks_total"
    POLICY_DENIES = "agentbox_policy_denies_total"
    APPROVALS_PENDING = "agentbox_approvals_pending"
    APPROVALS_TOTAL = "agentbox_approvals_total"
    RISK_ASSESSMENTS = "agentbox_risk_assessments_total"
    RISK_HIGH = "agentbox_risk_high_total"
    BUDGET_TOKENS = "agentbox_budget_usage_tokens"
    BUDGET_COST = "agentbox_budget_usage_cost"
    BUDGET_EXCEEDED = "agentbox_budget_exceeded_total"


def _ensure_path() -> None:
    lib = str(Path(__file__).resolve().parent.parent)
    if lib not in sys.path:
        sys.path.insert(0, lib)


def _db():
    _ensure_path()
    from storage import db as dbmod  # type: ignore

    return dbmod


def record_metric(
    name: str,
    value: float,
    labels: Optional[dict] = None,
    db_path: Optional[str] = None,
) -> int:
    """Insert a metric row. Returns row id."""
    db = _db()
    now = db.utc_now()
    with db.connect(db_path) as conn:
        cur = conn.execute(
            """
            INSERT INTO metrics (metric_name, metric_value, labels_json, created_at)
            VALUES (?, ?, ?, ?)
            """,
            (name, float(value), json.dumps(labels or {}), now),
        )
        conn.commit()
        return int(cur.lastrowid)


def list_metrics(
    name: Optional[str] = None,
    limit: int = 100,
    db_path: Optional[str] = None,
) -> list[dict]:
    db = _db()
    with db.connect(db_path) as conn:
        if name:
            rows = conn.execute(
                """
                SELECT * FROM metrics WHERE metric_name = ?
                ORDER BY id DESC LIMIT ?
                """,
                (name, limit),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM metrics ORDER BY id DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [dict(r) for r in rows]


def latest_by_name(db_path: Optional[str] = None) -> dict[str, dict]:
    """Return latest row per metric_name."""
    db = _db()
    with db.connect(db_path) as conn:
        rows = conn.execute(
            """
            SELECT m.* FROM metrics m
            INNER JOIN (
                SELECT metric_name, MAX(id) AS mid FROM metrics GROUP BY metric_name
            ) t ON m.id = t.mid
            ORDER BY m.metric_name
            """
        ).fetchall()
        return {r["metric_name"]: dict(r) for r in rows}


def summary(db_path: Optional[str] = None) -> dict[str, Any]:
    """Aggregate useful counters for CLI dashboard."""
    latest = latest_by_name(db_path=db_path)
    # Sum counters (all-time from DB)
    db = _db()
    counters: dict[str, float] = {}
    with db.connect(db_path) as conn:
        for row in conn.execute(
            "SELECT metric_name, SUM(metric_value) AS s FROM metrics GROUP BY metric_name"
        ).fetchall():
            counters[row["metric_name"]] = float(row["s"] or 0)
    return {"latest": latest, "sums": counters}


def main(argv: Optional[list[str]] = None) -> int:
    argv = list(argv if argv is not None else sys.argv[1:])
    db_path = os.environ.get("AGENTBOX_V5_DB")
    if not argv or argv[0] in ("show", "summary"):
        print(json.dumps(summary(db_path=db_path), indent=2, default=str))
        return 0
    if argv[0] == "list":
        name = None
        limit = 50
        i = 1
        while i < len(argv):
            if argv[i] == "--name" and i + 1 < len(argv):
                name = argv[i + 1]
                i += 2
            elif argv[i] == "--limit" and i + 1 < len(argv):
                limit = int(argv[i + 1])
                i += 2
            else:
                i += 1
        print(json.dumps(list_metrics(name=name, limit=limit, db_path=db_path), indent=2, default=str))
        return 0
    if argv[0] == "record":
        import argparse

        p = argparse.ArgumentParser()
        p.add_argument("name")
        p.add_argument("value", type=float)
        p.add_argument("--label", action="append", default=[])
        args = p.parse_args(argv[1:])
        labels = {}
        for item in args.label:
            if "=" in item:
                k, v = item.split("=", 1)
                labels[k] = v
        mid = record_metric(args.name, args.value, labels=labels, db_path=db_path)
        print(mid)
        return 0
    print("usage: metrics.py show|list|record NAME VALUE", file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main())
