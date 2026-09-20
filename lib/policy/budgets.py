#!/usr/bin/env python3
"""AgentBox v5 — Budget Engine (beta3: scopes + budget_usage table)."""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any, Optional

_HERE = Path(__file__).resolve().parent
for _c in (_HERE.parent / "storage", _HERE.parent.parent / "lib" / "storage"):
    if (_c / "db.py").is_file():
        sys.path.insert(0, str(_c))
        break

import db  # noqa: E402


def _ensure_lib() -> None:
    lib = str(_HERE.parent)
    if lib not in sys.path:
        sys.path.insert(0, lib)


def _tomllib():
    try:
        import tomllib
        return tomllib
    except ImportError:
        import tomli as tomllib  # type: ignore
        return tomllib


def config_paths() -> list[Path]:
    home = Path(os.environ.get("AGENTBOX_V5_HOME", Path.home() / ".local/share/agentbox/v5"))
    lib = Path(os.environ.get("AGENTBOX_V5_LIB", _HERE.parent))
    return [
        home / "config" / "budgets.toml",
        lib.parent / "config" / "budgets.toml",
        _HERE.parent.parent / "config" / "budgets.toml",
    ]


def load_budgets() -> dict[str, Any]:
    tomllib = _tomllib()
    for p in config_paths():
        if p.is_file():
            with open(p, "rb") as f:
                return tomllib.load(f)
    return {
        "global": {
            "daily_cost_usd": 20.0,
            "monthly_cost_usd": 200.0,
            "max_parallel_agents": 4,
            "daily_cost_limit": 50.0,
            "parallel_agent_limit": 4,
            "container_limit": 4,
        },
        "task_defaults": {
            "max_runtime_seconds": 3600,
            "max_agent_runs": 12,
            "max_retries": 2,
            "max_tokens": 150000,
            "max_cost_usd": 5.0,
            "max_files_changed": 50,
            "max_handoffs": 10,
        },
        "defaults": {
            "max_runtime_secs": 1800,
            "max_tokens": 100000,
            "max_cost_usd": 5.0,
            "max_retries": 2,
            "max_files_changed": 50,
            "max_handoffs": 10,
        },
        "stub": {"token_cost": 10, "cost_usd": 0.01},
    }


def effective_limits(task: dict, cfg: Optional[dict] = None) -> dict[str, Any]:
    cfg = cfg or load_budgets()
    defaults = cfg.get("task_defaults") or cfg.get("defaults") or {}
    max_tokens = int(task.get("budget_tokens") or 0) or int(
        defaults.get("max_tokens", 100000)
    )
    max_cost = float(task.get("budget_cost") or 0) or float(
        defaults.get("max_cost_usd", 5.0)
    )
    max_runtime = int(task.get("timeout_secs") or 0) or int(
        defaults.get("max_runtime_seconds")
        or defaults.get("max_runtime_secs", 1800)
    )
    return {
        "max_tokens": max_tokens,
        "max_cost_usd": max_cost,
        "max_runtime_secs": max_runtime,
        "max_retries": int(defaults.get("max_retries", 2)),
        "max_files_changed": int(defaults.get("max_files_changed", 50)),
        "max_handoffs": int(defaults.get("max_handoffs", 10)),
        "max_agent_runs": int(defaults.get("max_agent_runs", 12)),
        "global": cfg.get("global", {}),
        "stub": cfg.get("stub", {"token_cost": 10, "cost_usd": 0.01}),
    }


def usage_of(task: dict) -> dict[str, Any]:
    return {
        "tokens": int(task.get("usage_tokens") or 0),
        "cost": float(task.get("usage_cost") or 0.0),
        "runtime_secs": int(task.get("usage_runtime_secs") or 0),
        "retries": int(task.get("usage_retries") or 0),
        "files_changed": int(task.get("usage_files_changed") or 0),
    }


def check_exceeded(task: dict, cfg: Optional[dict] = None) -> list[str]:
    limits = effective_limits(task, cfg)
    usage = usage_of(task)
    exceeded: list[str] = []
    bt = int(task.get("budget_tokens") or 0)
    bc = float(task.get("budget_cost") or 0.0)
    if bt > 0 and usage["tokens"] >= bt:
        exceeded.append("tokens")
    if bc > 0 and usage["cost"] >= bc:
        exceeded.append("cost")
    if usage["runtime_secs"] >= limits["max_runtime_secs"] > 0:
        exceeded.append("runtime")
    if usage["retries"] >= limits["max_retries"] > 0:
        exceeded.append("retries")
    if usage["files_changed"] >= limits["max_files_changed"] > 0:
        exceeded.append("files_changed")
    return exceeded


