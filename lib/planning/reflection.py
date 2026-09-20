#!/usr/bin/env python3
"""Execution reflection — CONTINUE / RETRY / REPLAN / ESCALATE / COMPLETE."""
from __future__ import annotations

from typing import Any, Optional

from planning import store
from planning.retry_strategy import classify_failure, decide_retry


def reflect(
    goal_id: str,
    task_id: str = "",
    run_result: Optional[dict] = None,
    context: Optional[dict] = None,
    plan_id: str = "",
    db_path: Optional[str] = None,
) -> dict[str, Any]:
    result = run_result or {}
    ctx = context or {}
    status = str(result.get("status") or result.get("outcome") or "unknown").lower()
    error = str(result.get("error") or result.get("message") or "")
    recent = list(ctx.get("recent_errors") or result.get("recent_errors") or [])

    decision = "CONTINUE"
    confidence = 0.75
    reason = "stage completed successfully"
    proposed: list[str] = []

    if status in ("completed", "success", "ok", "passed"):
        if ctx.get("goal_complete") or result.get("goal_complete"):
            decision, confidence, reason = "COMPLETE", 0.9, "success criteria met"
            proposed = ["mark_goal_completed"]
        else:
            decision, confidence, reason = "CONTINUE", 0.85, "continue to next ready node"
            proposed = ["schedule_next"]
    elif status in ("failed", "error", "fail"):
        fclass = classify_failure(error, {**result, **ctx})
        retry = decide_retry(
            fclass,
            attempt=int(result.get("attempt") or ctx.get("attempt") or 1),
            recent_errors=recent + ([error] if error else []),
        )
        if retry.get("loop_detected") or retry.get("action") == "escalate":
            decision, confidence = "ESCALATE", 0.95
            reason = retry.get("reason") or f"escalate after {fclass}"
            proposed = ["needs_human", f"failure_class={fclass}"]
        elif retry.get("action") == "replan" or fclass == "DEPENDENCY":
            decision, confidence = "REPLAN", 0.88
            reason = f"Requires replan ({fclass}): {error or reason}"
            proposed = ["revise_plan", "add_research_subtask"]
            if retry.get("fallback_agent"):
                proposed.append(f"insert_agent:{retry['fallback_agent']}")
        elif retry.get("action") in ("retry", "debugger", "fallback", "failover"):
            decision, confidence = "RETRY", 0.8
            reason = f"{fclass} -> {retry['action']}"
            proposed = [retry["action"]]
            if retry.get("fallback_agent"):
                proposed.append(f"insert_agent:{retry['fallback_agent']}")
        elif retry.get("action") in ("block", "pause", "wait"):
            decision, confidence = "ESCALATE", 0.9
            reason = f"{fclass} blocks autonomy ({retry['action']})"
            proposed = [retry["action"], "needs_human"]
        else:
            decision, confidence = "REPLAN", 0.7
            reason = f"unknown failure path: {fclass}"
            proposed = ["revise_plan"]
    elif status in ("blocked", "policy_denied", "risk_blocked"):
        decision, confidence, reason = "ESCALATE", 0.95, f"blocked status: {status}"
        proposed = ["needs_human"]
    else:
        decision, confidence, reason = "CONTINUE", 0.5, f"unrecognized status={status}; default continue"

    proposed = [p for p in proposed if p not in ("bypass_policy", "raise_budget", "skip_approval")]

    rec = store.save_reflection(
        goal_id=goal_id,
        decision=decision,
        reason=reason,
        confidence=confidence,
        proposed_actions=proposed,
        task_id=task_id,
        run_id=str(result.get("run_id") or ""),
        plan_id=plan_id,
        db_path=db_path,
    )
    return {
        "decision": decision,
        "confidence": confidence,
        "reason": reason,
        "proposed_actions": proposed,
        "reflection": rec,
    }
