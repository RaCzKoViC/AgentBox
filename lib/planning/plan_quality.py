#!/usr/bin/env python3
"""Plan quality scoring — coverage, deps, risk, budget, parallelism, approvals."""
from __future__ import annotations

from typing import Any, Optional

from planning.task_graph import validate_graph, critical_path, topological_order


def score_plan(graph: dict, analysis: Optional[dict] = None, min_score: float = 65.0) -> dict[str, Any]:
    analysis = analysis or {}
    nodes = graph.get("nodes") or []
    validation = validate_graph(graph)
    scores: dict[str, float] = {}

    # coverage: required agents present
    required = set(analysis.get("required_agents") or [])
    present = { (n.get("agent") or "").lower() for n in nodes }
    if required:
        scores["coverage"] = 100.0 * len(required & present) / max(len(required), 1)
    else:
        scores["coverage"] = 80.0 if len(nodes) >= 3 else 50.0

    # dependency correctness
    scores["dependency_correctness"] = 100.0 if validation["ok"] else max(0.0, 100.0 - 20 * len(validation["errors"]))

    # risk coverage: high-risk goals should have reviewer + approval
    risk = str(analysis.get("risk") or "MEDIUM").upper()
    has_reviewer = "reviewer" in present
    has_approval = any((n.get("meta") or {}).get("approval_gate") for n in nodes) or bool(analysis.get("approval_points"))
    if risk in ("HIGH", "CRITICAL", "VERY_HIGH"):
        scores["risk_coverage"] = (50.0 if has_reviewer else 0.0) + (50.0 if has_approval else 0.0)
    else:
        scores["risk_coverage"] = 80.0 + (20.0 if has_reviewer else 0.0)

    # budget feasibility (estimated cost heuristic)
    total_cost = sum(float(n.get("estimated_cost") or 0.05) for n in nodes)
    budget = float((analysis.get("constraints") or {}).get("budget") or 10.0)
    scores["budget_feasibility"] = 100.0 if total_cost <= budget else max(0.0, 100.0 * budget / total_cost)

    # parallelism: reward some parallel_safe nodes without overdoing
    parallel = sum(1 for n in nodes if n.get("parallel_safe"))
    scores["parallelism"] = min(100.0, 40.0 + parallel * 15.0)

    # approval correctness
    points = analysis.get("approval_points") or []
    scores["approval_correctness"] = 100.0 if points else 70.0
    if risk in ("HIGH", "CRITICAL") and "merge" not in points and not has_approval:
        scores["approval_correctness"] = 40.0

    # test coverage signal
    scores["test_coverage"] = 100.0 if "tester" in present else 40.0

    weights = {
        "coverage": 0.2,
        "dependency_correctness": 0.25,
        "risk_coverage": 0.15,
        "budget_feasibility": 0.1,
        "parallelism": 0.05,
        "approval_correctness": 0.1,
        "test_coverage": 0.15,
    }
    total = sum(scores[k] * w for k, w in weights.items())
    try:
        cpath = critical_path(graph)
    except Exception:
        cpath = {"path": [], "seconds": 0}
    try:
        order = topological_order(graph)
    except Exception:
        order = []

    return {
        "score": round(total, 2),
        "pass": total >= min_score,
        "min_score": min_score,
        "components": scores,
        "validation": validation,
        "critical_path": cpath,
        "ordered_ids": order,
        "node_count": len(nodes),
        "estimated_cost": total_cost,
    }