def would_exceed(
    task: dict,
    add_tokens: int = 0,
    add_cost: float = 0.0,
    cfg: Optional[dict] = None,
) -> list[str]:
    bt = int(task.get("budget_tokens") or 0)
    bc = float(task.get("budget_cost") or 0.0)
    usage = usage_of(task)
    exceeded: list[str] = []
    if bt > 0 and usage["tokens"] + add_tokens > bt:
        exceeded.append("tokens")
    if bc > 0 and usage["cost"] + add_cost > bc:
        exceeded.append("cost")
    exceeded.extend(x for x in check_exceeded(task, cfg) if x not in exceeded)
    return exceeded


def can_start(task: dict, cfg: Optional[dict] = None) -> tuple[bool, str]:
    cfg = cfg or load_budgets()
    stub = cfg.get("stub", {})
    token_cost = int(stub.get("token_cost", 10))
    cost_usd = float(stub.get("cost_usd", 0.01))
    already = check_exceeded(task, cfg)
    if already:
        return False, f"already exceeded: {','.join(already)}"
    hit = would_exceed(task, add_tokens=token_cost, add_cost=cost_usd, cfg=cfg)
    if hit:
        return False, f"stub would exceed: {','.join(hit)}"
    g = cfg.get("global", {})
    parallel_limit = int(
        g.get("max_parallel_agents") or g.get("parallel_agent_limit") or 0
    )
    if parallel_limit > 0:
        running = db.count_running()
        if running >= parallel_limit:
            return False, f"global parallel_agent_limit={parallel_limit}"
    return True, "ok"


def seed_budgets_table(db_path: Optional[str] = None) -> int:
    """Seed budgets table from config if empty."""
    cfg = load_budgets()
    with db.connect(db_path) as conn:
        n = conn.execute("SELECT COUNT(*) c FROM budgets").fetchone()["c"]
        if n > 0:
            return int(n)
        now = db.utc_now()
        count = 0
        g = cfg.get("global") or {}
        for metric, key in [
            ("max_cost_usd", "daily_cost_usd"),
            ("max_parallel_agents", "max_parallel_agents"),
        ]:
            val = g.get(key) or g.get("daily_cost_limit") if metric == "max_cost_usd" else g.get(key)
            if val is None and metric == "max_parallel_agents":
                val = g.get("parallel_agent_limit", 4)
            if val is None:
                continue
            bid = db.new_id("b_")
            conn.execute(
                """
                INSERT INTO budgets (id, scope_type, scope_id, metric, limit_value, period, enabled, created_at, updated_at)
                VALUES (?, 'global', NULL, ?, ?, ?, 1, ?, ?)
                """,
                (bid, metric, float(val), "daily" if "cost" in metric else None, now, now),
            )
            count += 1
        defaults = cfg.get("task_defaults") or cfg.get("defaults") or {}
        for metric, keys in [
            ("max_tokens", ("max_tokens",)),
            ("max_cost_usd", ("max_cost_usd",)),
            ("max_runtime_seconds", ("max_runtime_seconds", "max_runtime_secs")),
            ("max_retries", ("max_retries",)),
            ("max_files_changed", ("max_files_changed",)),
            ("max_handoffs", ("max_handoffs",)),
            ("max_agent_runs", ("max_agent_runs",)),
        ]:
            val = None
            for k in keys:
                if k in defaults:
                    val = defaults[k]
                    break
            if val is None:
                continue
            bid = db.new_id("b_")
            conn.execute(
                """
                INSERT INTO budgets (id, scope_type, scope_id, metric, limit_value, period, enabled, created_at, updated_at)
                VALUES (?, 'task_defaults', NULL, ?, ?, NULL, 1, ?, ?)
                """,
                (bid, metric, float(val), now, now),
            )
            count += 1
        conn.commit()
        return count


