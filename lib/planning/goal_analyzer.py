#!/usr/bin/env python3
"""Goal analyzer — complexity, agents, risk, approval points."""
from __future__ import annotations

import re
from typing import Any, Optional


def analyze_goal(
    title: str,
    description: str = "",
    project_context: Optional[dict] = None,
    constraints: Optional[dict] = None,
) -> dict[str, Any]:
    text = f"{title or ''}\n{description or ''}".lower()
    ctx = project_context or {}
    cons = constraints or {}

    classification: dict[str, Any] = {}
    try:
        from intelligence.task_classifier import classify_task
        classification = classify_task(title, description, project_context=ctx) or {}
    except Exception as exc:
        classification = {"_error": str(exc)}

    task_type = classification.get("type") or _guess_type(text)
    complexity = classification.get("complexity") or _guess_complexity(text, ctx)
    if complexity == "HIGH" and any(k in text for k in ("distributed", "failover", "multi-agent", "architecture")):
        complexity = "VERY_HIGH"

    required_agents = list(classification.get("required_roles") or classification.get("required_roles") or [])
    if not required_agents:
        required_agents = _agents_for(task_type)
    if task_type in ("coding", "architecture", "refactor") and "architect" not in required_agents:
        if "planner" in required_agents:
            i = required_agents.index("planner") + 1
            required_agents = required_agents[:i] + ["architect"] + [a for a in required_agents[i:] if a != "architect"]
        else:
            required_agents = ["planner", "architect"] + required_agents

    stages = max(len(required_agents), 3)
    if complexity in ("HIGH", "VERY_HIGH"):
        stages = max(stages, 5)

    risk = str(cons.get("risk") or ctx.get("risk") or "MEDIUM").upper()
    if complexity == "VERY_HIGH" or any(k in text for k in ("security", "production", "migrate")):
        risk = "HIGH"
    if any(k in text for k in ("read-only", "docs only")):
        risk = "LOW"

    approval_points = ["plan"]
    if risk in ("HIGH", "CRITICAL") or complexity in ("HIGH", "VERY_HIGH"):
        approval_points.append("merge")
    if any(k in text for k in ("release", "deploy")):
        approval_points.append("release")

    return {
        "complexity": complexity,
        "task_type": task_type,
        "estimated_stages": stages,
        "required_agents": required_agents,
        "risk": risk,
        "approval_points": approval_points,
        "classification": classification,
        "memory_notes": _memory_notes(title, description),
        "recommended_context": classification.get("recommended_context") or classification.get("recommended_context") or ["code", "memory"],
    }


analyze = analyze_goal


def _guess_type(text: str) -> str:
    for t, pat in [
        ("bugfix", r"\bbug\b|\bfix\b|\berror\b"),
        ("security", r"\bsecur|\bvuln|\bcve\b"),
        ("refactor", r"\brefactor|\bcleanup"),
        ("architecture", r"\barchitect|\bdesign\b"),
        ("testing", r"\btest|\bpytest"),
        ("research", r"\bresearch|\binvestigat"),
        ("deployment", r"\bdeploy|\brelease"),
        ("coding", r"\bimplement|\bfeature|\badd\b|\bbuild\b"),
    ]:
        if re.search(pat, text):
            return t
    return "coding"


def _guess_complexity(text: str, ctx: dict) -> str:
    length = len(text)
    modules = int(ctx.get("modules") or ctx.get("files") or 0)
    if length > 400 or modules > 40 or "distributed" in text:
        return "VERY_HIGH"
    if length > 200 or modules > 20:
        return "HIGH"
    if length > 80 or modules > 5:
        return "MEDIUM"
    return "LOW"


def _agents_for(task_type: str) -> list[str]:
    return list({
        "coding": ["planner", "architect", "coder", "tester", "reviewer"],
        "bugfix": ["planner", "coder", "tester", "reviewer"],
        "refactor": ["planner", "architect", "coder", "tester", "reviewer"],
        "architecture": ["planner", "architect", "reviewer"],
        "testing": ["planner", "tester", "reviewer"],
        "research": ["planner", "researcher", "reviewer"],
        "security": ["planner", "architect", "coder", "reviewer"],
        "deployment": ["planner", "coder", "tester", "reviewer"],
    }.get(task_type, ["planner", "coder", "tester", "reviewer"]))


def _memory_notes(title: str, description: str) -> list[str]:
    notes: list[str] = []
    try:
        from intelligence.retrieval import retrieve_context
        pack = retrieve_context(f"{title} {description}", top_k=3, sources=["memory", "code"])
        for h in (pack.get("hits") or [])[:3]:
            preview = (h.get("text_preview") or h.get("content") or h.get("summary") or "")[:160]
            if preview:
                notes.append(preview)
    except Exception as exc:
        notes.append(f"memory retrieval unavailable: {exc}")
    return notes
