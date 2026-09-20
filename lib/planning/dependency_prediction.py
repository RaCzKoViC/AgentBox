#!/usr/bin/env python3
"""Predict hard/soft/approval dependencies between plan stages."""
from __future__ import annotations

from typing import Any

STAGE_ORDER = [
    "planner", "researcher", "architect", "coder", "debugger",
    "tester", "reviewer", "releaser",
]


def predict_dependencies(nodes: list[dict]) -> list[dict]:
    """Mutate nodes with dependency lists; return edge list."""
    by_agent: dict[str, list[dict]] = {}
    for s in nodes:
        agent = (s.get("agent") or s.get("assigned_agent") or "coder").lower()
        s["agent"] = agent
        by_agent.setdefault(agent, []).append(s)

    ordered: list[dict] = []
    seen: set[str] = set()
    for role in STAGE_ORDER:
        for s in by_agent.get(role, []):
            if s["id"] not in seen:
                ordered.append(s)
                seen.add(s["id"])
    for s in nodes:
        if s["id"] not in seen:
            ordered.append(s)
            seen.add(s["id"])

    edges: list[dict] = []
    prev_id = None
    for s in ordered:
        deps = list(s.get("dependencies") or [])
        if prev_id and prev_id not in deps:
            deps.append(prev_id)
            edges.append({"from": prev_id, "to": s["id"], "type": "hard"})
        agent = (s.get("agent") or "").lower()
        if agent == "tester":
            for c in by_agent.get("coder", []):
                if c["id"] not in deps and c["id"] != s["id"]:
                    deps.append(c["id"])
                    edges.append({"from": c["id"], "to": s["id"], "type": "hard"})
        if agent == "reviewer":
            for t in by_agent.get("tester", []):
                if t["id"] not in deps and t["id"] != s["id"]:
                    deps.append(t["id"])
                    edges.append({"from": t["id"], "to": s["id"], "type": "hard"})
            s.setdefault("meta", {})["approval_gate"] = "before_merge"
        s["dependencies"] = [d for d in deps if d != s["id"]]
        prev_id = s["id"]
    return edges


def chain_from_agents(agents: list[str]) -> list[dict]:
    nodes = []
    for i, name in enumerate(agents):
        nodes.append({
            "id": f"stage_{name}_{i}",
            "title": name.replace("_", " ").title(),
            "agent": name,
            "dependencies": [f"stage_{agents[i-1]}_{i-1}"] if i > 0 else [],
            "order_index": i,
            "type": "stage",
            "estimated_runtime": 120,
            "estimated_cost": 0.05,
            "risk": "MEDIUM",
            "critical": True,
            "parallel_safe": False,
        })
    predict_dependencies(nodes)
    return nodes