def _sum_usage(
    scope_type: str,
    scope_id: Optional[str],
    metric: str,
    db_path: Optional[str] = None,
) -> float:
    with db.connect(db_path) as conn:
        if scope_id is None:
            row = conn.execute(
                """
                SELECT COALESCE(SUM(value),0) s FROM budget_usage
                WHERE scope_type=? AND scope_id IS NULL AND metric=?
                """,
                (scope_type, metric),
            ).fetchone()
        else:
            row = conn.execute(
                """
                SELECT COALESCE(SUM(value),0) s FROM budget_usage
                WHERE scope_type=? AND scope_id=? AND metric=?
                """,
                (scope_type, scope_id, metric),
            ).fetchone()
        return float(row["s"] or 0)


def _limit_for(
    scope_type: str,
    scope_id: Optional[str],
    metric: str,
    db_path: Optional[str] = None,
) -> Optional[float]:
    with db.connect(db_path) as conn:
        # Exact scope
        if scope_id is not None:
            row = conn.execute(
                """
                SELECT limit_value FROM budgets
                WHERE enabled=1 AND scope_type=? AND scope_id=? AND metric=?
                LIMIT 1
                """,
                (scope_type, scope_id, metric),
            ).fetchone()
            if row:
                return float(row["limit_value"])
        # Defaults / global
        for st in (scope_type, "task_defaults", "global"):
            row = conn.execute(
                """
                SELECT limit_value FROM budgets
                WHERE enabled=1 AND scope_type=? AND metric=?
                ORDER BY CASE WHEN scope_id IS NULL THEN 1 ELSE 0 END
                LIMIT 1
                """,
                (st, metric),
            ).fetchone()
            if row:
                return float(row["limit_value"])
    # Fall back to config
    cfg = load_budgets()
    if scope_type == "task" or scope_type == "task_defaults":
        d = cfg.get("task_defaults") or cfg.get("defaults") or {}
        mapping = {
            "max_tokens": d.get("max_tokens"),
            "max_cost_usd": d.get("max_cost_usd"),
            "max_runtime_seconds": d.get("max_runtime_seconds") or d.get("max_runtime_secs"),
            "max_handoffs": d.get("max_handoffs", 10),
            "max_retries": d.get("max_retries"),
            "max_files_changed": d.get("max_files_changed"),
            "max_agent_runs": d.get("max_agent_runs"),
        }
        if metric in mapping and mapping[metric] is not None:
            return float(mapping[metric])
    g = cfg.get("global") or {}
    if metric in ("max_cost_usd", "daily_cost_usd"):
        return float(g.get("daily_cost_usd") or g.get("daily_cost_limit") or 20)
    if metric == "max_parallel_agents":
        return float(g.get("max_parallel_agents") or g.get("parallel_agent_limit") or 4)
    return None


def check_budget(
    scope_type: str,
    scope_id: Optional[str],
    metric: str,
    requested_value: float = 1.0,
    db_path: Optional[str] = None,
) -> dict[str, Any]:
    """Check budget before costly op. Returns {ok, remaining, limit, used, reason}."""
    try:
        seed_budgets_table(db_path=db_path)
    except Exception:
        pass
    limit = _limit_for(scope_type, scope_id, metric, db_path=db_path)
    used = _sum_usage(scope_type, scope_id, metric, db_path=db_path)
    # Also count agent_handoffs rows; take the max so either source enforces
    if metric == "max_handoffs" and scope_id:
        with db.connect(db_path) as conn:
            try:
                hc = float(
                    conn.execute(
                        "SELECT COUNT(*) c FROM agent_handoffs WHERE task_id=?",
                        (scope_id,),
                    ).fetchone()["c"]
                )
                used = max(used, hc)
            except Exception:
                pass
    if limit is None:
        result = {
            "ok": True,
            "remaining": None,
            "limit": None,
            "used": used,
            "requested": requested_value,
            "reason": "no limit configured",
            "metric": metric,
            "scope_type": scope_type,
            "scope_id": scope_id,
        }
    else:
        remaining = limit - used
        ok = (used + requested_value) <= limit
        result = {
            "ok": ok,
            "remaining": remaining,
            "limit": limit,
            "used": used,
            "requested": requested_value,
            "reason": "ok" if ok else f"budget exceeded: {metric} used={used}+{requested_value}>{limit}",
            "metric": metric,
            "scope_type": scope_type,
            "scope_id": scope_id,
        }
    try:
        db.emit_event(
            kind="budget.checked",
            message=f"{scope_type}/{scope_id} {metric}: {result['reason']}",
            task_id=scope_id if scope_type == "task" else None,
            payload=result,
            db_path=db_path,
        )
        _ensure_lib()
        from observability.metrics import record_metric  # type: ignore
        record_metric("agentbox_budget_checked", 1.0, labels={"metric": metric, "ok": str(result["ok"])}, db_path=db_path)
        if not result["ok"]:
            record_metric("agentbox_budget_exceeded_total", 1.0, labels={"metric": metric}, db_path=db_path)
            db.emit_event(
                kind="budget.exceeded",
                message=result["reason"],
                task_id=scope_id if scope_type == "task" else None,
                payload=result,
                db_path=db_path,
            )
        elif limit is not None and result["remaining"] is not None and result["remaining"] < limit * 0.2:
            db.emit_event(
                kind="budget.warning",
                message=f"{metric} remaining={result['remaining']}",
                task_id=scope_id if scope_type == "task" else None,
                payload=result,
                db_path=db_path,
            )
    except Exception:
        pass
    return result


