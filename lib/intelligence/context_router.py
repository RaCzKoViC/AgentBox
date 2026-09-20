#!/usr/bin/env python3
"""Per-agent context routing — different agents get different slices."""
from __future__ import annotations

from typing import Any, Optional

AGENT_FOCUS = {
    "planner": ["architecture", "project_summary", "memory", "constraints"],
    "coder": ["code", "symbols", "tests", "constraints", "memory"],
    "tester": ["code", "tests", "recent_failures"],
    "reviewer": ["code", "policy", "architecture", "constraints", "acceptance"],
    "researcher": ["docs", "memory", "architecture"],
    "default": ["code", "memory", "constraints"],
}


def route_context(
    pack: dict[str, Any],
    agent_role: str,
    *,
    max_code_hits: int = 8,
    max_memory_hits: int = 5,
) -> dict[str, Any]:
    role = (agent_role or "default").lower()
    focus = AGENT_FOCUS.get(role, AGENT_FOCUS["default"])
    hits = list(pack.get("hits") or [])

    code_hits = [h for h in hits if h.get("source") in ("semantic", "keyword")]
    mem_hits = [h for h in hits if h.get("source") == "memory"]

    if "code" not in focus and "symbols" not in focus and "tests" not in focus:
        code_hits = code_hits[:2]
    else:
        # tester prefers test files
        if role == "tester":
            code_hits.sort(
                key=lambda h: (
                    0 if "test" in (h.get("file_path") or "").lower() else 1,
                    -(h.get("rerank_score") or h.get("score") or 0),
                )
            )
        code_hits = code_hits[:max_code_hits]

    if "memory" not in focus and "architecture" not in focus:
        mem_hits = mem_hits[:1]
    else:
        mem_hits = mem_hits[:max_memory_hits]

    return {
        "agent_role": role,
        "focus": focus,
        "code_hits": code_hits,
        "memory_hits": mem_hits,
        "constraints": pack.get("constraints") or [],
        "task": pack.get("task"),
    }


def format_for_prompt(routed: dict[str, Any]) -> str:
    parts = [f"## AGENT FOCUS ({routed.get('agent_role')})"]
    for h in routed.get("code_hits") or []:
        loc = h.get("file_path") or "?"
        sym = h.get("symbol") or ""
        preview = (h.get("text_preview") or h.get("content") or "")[:500]
        parts.append(f"### {loc} :: {sym}\n{preview}")
    if routed.get("memory_hits"):
        parts.append("## VECTOR MEMORY")
        for m in routed["memory_hits"]:
            parts.append(f"- [{m.get('memory_type') or 'note'}] {m.get('text_preview') or m.get('content') or ''}")
    for c in routed.get("constraints") or []:
        parts.append(f"CONSTRAINT: {c}")
    return "\n\n".join(parts)
