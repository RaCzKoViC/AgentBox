#!/usr/bin/env python3
"""Plan revision — create new plan version; may insert retry/research subtasks."""
from __future__ import annotations

from typing import Any, Optional

from planning import store
from planning.task_graph import build_graph, validate_graph, ordered_nodes, critical_path
from planning.plan_quality import score_plan
from planning.retry_strategy import classify_failure, decide_retry


def revise_plan(
    plan_id: str,
    reason: str = "execution issue",
    observations: Optional[dict] = None,
    constraints: Optional[dict] = None,
    insert_retry: bool = True,
    db_path: Optional[str] = None,
) -> dict[str, Any]:
    current = store.get_plan(plan_id, db_path=db_path)
    if not current:
        raise KeyError(f"plan not found: {plan_id}")
    goal_id = current["goal_id"]
    obs = observations or {}
    cons = constraints or {}

    nodes = []
    for n in (current.get("nodes") or []):
        nodes.append({
            "id": n["id"],
            "title": n.get("title") or n["id"],
            "description": n.get("description") or "",
            "agent": n.get("agent") or n.get("assigned_agent") or "coder",
            "type": n.get("node_type") or n.get("type") or "stage",
            "dependencies": list(n.get("dependencies") or []),
            "order_index": int(n.get("order_index") or 0),
            "estimated_runtime": float(n.get("estimated_runtime") or 60),
            "estimated_cost": float(n.get("estimated_cost") or 0.05),
            "risk": n.get("risk") or "MEDIUM",
            "critical": bool(n.get("critical", True)),
            "parallel_safe": bool(n.get("parallel_safe")),
            "meta": dict(n.get("meta") or {}),
            "status": n.get("status") or "pending",
        })

    changes: dict[str, Any] = {"added": [], "removed": [], "reason": reason}
    failure_class = classify_failure(obs.get("error") or reason, obs)
    retry_dec = decide_retry(failure_class, attempt=int(obs.get("attempt") or 1))

    if insert_retry and retry_dec.get("action") in ("retry", "debugger", "replan", "researcher", "fallback", "failover"):
        from storage import db as dbmod
        failed_id = obs.get("task_id") or obs.get("node_id")
        deps = [failed_id] if failed_id else ([nodes[-1]["id"]] if nodes else [])
        agent = retry_dec.get("fallback_agent") or ("researcher" if failure_class == "DEPENDENCY" else "debugger")
        new_id = dbmod.new_id("n_")
        new_node = {
            "id": new_id,
            "title": retry_dec.get("title") or f"Retry: {failure_class.lower()}",
            "description": f"Auto-inserted by plan revision ({failure_class}): {reason}",
            "agent": agent,
            "type": "retry",
            "dependencies": deps,
            "order_index": (max((n["order_index"] for n in nodes), default=0) + 1),
            "estimated_runtime": 90,
            "estimated_cost": 0.03,
            "risk": "MEDIUM",
            "critical": True,
            "parallel_safe": False,
            "meta": {"revision": True, "failure_class": failure_class, "retry": retry_dec},
            "status": "pending",
        }
        nodes.append(new_node)
        changes["added"].append({"id": new_id, "title": new_node["title"], "agent": agent})

    for rid in obs.get("remove_node_ids") or []:
        before = len(nodes)
        nodes = [n for n in nodes if n["id"] != rid]
        if len(nodes) < before:
            changes["removed"].append(rid)


    # Remint node IDs so the new plan version does not collide with prior plan_nodes
    from storage import db as dbmod
    id_map = {n["id"]: dbmod.new_id("n_") for n in nodes}
    for n in nodes:
        old = n["id"]
        n["id"] = id_map[old]
        n["dependencies"] = [id_map.get(d, d) for d in (n.get("dependencies") or [])]
        if n.get("meta") is None:
            n["meta"] = {}
        n["meta"]["supersedes_node_id"] = old
    for item in changes.get("added") or []:
        if isinstance(item, dict) and item.get("id") in id_map:
            item["id"] = id_map[item["id"]]

    graph = build_graph(nodes)
    validation = validate_graph(graph)
    if not validation["ok"]:
        raise ValueError(f"revised plan invalid: {validation['errors']}")

    ordered = ordered_nodes(graph)
    cpath = critical_path(graph)
    quality = score_plan(graph, analysis={"required_agents": [n.get("agent") for n in nodes]})
    version = int(current.get("version") or 1) + 1
    store.set_goal_status(goal_id, "revising", db_path=db_path)

    new_plan = store.save_plan(
        goal_id=goal_id,
        graph={"nodes": ordered, "edges": graph.get("edges") or [], "critical_path": cpath},
        summary=f"Revision of {plan_id}: {reason}",
        version=version,
        status="approved" if cons.get("auto_approve", True) else "awaiting_approval",
        estimated_cost=sum(float(n.get("estimated_cost") or 0) for n in ordered),
        estimated_runtime_seconds=sum(float(n.get("estimated_runtime") or 0) for n in ordered),
        risk_summary=current.get("risk_summary") or {},
        approval_points=current.get("approval_points") or ["plan"],
        quality_score=float(quality.get("score") or 0),
        supersedes_plan_id=plan_id,
        workflow_template=current.get("workflow_template") or "",
        intelligence_notes={"revision_of": plan_id, "failure_class": failure_class},
        db_path=db_path,
    )
    store.set_plan_status(plan_id, "superseded", db_path=db_path)
    rev = store.record_revision(
        plan_id=plan_id, goal_id=goal_id, reason=reason,
        changes=changes, new_plan_id=new_plan["id"], db_path=db_path,
    )
    store.set_goal_status(goal_id, "active", db_path=db_path)
    return {
        "plan": new_plan,
        "revision": rev,
        "changes": changes,
        "validation": validation,
        "quality": quality,
        "retry": retry_dec,
        "failure_class": failure_class,
    }