def record_usage(
    scope_type: str,
    scope_id: Optional[str],
    metric: str,
    value: float,
    task_id: Optional[str] = None,
    run_id: Optional[str] = None,
    db_path: Optional[str] = None,
) -> dict:
    with db.connect(db_path) as conn:
        cur = conn.execute(
            """
            INSERT INTO budget_usage (scope_type, scope_id, metric, value, task_id, run_id, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (scope_type, scope_id, metric, float(value), task_id or scope_id, run_id, db.utc_now()),
        )
        conn.commit()
        row_id = int(cur.lastrowid)
    try:
        db.emit_event(
            kind="budget.consumed",
            message=f"{metric}+={value}",
            task_id=task_id or (scope_id if scope_type == "task" else None),
            payload={"metric": metric, "value": value, "scope_type": scope_type, "scope_id": scope_id},
            db_path=db_path,
        )
        _ensure_lib()
        from observability.metrics import record_metric  # type: ignore
        if metric in ("max_tokens", "tokens"):
            record_metric("agentbox_budget_usage_tokens", float(value), db_path=db_path)
        if metric in ("max_cost_usd", "cost"):
            record_metric("agentbox_budget_usage_cost", float(value), db_path=db_path)
    except Exception:
        pass
    return {"id": row_id, "metric": metric, "value": value}


def remaining_budget(
    scope_type: str,
    scope_id: Optional[str],
    metric: str,
    db_path: Optional[str] = None,
) -> Optional[float]:
    chk = check_budget(scope_type, scope_id, metric, requested_value=0, db_path=db_path)
    return chk.get("remaining")


def budget_summary(db_path: Optional[str] = None) -> dict[str, Any]:
    try:
        seed_budgets_table(db_path=db_path)
    except Exception:
        pass
    cfg = load_budgets()
    with db.connect(db_path) as conn:
        budgets = [dict(r) for r in conn.execute("SELECT * FROM budgets WHERE enabled=1").fetchall()]
        usage_rows = [dict(r) for r in conn.execute(
            "SELECT scope_type, scope_id, metric, SUM(value) AS total FROM budget_usage GROUP BY scope_type, scope_id, metric"
        ).fetchall()]
        task_usage = conn.execute(
            """
            SELECT COALESCE(SUM(usage_tokens),0) AS tokens,
                   COALESCE(SUM(usage_cost),0) AS cost,
                   COALESCE(SUM(usage_runtime_secs),0) AS runtime
            FROM tasks
            """
        ).fetchone()
    warnings = []
    for b in budgets:
        used = 0.0
        for u in usage_rows:
            if u["metric"] == b["metric"] and u["scope_type"] == b["scope_type"]:
                if (u["scope_id"] or None) == (b["scope_id"] or None):
                    used = float(u["total"] or 0)
        lim = float(b["limit_value"])
        if lim > 0 and used / lim >= 0.8:
            warnings.append({
                "metric": b["metric"],
                "used": used,
                "limit": lim,
                "pct": round(100 * used / lim, 1),
            })
    return {
        "config": cfg,
        "budgets": budgets,
        "usage_by_scope": usage_rows,
        "usage_total": {
            "tokens": int(task_usage["tokens"]),
            "cost": float(task_usage["cost"]),
            "runtime_secs": int(task_usage["runtime"]),
        },
        "warnings": warnings,
    }


def pause_budget(task_id: str, reason: str, db_path: Optional[str] = None) -> dict:
    # Prefer budget_paused (beta3) but keep paused_budget for alpha3 compat
    try:
        task = db.set_task_status(task_id, "budget_paused", db_path=db_path)
    except Exception:
        task = db.set_task_status(task_id, "paused_budget", db_path=db_path)
    db.emit_event(
        kind="budget.exceeded",
        message=reason,
        task_id=task_id,
        payload={"reason": reason},
        db_path=db_path,
    )
    try:
        _ensure_lib()
        from observability.metrics import record_metric  # type: ignore
        record_metric("agentbox_budget_exceeded_total", 1.0, db_path=db_path)
    except Exception:
        pass
    return task


def consume(
    task_id: str,
    tokens: int = 0,
    cost: float = 0.0,
    runtime_secs: int = 0,
    retries: int = 0,
    files_changed: int = 0,
    db_path: Optional[str] = None,
) -> dict:
    task = db.get_task(task_id, db_path)
    if not task:
        raise KeyError(f"task not found: {task_id}")
    now = db.utc_now()
    with db.connect(db_path) as conn:
        conn.execute(
            """
            UPDATE tasks SET
                usage_tokens = usage_tokens + ?,
                usage_cost = usage_cost + ?,
                usage_runtime_secs = usage_runtime_secs + ?,
                usage_retries = usage_retries + ?,
                usage_files_changed = usage_files_changed + ?,
                updated_at = ?
            WHERE id = ?
            """,
            (tokens, cost, runtime_secs, retries, files_changed, now, task_id),
        )
        conn.commit()
    if tokens:
        record_usage("task", task_id, "max_tokens", tokens, task_id=task_id, db_path=db_path)
    if cost:
        record_usage("task", task_id, "max_cost_usd", cost, task_id=task_id, db_path=db_path)
    task = db.get_task(task_id, db_path)
    hit = check_exceeded(task)
    bt = int(task.get("budget_tokens") or 0)
    bc = float(task.get("budget_cost") or 0.0)
    if bt > 0 and int(task.get("usage_tokens") or 0) > bt and "tokens" not in hit:
        hit.append("tokens")
    if bc > 0 and float(task.get("usage_cost") or 0) > bc and "cost" not in hit:
        hit.append("cost")
    if hit:
        return pause_budget(task_id, f"exceeded after consume: {','.join(hit)}", db_path=db_path)
    return task


def set_task_budget(
    task_id: str,
    tokens: Optional[int] = None,
    cost: Optional[float] = None,
    db_path: Optional[str] = None,
) -> dict:
    task = db.get_task(task_id, db_path)
    if not task:
        raise KeyError(f"task not found: {task_id}")
    now = db.utc_now()
    with db.connect(db_path) as conn:
        if tokens is not None:
            conn.execute(
                "UPDATE tasks SET budget_tokens = ?, updated_at = ? WHERE id = ?",
                (int(tokens), now, task_id),
            )
            # Also upsert budgets row
            conn.execute(
                """
                INSERT INTO budgets (id, scope_type, scope_id, metric, limit_value, period, enabled, created_at, updated_at)
                VALUES (?, 'task', ?, 'max_tokens', ?, NULL, 1, ?, ?)
                """,
                (db.new_id("b_"), task_id, float(tokens), now, now),
            )
        if cost is not None:
            conn.execute(
                "UPDATE tasks SET budget_cost = ?, updated_at = ? WHERE id = ?",
                (float(cost), now, task_id),
            )
            conn.execute(
                """
                INSERT INTO budgets (id, scope_type, scope_id, metric, limit_value, period, enabled, created_at, updated_at)
                VALUES (?, 'task', ?, 'max_cost_usd', ?, NULL, 1, ?, ?)
                """,
                (db.new_id("b_"), task_id, float(cost), now, now),
            )
        conn.commit()
    return db.get_task(task_id, db_path)


def show_global(db_path: Optional[str] = None) -> dict:
    return budget_summary(db_path=db_path)


def show_task(task_id: str, db_path: Optional[str] = None) -> dict:
    task = db.get_task(task_id, db_path)
    if not task:
        raise KeyError(f"task not found: {task_id}")
    cfg = load_budgets()
    handoff_chk = check_budget("task", task_id, "max_handoffs", 0, db_path=db_path)
    return {
        "task_id": task_id,
        "status": task["status"],
        "limits": effective_limits(task, cfg),
        "usage": usage_of(task),
        "budget_tokens": task.get("budget_tokens"),
        "budget_cost": task.get("budget_cost"),
        "exceeded": check_exceeded(task, cfg),
        "can_start": can_start(task, cfg),
        "handoffs": handoff_chk,
    }


def list_usage(limit: int = 100, db_path: Optional[str] = None) -> list[dict]:
    with db.connect(db_path) as conn:
        rows = conn.execute(
            "SELECT * FROM budget_usage ORDER BY id DESC LIMIT ?",
            (limit,),
        ).fetchall()
        return [dict(r) for r in rows]


def _print(obj: Any) -> None:
    print(json.dumps(obj, indent=2, ensure_ascii=False, default=str))


def main(argv: Optional[list[str]] = None) -> int:
    argv = list(argv if argv is not None else sys.argv[1:])
    db_path = os.environ.get("AGENTBOX_V5_DB")
    if not argv:
        print("usage: budgets.py show|task ID|usage|set|check|consume|seed|pause", file=sys.stderr)
        return 2
    cmd = argv[0]
    try:
        if cmd == "show":
            _print(show_global(db_path))
            return 0
        if cmd == "task":
            if len(argv) < 2:
                print("task ID required", file=sys.stderr)
                return 2
            _print(show_task(argv[1], db_path))
            return 0
        if cmd == "usage":
            _print(list_usage(db_path=db_path))
            return 0
        if cmd == "seed":
            n = seed_budgets_table(db_path=db_path)
            _print({"seeded": n})
            return 0
        if cmd == "set":
            if len(argv) < 4:
                print("set ID tokens N | set ID cost N", file=sys.stderr)
                return 2
            tid, kind, val = argv[1], argv[2], argv[3]
            if kind == "tokens":
                _print(set_task_budget(tid, tokens=int(val), db_path=db_path))
            elif kind == "cost":
                _print(set_task_budget(tid, cost=float(val), db_path=db_path))
            else:
                print("set ID tokens|cost N", file=sys.stderr)
                return 2
            return 0
        if cmd == "check":
            if len(argv) < 2:
                print("check ID | check --scope task --id ID --metric max_handoffs", file=sys.stderr)
                return 2
            if argv[1].startswith("--"):
                import argparse
                p = argparse.ArgumentParser()
                p.add_argument("--scope", default="task")
                p.add_argument("--id", default=None)
                p.add_argument("--metric", default="max_tokens")
                p.add_argument("--value", type=float, default=1.0)
                args = p.parse_args(argv[1:])
                r = check_budget(args.scope, args.id, args.metric, args.value, db_path=db_path)
                _print(r)
                return 0 if r["ok"] else 1
            task = db.get_task(argv[1], db_path)
            if not task:
                print(f"not found: {argv[1]}", file=sys.stderr)
                return 1
            ok, reason = can_start(task)
            _print({"ok": ok, "reason": reason, "exceeded": check_exceeded(task)})
            return 0 if ok else 1
        if cmd == "consume":
            import argparse
            p = argparse.ArgumentParser()
            p.add_argument("task_id")
            p.add_argument("--tokens", type=int, default=0)
            p.add_argument("--cost", type=float, default=0.0)
            p.add_argument("--runtime", type=int, default=0)
            args = p.parse_args(argv[1:])
            _print(consume(args.task_id, tokens=args.tokens, cost=args.cost,
                           runtime_secs=args.runtime, db_path=db_path))
            return 0
        if cmd == "pause":
            if len(argv) < 2:
                print("pause ID [reason]", file=sys.stderr)
                return 2
            reason = argv[2] if len(argv) > 2 else "manual pause"
            _print(pause_budget(argv[1], reason, db_path=db_path))
            return 0
        print(f"unknown: {cmd}", file=sys.stderr)
        return 2
    except Exception as e:
        print(f"error: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
