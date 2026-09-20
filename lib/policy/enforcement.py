#!/usr/bin/env python3
"""AgentBox v5 — Enforcement Engine (beta3).

Pipeline: Risk → Policy → Budget → Permissions → ALLOW / DENY / APPROVAL
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any, Callable, Optional

_HERE = Path(__file__).resolve().parent


def _ensure_path() -> None:
    lib = str(_HERE.parent)
    if lib not in sys.path:
        sys.path.insert(0, lib)


def enforce_action(
    action: str,
    resource: Optional[str] = None,
    task_id: Optional[str] = None,
    run_id: Optional[str] = None,
    agent_name: Optional[str] = None,
    context: Optional[dict] = None,
    budget_metric: Optional[str] = None,
    budget_value: float = 1.0,
    execute: Optional[Callable[[], Any]] = None,
    db_path: Optional[str] = None,
) -> dict[str, Any]:
    """Enforce action through risk → policy → budget → permissions.

    Returns:
      {
        decision: allow|deny|approval,
        risk, policy, budget, permission,
        approval_id?, result? (if execute and allow)
      }
    """
    _ensure_path()
    context = dict(context or {})
    if resource:
        context.setdefault("resource", resource)
    if task_id:
        context.setdefault("task_id", task_id)

    from policy import risk as riskmod  # type: ignore
    from policy import policies as polmod  # type: ignore
    from policy import budgets as budmod  # type: ignore
    from policy import permissions as permmod  # type: ignore
    from policy import approvals as apprmod  # type: ignore
    from storage import db as dbmod  # type: ignore

    # 1) Risk
    assessment = riskmod.assess_risk(action, resource=resource, context=context)
    assessment = riskmod.persist_assessment(
        assessment,
        task_id=task_id,
        run_id=run_id,
        agent_name=agent_name,
        db_path=db_path,
    )

    # 2) Policy
    policy = polmod.evaluate_policy(
        action,
        resource=resource,
        task_id=task_id,
        agent_name=agent_name,
        context=context,
        db_path=db_path,
    )

    decision = policy["decision"]
    reason = policy["reason"]

    # CRITICAL hard deny always wins (even if policy somehow allowed)
    if assessment["risk_level"] == "CRITICAL" or assessment["decision"] == "deny":
        # Re-check: evaluate_policy should already deny, but reinforce
        if decision != "deny":
            # Only if AUTO_APPROVE somehow flipped — CRITICAL must stay deny
            act = (action or "").replace("/", ".")
            if act in ("git.force_push", "force_push", "docker.privileged", "filesystem.system_write") \
                    or assessment["risk_score"] >= 80 and assessment["decision"] == "deny":
                decision = "deny"
                reason = f"enforcement CRITICAL deny: {assessment.get('reasons')}"

    # 3) Budget (before costly ops)
    budget = None
    if budget_metric or action in ("handoff.create", "agent.delegate", "before_run"):
        metric = budget_metric or (
            "max_handoffs" if action in ("handoff.create", "agent.delegate") else "max_agent_runs"
        )
        scope_id = task_id
        budget = budmod.check_budget(
            "task" if task_id else "global",
            scope_id,
            metric,
            requested_value=budget_value,
            db_path=db_path,
        )
        if not budget.get("ok"):
            decision = "deny"
            reason = f"budget: {budget.get('reason')}"
            if task_id:
                try:
                    budmod.pause_budget(task_id, reason, db_path=db_path)
                except Exception:
                    pass

    # 4) Permissions
    permission = None
    if agent_name:
        permission = permmod.check_permission(
            agent_name, action, resource=resource, context=context, db_path=db_path
        )
        if not permission.get("allowed"):
            decision = "deny"
            reason = f"permission: {permission.get('reason')}"
            try:
                dbmod.emit_event(
                    kind="permission.denied",
                    message=reason,
                    task_id=task_id,
                    payload={"action": action, "agent": agent_name},
                    db_path=db_path,
                )
            except Exception:
                pass

    out: dict[str, Any] = {
        "decision": decision,
        "reason": reason,
        "risk": assessment,
        "policy": policy,
        "budget": budget,
        "permission": permission,
        "action": action,
        "resource": resource,
        "task_id": task_id,
        "agent_name": agent_name,
    }

    if decision == "deny":
        try:
            if task_id and assessment["risk_level"] == "CRITICAL":
                try:
                    dbmod.set_task_status(task_id, "risk_blocked", db_path=db_path)
                except Exception:
                    try:
                        dbmod.set_task_status(task_id, "blocked", db_path=db_path)
                    except Exception:
                        pass
            elif task_id and "permission" in reason:
                try:
                    dbmod.set_task_status(task_id, "security_blocked", db_path=db_path)
                except Exception:
                    pass
            elif task_id and "budget" in reason:
                pass  # already paused
            elif task_id:
                try:
                    dbmod.set_task_status(task_id, "policy_denied", db_path=db_path)
                except Exception:
                    pass
        except Exception:
            pass
        return out

    if decision == "approval":
        # AUTO_APPROVE already handled in evaluate_policy for non-CRITICAL.
        # If we still need approval, create queue entry.
        appr = apprmod.create_approval(
            task_id=task_id,
            gate=action.replace("/", "."),
            approval_type=action.replace("/", "."),
            reason=reason,
            run_id=run_id,
            handoff_id=context.get("handoff_id"),
            requested_by=agent_name,
            risk_score=assessment["risk_score"],
            payload={"action": action, "resource": resource, "context": {
                k: context[k] for k in context if k not in ("secrets", "password", "token")
            }},
            db_path=db_path,
        )
        out["approval_id"] = appr["id"]
        out["approval"] = appr
        return out

    # ALLOW → optional execute + record usage
    if execute is not None:
        try:
            out["result"] = execute()
            out["executed"] = True
        except Exception as e:
            out["executed"] = False
            out["error"] = str(e)
            raise
    else:
        out["executed"] = False

    if budget_metric and task_id:
        try:
            budmod.record_usage(
                "task", task_id, budget_metric, budget_value,
                task_id=task_id, run_id=run_id, db_path=db_path,
            )
        except Exception:
            pass

    return out


def _print(obj: Any) -> None:
    print(json.dumps(obj, indent=2, ensure_ascii=False, default=str))


def main(argv: Optional[list[str]] = None) -> int:
    argv = list(argv if argv is not None else sys.argv[1:])
    db_path = os.environ.get("AGENTBOX_V5_DB")
    if not argv or argv[0] not in ("check", "enforce"):
        print(
            "usage: enforcement.py check ACTION [--resource R] [--agent A] [--task T]",
            file=sys.stderr,
        )
        return 2
    import argparse
    p = argparse.ArgumentParser()
    p.add_argument("action")
    p.add_argument("--resource", default=None)
    p.add_argument("--agent", default=None)
    p.add_argument("--task", default=None)
    p.add_argument("--budget-metric", default=None)
    p.add_argument("--force", action="store_true")
    p.add_argument("--privileged", action="store_true")
    args = p.parse_args(argv[1:])
    ctx = {"force": args.force, "force_push": args.force, "privileged": args.privileged}
    result = enforce_action(
        args.action,
        resource=args.resource,
        task_id=args.task,
        agent_name=args.agent,
        context=ctx,
        budget_metric=args.budget_metric,
        db_path=db_path,
    )
    _print(result)
    d = result["decision"]
    return 0 if d == "allow" else (2 if d == "approval" else 1)


if __name__ == "__main__":
    sys.exit(main())
