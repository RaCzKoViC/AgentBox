#!/usr/bin/env python3
"""Tool chaining — plan and execute sequential tool calls with checkpoints."""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Any, Optional

_HERE = Path(__file__).resolve().parent


def _ensure_path() -> None:
    lib = str(_HERE.parent)
    if lib not in sys.path:
        sys.path.insert(0, lib)


def plan_tool_chain(
    goal: str,
    capabilities: Optional[list[str]] = None,
    constraints: Optional[dict] = None,
) -> dict[str, Any]:
    """Heuristic chain planner from goal text / capabilities."""
    _ensure_path()
    from tools.capability import find_tools

    caps = list(capabilities or [])
    g = (goal or "").lower()
    if not caps:
        if "git" in g or "diff" in g:
            caps += ["git_status", "git_diff"]
        if "read" in g or "file" in g:
            caps += ["read_file"]
        if "test" in g:
            caps += ["shell_exec"]
        if "http" in g or "fetch" in g:
            caps += ["http_get"]
        if not caps:
            caps = ["read_file", "git_status"]

    steps = []
    for cap in caps:
        matches = find_tools(cap, constraints=constraints)
        if not matches:
            steps.append({"capability": cap, "tool_id": None, "status": "unmatched"})
            continue
        best = matches[0]
        steps.append({
            "capability": cap,
            "tool_id": best.get("id"),
            "score": best.get("score"),
            "risk_level": best.get("risk_level"),
        })
    return {"goal": goal, "steps": steps, "ok": all(s.get("tool_id") for s in steps)}


def validate_chain(steps: list[dict], db_path: Optional[str] = None) -> dict[str, Any]:
    _ensure_path()
    from tools import registry
    errors = []
    for i, s in enumerate(steps):
        tid = s.get("tool_id")
        if not tid:
            errors.append(f"step {i}: no tool")
            continue
        t = registry.get_tool(tid, db_path=db_path)
        if not t:
            errors.append(f"step {i}: tool {tid} not found")
        elif not t.get("enabled"):
            errors.append(f"step {i}: tool {tid} disabled")
        elif t.get("health_status") == "quarantined":
            errors.append(f"step {i}: tool {tid} quarantined")
        if (t or {}).get("risk_level") == "CRITICAL":
            errors.append(f"step {i}: CRITICAL tool forbidden in chain without explicit approval")
    return {"ok": not errors, "errors": errors}


def run_chain(
    steps: list[dict],
    default_inputs: Optional[dict] = None,
    task_context: Optional[dict] = None,
    agent_context: Optional[dict] = None,
    db_path: Optional[str] = None,
    stop_on_failure: bool = True,
) -> dict[str, Any]:
    """Execute chain; each step through executor (enforcement). Checkpoint after each."""
    _ensure_path()
    from tools.executor import execute_tool

    v = validate_chain(steps, db_path=db_path)
    if not v["ok"]:
        return {"ok": False, "validation": v, "results": []}

    results = []
    default_inputs = default_inputs or {}
    for i, s in enumerate(steps):
        tid = s["tool_id"]
        payload = dict(default_inputs.get(tid) or s.get("input") or {})
        # carry forward simple outputs
        if i > 0 and results[-1].get("ok") and tid.startswith("file.") and "path" not in payload:
            prev = results[-1]
            if prev.get("path"):
                payload.setdefault("path", prev["path"])
        r = execute_tool(tid, payload, task_context=task_context, agent_context=agent_context, db_path=db_path)
        results.append(r)
        # checkpoint marker
        r["checkpoint"] = {"step": i, "tool_id": tid}
        if stop_on_failure and not r.get("ok") and r.get("status") not in ("completed",):
            if r.get("decision") in ("deny", "approval") or r.get("status") in ("denied", "failed", "timeout"):
                return {"ok": False, "results": results, "stopped_at": i}
    ok = all(r.get("ok") for r in results)
    return {"ok": ok, "results": results}
