#!/usr/bin/env python3
"""Planner — compose goal analysis + workflow template into a versioned plan."""
from __future__ import annotations

import os
from typing import Any, Optional

from planning import store
from planning.goal_analyzer import analyze_goal
from planning.task_graph import build_graph, validate_graph, ordered_nodes, critical_path
from planning.dependency_prediction import predict_dependencies
from planning.workflow_templates import compile_template, resolve_template_name
from planning.plan_quality import score_plan


def create_goal(
    title: str,
    description: str = "",
    project_id: str = "",
    priority: int = 100,
    constraints: Optional[dict] = None,
    db_path: Optional[str] = None,
) -> dict:
    analysis = analyze_goal(title, description, constraints=constraints)
    goal = store.create_goal(
        title=title,
        description=description,
        project_id=project_id,
        priority=priority,
        constraints={**(constraints or {}), "analysis": analysis},
        risk_profile=analysis.get("risk", "MEDIUM"),
        approval_policy="plan",
        db_path=db_path,
    )
    store.set_goal_status(goal["id"], "analyzing", db_path=db_path)
    goal = store.set_goal_status(goal["id"], "planning", db_path=db_path)
    goal["analysis"] = analysis
    return goal


def generate_plan(
    goal_id: str,
    template: Optional[str] = None,
    auto_approve: Optional[bool] = None,
    db_path: Optional[str] = None,
) -> dict:
    goal = store.get_goal(goal_id, db_path=db_path)
    if not goal:
        raise KeyError(f"goal not found: {goal_id}")

    analysis = (goal.get("constraints") or {}).get("analysis") or analyze_goal(
        goal["title"], goal.get("description") or ""
    )
    tpl_name = resolve_template_name(
        template
        or (goal.get("constraints") or {}).get("workflow")
        or analysis.get("task_type")
        or "software_feature"
    )
    compiled = compile_template(tpl_name, goal=goal, analysis=analysis)
    nodes = compiled["nodes"]
    predict_dependencies(nodes)
    graph = build_graph(nodes)
    validation = validate_graph(graph)
    if not validation.get("ok"):
        raise ValueError(f"invalid plan graph: {validation.get('errors')}")

    ordered = ordered_nodes(graph)
    cpath = critical_path(graph)

    # Intelligence wiring
    intel_notes: dict[str, Any] = {"memory_notes": analysis.get("memory_notes") or [], "nodes": {}}
    for n in ordered:
        note: dict[str, Any] = {"agent": n.get("agent")}
        try:
            from intelligence.task_classifier import classify_task
            note["classification"] = classify_task(
                n.get("title") or "", n.get("description") or "",
                project_context={"risk": analysis.get("risk")},
            )
        except Exception as exc:
            note["classification_error"] = str(exc)
        try:
            from intelligence.model_router import route
            note["router"] = route(
                task_type=(note.get("classification") or {}).get("type")
                or analysis.get("task_type")
                or "coding",
                title=n.get("title") or "",
                description=n.get("description") or "",
                agent_role=n.get("agent") or "coder",
            )
        except Exception as exc:
            note["router_error"] = str(exc)
        intel_notes["nodes"][n["id"]] = note
        n.setdefault("meta", {})["intelligence"] = note
        # v5.4 soft tool suggestions (capability-based, non-binding)
        try:
            from tools.capability import find_tools
            need = (n.get("title") or "") + " " + (n.get("description") or "")
            caps = n.get("required_capabilities") or []
            suggestions = []
            for cap in (caps or [need[:80]]):
                matches = find_tools(str(cap), constraints={"max_risk": "HIGH"})
                for m in matches[:2]:
                    suggestions.append({"tool_id": m.get("id"), "score": m.get("score"), "need": cap})
            # dedupe
            seen = set()
            uniq = []
            for s in suggestions:
                if s["tool_id"] and s["tool_id"] not in seen:
                    seen.add(s["tool_id"])
                    uniq.append(s)
            note["suggested_tools"] = uniq[:5]
            n.setdefault("meta", {})["suggested_tools"] = uniq[:5]
            if uniq and not caps:
                n["required_capabilities"] = [u["tool_id"] for u in uniq[:3]]
        except Exception as exc:
            note["suggested_tools_error"] = str(exc)

    quality = score_plan(
        {"nodes": ordered, "edges": graph.get("edges") or []},
        analysis={
            "required_agents": list(analysis.get("required_agents") or []),
            "risk": analysis.get("risk"),
            "approval_points": analysis.get("approval_points") or [],
            "constraints": goal.get("constraints") or {},
        },
    )

    existing = store.list_plans(goal_id, db_path=db_path)
    version = (max((p.get("version") or 0) for p in existing) + 1) if existing else 1

    if auto_approve is None:
        auto_approve = os.environ.get("AGENTBOX_AUTO_APPROVE", "1") == "1"
    if auto_approve and analysis.get("risk") not in ("HIGH", "CRITICAL"):
        status = "approved"
    else:
        status = "awaiting_approval"

    est_runtime = sum(float(n.get("estimated_runtime") or 60) for n in ordered)
    est_cost = sum(float(n.get("estimated_cost") or 0.05) for n in ordered)
    summary = (
        f"Template={tpl_name}; stages={len(ordered)}; "
        f"critical_path={len(cpath.get('path') or [])}; quality={quality.get('score')}"
    )
    plan = store.save_plan(
        goal_id=goal_id,
        graph={"nodes": ordered, "edges": graph.get("edges") or [], "critical_path": cpath},
        summary=summary,
        version=version,
        status=status,
        estimated_cost=est_cost,
        estimated_runtime_seconds=est_runtime,
        risk_summary={"risk": analysis.get("risk"), "complexity": analysis.get("complexity")},
        approval_points=analysis.get("approval_points") or compiled.get("approvals") or ["plan"],
        quality_score=float(quality.get("score") or 0),
        workflow_template=tpl_name,
        intelligence_notes=intel_notes,
        db_path=db_path,
    )
    store.create_workflow_run(
        template_name=tpl_name, goal_id=goal_id, plan_id=plan["id"],
        status="compiled", meta={"node_count": len(ordered)}, db_path=db_path,
    )

    if status == "approved":
        store.set_goal_status(goal_id, "active", db_path=db_path)
    else:
        store.set_goal_status(goal_id, "awaiting_plan_approval", db_path=db_path)

    plan["validation"] = validation
    plan["quality"] = quality
    plan["analysis"] = analysis
    return plan


def plan_from_template(
    title: str,
    description: str = "",
    template: str = "software_feature",
    project_id: str = "",
    db_path: Optional[str] = None,
) -> dict:
    goal = create_goal(
        title, description, project_id=project_id,
        constraints={"workflow": template}, db_path=db_path,
    )
    plan = generate_plan(goal["id"], template=template, db_path=db_path)
    return {"goal": store.get_goal(goal["id"], db_path=db_path), "plan": plan}
