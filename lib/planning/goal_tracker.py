#!/usr/bin/env python3
"""Goal progress tracking — weighted / critical-path aware."""
from __future__ import annotations

from typing import Any, Optional

from planning import store
from planning.task_graph import critical_path, topological_order


def goal_progress(goal_id: str, db_path: Optional[str] = None) -> dict[str, Any]:
    goal = store.get_goal(goal_id, db_path=db_path)
    if not goal:
        raise KeyError(goal_id)
    plans = store.list_plans(goal_id, db_path=db_path)
    plan = None
    for p in plans:
        if p.get("status") in ("approved", "active", "running", "draft", "awaiting_approval"):
            plan = store.get_plan(p["id"], db_path=db_path)
            if plan:
                break
    if not plan and plans:
        plan = store.get_plan(plans[0]["id"], db_path=db_path)

    nodes = (plan or {}).get("nodes") or []
    total = len(nodes) or 1
    completed = [n for n in nodes if (n.get("status") or "") in ("completed", "done", "success")]
    blocked = [n for n in nodes if (n.get("status") or "") in ("blocked", "failed")]
    active = [n for n in nodes if (n.get("status") or "") in ("running", "active", "in_progress")]
    pending = [n for n in nodes if (n.get("status") or "pending") in ("pending", "ready", "queued")]

    # weighted percent
    weights = [float(n.get("meta", {}).get("weight") or 1.0) for n in nodes] or [1.0]
    done_w = sum(w for n, w in zip(nodes, weights) if (n.get("status") or "") in ("completed", "done", "success"))
    percent = round(100.0 * done_w / max(sum(weights), 1e-9), 1)

    cp_percent = 0.0
    try:
        graph = plan.get("graph") if plan else {"nodes": nodes, "edges": []}
        if not graph.get("nodes"):
            graph = {"nodes": [
                {**n, "id": n["id"], "dependencies": n.get("dependencies") or [],
                 "estimated_runtime": n.get("estimated_runtime") or 60}
                for n in nodes
            ], "edges": []}
        cp = critical_path(graph)
        path_ids = set(cp.get("path") or [])
        if path_ids:
            done_cp = sum(1 for n in nodes if n["id"] in path_ids and (n.get("status") or "") in ("completed", "done", "success"))
            cp_percent = round(100.0 * done_cp / len(path_ids), 1)
    except Exception:
        cp = {"path": [], "seconds": 0}

    return {
        "goal_id": goal_id,
        "status": goal.get("status"),
        "percent": percent,
        "critical_path_percent": cp_percent,
        "blocked": len(blocked),
        "active": len(active),
        "completed": len(completed),
        "pending": len(pending),
        "total": len(nodes),
        "plan_id": (plan or {}).get("id"),
        "plan_version": (plan or {}).get("version"),
        "critical_path": cp.get("path") if isinstance(cp, dict) else [],
    }
