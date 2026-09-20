#!/usr/bin/env python3
"""Rule-based task classifier — type, complexity, roles, context needs."""
from __future__ import annotations

import re
from typing import Any, Optional

TASK_TYPES = [
    "coding", "bugfix", "refactor", "research", "security", "performance",
    "documentation", "testing", "architecture", "deployment", "data_analysis",
]

RULES: list[tuple[str, list[str]]] = [
    ("bugfix", [r"\bbug\b", r"\bfix\b", r"\berror\b", r"\bcrash\b", r"\bfail", r"\bregress"]),
    ("security", [r"\bsecur", r"\bvuln", r"\bcve\b", r"\bauth", r"\binject", r"\bxss\b", r"\bsecret"]),
    ("performance", [r"\bperf", r"\bslow", r"\blatenc", r"\boptim", r"\bthroughput", r"\bmemory leak"]),
    ("testing", [r"\btest", r"\bpytest", r"\bcoverage", r"\bspec\b", r"\bassert"]),
    ("documentation", [r"\bdoc", r"\breadme", r"\bchangelog", r"\bcomment"]),
    ("refactor", [r"\brefactor", r"\bcleanup", r"\brename", r"\bextract", r"\bdedup"]),
    ("architecture", [r"\barchitect", r"\bdesign", r"\brfc\b", r"\badr\b", r"\bmodul"]),
    ("deployment", [r"\bdeploy", r"\bci\b", r"\bcd\b", r"\bkuber", r"\bdocker", r"\brelease"]),
    ("data_analysis", [r"\banalys", r"\bmetric", r"\bdashboard", r"\bsql\b", r"\bdataset"]),
    ("research", [r"\bresearch", r"\binvestigat", r"\bexplor", r"\bspik"]),
    ("coding", [r"\bimplement", r"\badd\b", r"\bfeature", r"\bcreate", r"\bwrite", r"\bcod"]),
]

ROLE_MAP = {
    "coding": ["planner", "coder", "tester", "reviewer"],
    "bugfix": ["planner", "coder", "tester", "reviewer"],
    "refactor": ["planner", "coder", "tester", "reviewer"],
    "research": ["researcher", "planner"],
    "security": ["planner", "coder", "reviewer"],
    "performance": ["planner", "coder", "tester"],
    "documentation": ["coder", "reviewer"],
    "testing": ["tester", "coder"],
    "architecture": ["planner", "reviewer"],
    "deployment": ["planner", "coder"],
    "data_analysis": ["researcher", "coder"],
}

CTX_MAP = {
    "coding": ["code", "tests", "constraints"],
    "bugfix": ["code", "tests", "recent_failures"],
    "refactor": ["code", "architecture", "tests"],
    "research": ["docs", "memory"],
    "security": ["code", "policy", "security_notes"],
    "performance": ["code", "metrics"],
    "documentation": ["code", "docs"],
    "testing": ["code", "tests", "recent_failures"],
    "architecture": ["architecture", "memory", "docs"],
    "deployment": ["config", "docs"],
    "data_analysis": ["code", "artifacts"],
}


def classify_task(
    title: str,
    description: str = "",
    project_context: Optional[dict] = None,
) -> dict[str, Any]:
    text = f"{title or ''}\n{description or ''}".lower()
    scores: dict[str, int] = {t: 0 for t in TASK_TYPES}
    for ttype, pats in RULES:
        for pat in pats:
            if re.search(pat, text):
                scores[ttype] += 1
    best = max(scores, key=lambda k: scores[k])
    if scores[best] == 0:
        best = "coding"

    # complexity heuristics
    length = len(text)
    ctx = project_context or {}
    modules = int(ctx.get("modules") or ctx.get("files") or 0)
    risk = str(ctx.get("risk") or "").upper()
    complexity = "LOW"
    if length > 200 or modules > 20 or "HIGH" in risk:
        complexity = "HIGH"
    elif length > 80 or modules > 5:
        complexity = "MEDIUM"
    if best in ("architecture", "security") and complexity == "LOW":
        complexity = "MEDIUM"
    if "VERY" in risk or modules > 100:
        complexity = "VERY_HIGH"

    return {
        "type": best,
        "complexity": complexity,
        "scores": {k: v for k, v in scores.items() if v > 0},
        "required_roles": ROLE_MAP.get(best, ["coder"]),
        "recommended_context": CTX_MAP.get(best, ["code"]),
        "title": title,
    }
