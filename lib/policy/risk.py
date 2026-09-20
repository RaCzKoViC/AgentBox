#!/usr/bin/env python3
"""AgentBox v5 — Risk Engine (beta3)."""
from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path
from typing import Any, Optional

_HERE = Path(__file__).resolve().parent


def _ensure_path() -> None:
    lib = str(_HERE.parent)
    if lib not in sys.path:
        sys.path.insert(0, lib)


def _db():
    _ensure_path()
    from storage import db as dbmod  # type: ignore

    return dbmod


# Base risk points by action (spec §3)
RISK_POINTS: dict[str, int] = {
    "read_file": 0,
    "filesystem.read": 0,
    "modify_workspace_file": 5,
    "filesystem.write": 5,
    "create_file": 5,
    "filesystem.create": 5,
    "delete_file": 15,
    "filesystem.delete": 15,
    "install_dependency": 20,
    "packages.install": 20,
    "packages.remove": 20,
    "network_request": 15,
    "network.outbound": 15,
    "network.unknown_domains": 25,
    "modify_lockfile": 10,
    "database_migration": 35,
    "database.migration": 35,
    "database.destructive_migration": 80,
    "docker_build": 20,
    "docker.build": 20,
    "docker_run": 25,
    "docker.run": 25,
    "docker.privileged": 80,
    "privileged_container": 80,
    "modify_etc": 80,
    "filesystem.system_write": 80,
    "access_secret": 70,
    "filesystem.secret_files": 70,
    "git_commit": 10,
    "git.commit": 10,
    "git_merge": 30,
    "git.merge": 30,
    "git_push": 50,
    "git.push": 50,
    "force_push": 100,
    "git.force_push": 100,
    "production_deploy": 90,
    "deployment.production": 90,
    "deployment.staging": 20,
    "agent.delegate": 15,
    "handoff.create": 15,
    "before_run": 5,
    "run.before_run": 5,
    "shell.run": 55,
    "shell.dangerous": 85,
    "git.status": 0,
    "git.diff": 0,
    "http.get": 15,
    "docker.ps": 5,
    "file.read": 0,
    "file.write": 5,
}


def risk_level(score: int) -> str:
    s = max(0, min(100, int(score)))
    if s <= 19:
        return "LOW"
    if s <= 39:
        return "MODERATE"
    if s <= 59:
        return "ELEVATED"
    if s <= 79:
        return "HIGH"
    return "CRITICAL"


def default_decision_for_level(level: str) -> str:
    """Spec §3 default decisions by risk level."""
    return {
        "LOW": "allow",
        "MODERATE": "allow",  # allow + audit
        "ELEVATED": "approval",  # policy dependent — default approval-ish
        "HIGH": "approval",
        "CRITICAL": "deny",
    }.get(level, "deny")


def _secret_like(path: str) -> bool:
    p = (path or "").lower()
    patterns = (
        r"\.env($|\.)", r"secrets?", r"credentials?", r"\.pem$", r"\.key$",
        r"id_rsa", r"id_ed25519", r"\.aws/", r"\.ssh/", r"token", r"passwd",
        r"password", r"apikey", r"api_key",
    )
    return any(re.search(pat, p) for pat in patterns)


def _system_path(path: str) -> bool:
    p = os.path.abspath(path or "")
    for prefix in ("/etc", "/usr", "/boot", "/bin", "/sbin", "/lib", "/lib64", "/root"):
        if p == prefix or p.startswith(prefix + "/"):
            return True
    return False


def _normalize_action(action: str) -> str:
    a = (action or "").strip().replace("/", ".")
    aliases = {
        "git push --force": "git.force_push",
        "git push -f": "git.force_push",
        "force-push": "git.force_push",
        "force_push": "git.force_push",
        "write": "filesystem.write",
        "read": "filesystem.read",
        "delete": "filesystem.delete",
        "push": "git.push",
        "merge": "git.merge",
        "commit": "git.commit",
        "docker privileged": "docker.privileged",
        "handoff": "handoff.create",
        "delegate": "agent.delegate",
    }
    low = a.lower()
    if low in aliases:
        return aliases[low]
    return a


def assess_risk(
    action: str,
    resource: Optional[str] = None,
    context: Optional[dict] = None,
) -> dict[str, Any]:
    """Assess risk for an action. Returns RiskAssessment dict."""
    context = context or {}
    action_n = _normalize_action(action)
    reasons: list[str] = []
    score = RISK_POINTS.get(action_n)
    if score is None:
        # fuzzy: try last segment / known substrings
        score = 25
        reasons.append(f"unknown action '{action_n}' → base 25")
        for key, pts in RISK_POINTS.items():
            if key in action_n or action_n.endswith(key.split(".")[-1]):
                score = pts
                reasons.append(f"matched pattern {key}={pts}")
                break
    else:
        reasons.append(f"base action {action_n}={score}")

    resource = resource or context.get("resource") or ""
    if resource:
        if _secret_like(resource):
            score = max(score, 70)
            reasons.append(f"secret-like resource: {resource}")
        if _system_path(resource):
            score = max(score, 80)
            reasons.append(f"system path write/access: {resource}")
        # outside workspace
        workspace = context.get("workspace") or os.environ.get("AGENTBOX_WORKSPACE") or "/workspace"
        if context.get("check_workspace", True) and action_n.startswith("filesystem."):
            try:
                abs_r = os.path.abspath(resource)
                abs_w = os.path.abspath(workspace)
                if not abs_r.startswith(abs_w + os.sep) and abs_r != abs_w:
                    if action_n in ("filesystem.write", "filesystem.create", "filesystem.delete",
                                    "filesystem.system_write", "modify_workspace_file"):
                        score = max(score, 80)
                        reasons.append(f"outside workspace: {resource}")
            except Exception:
                pass

    # Context boosters
    if context.get("force") or context.get("force_push"):
        score = 100
        reasons.append("force flag → CRITICAL")
        action_n = "git.force_push"
    if context.get("privileged"):
        score = max(score, 80)
        reasons.append("privileged container")
    if context.get("production"):
        score = max(score, 90)
        reasons.append("production target")
    if context.get("destructive"):
        score = max(score, 80)
        reasons.append("destructive flag")

    score = max(0, min(100, int(score)))
    level = risk_level(score)
    decision = default_decision_for_level(level)
    # Hard safety overrides
    if action_n in ("git.force_push", "force_push") or score >= 100:
        decision = "deny"
        level = "CRITICAL"
        score = 100
        reasons.append("hard deny: force_push / CRITICAL")
    if action_n in ("docker.privileged", "privileged_container"):
        decision = "deny"
        reasons.append("hard deny: privileged docker")
    if action_n == "filesystem.system_write" or (resource and _system_path(resource)
                                                  and "write" in action_n):
        decision = "deny"
        reasons.append("hard deny: system path write")

    return {
        "action": action_n,
        "resource": resource or None,
        "risk_score": score,
        "risk_level": level,
        "decision": decision,
        "reasons": reasons,
        "reasons_json": json.dumps(reasons),
    }


def persist_assessment(
    assessment: dict,
    task_id: Optional[str] = None,
    run_id: Optional[str] = None,
    agent_name: Optional[str] = None,
    db_path: Optional[str] = None,
) -> dict:
    """Store risk_assessments row + emit event + metric."""
    db = _db()
    rid = db.new_id("r_")
    now = db.utc_now()
    with db.connect(db_path) as conn:
        conn.execute(
            """
            INSERT INTO risk_assessments (
                id, task_id, run_id, agent_name, action, resource,
                risk_score, risk_level, decision, reasons_json, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                rid, task_id, run_id, agent_name,
                assessment.get("action") or "",
                assessment.get("resource"),
                int(assessment["risk_score"]),
                assessment["risk_level"],
                assessment["decision"],
                assessment.get("reasons_json") or json.dumps(assessment.get("reasons") or []),
                now,
            ),
        )
        conn.commit()
    assessment = dict(assessment)
    assessment["id"] = rid
    try:
        db.emit_event(
            kind="risk.assessed",
            message=f"{assessment['action']} score={assessment['risk_score']} {assessment['risk_level']}",
            task_id=task_id,
            run_id=run_id,
            payload={
                "assessment_id": rid,
                "action": assessment["action"],
                "risk_score": assessment["risk_score"],
                "risk_level": assessment["risk_level"],
                "decision": assessment["decision"],
            },
            db_path=db_path,
        )
        if assessment["risk_level"] == "HIGH":
            db.emit_event(kind="risk.high", message=assessment["action"],
                          task_id=task_id, payload={"assessment_id": rid}, db_path=db_path)
        if assessment["risk_level"] == "CRITICAL":
            db.emit_event(kind="risk.critical", message=assessment["action"],
                          task_id=task_id, payload={"assessment_id": rid}, db_path=db_path)
    except Exception:
        pass
    try:
        from observability.metrics import record_metric  # type: ignore

        record_metric("agentbox_risk_assessments_total", 1.0,
                      labels={"level": assessment["risk_level"]}, db_path=db_path)
        if assessment["risk_level"] in ("HIGH", "CRITICAL"):
            record_metric("agentbox_risk_high_total", 1.0,
                          labels={"level": assessment["risk_level"]}, db_path=db_path)
    except Exception:
        pass
    return assessment


def list_history(
    task_id: Optional[str] = None,
    limit: int = 50,
    db_path: Optional[str] = None,
) -> list[dict]:
    db = _db()
    with db.connect(db_path) as conn:
        if task_id:
            rows = conn.execute(
                "SELECT * FROM risk_assessments WHERE task_id=? ORDER BY created_at DESC LIMIT ?",
                (task_id, limit),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM risk_assessments ORDER BY created_at DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [dict(r) for r in rows]


def _print(obj: Any) -> None:
    print(json.dumps(obj, indent=2, ensure_ascii=False, default=str))


def main(argv: Optional[list[str]] = None) -> int:
    argv = list(argv if argv is not None else sys.argv[1:])
    db_path = os.environ.get("AGENTBOX_V5_DB")
    if not argv:
        print("usage: risk.py check ACTION [--resource R] | history [--task ID]", file=sys.stderr)
        return 2
    cmd = argv[0]
    try:
        if cmd == "check":
            import argparse
            p = argparse.ArgumentParser()
            p.add_argument("action")
            p.add_argument("--resource", default=None)
            p.add_argument("--task", default=None)
            p.add_argument("--agent", default=None)
            p.add_argument("--persist", action="store_true")
            p.add_argument("--force", action="store_true")
            p.add_argument("--privileged", action="store_true")
            args = p.parse_args(argv[1:])
            ctx = {"force": args.force, "privileged": args.privileged}
            result = assess_risk(args.action, resource=args.resource, context=ctx)
            if args.persist or args.task:
                result = persist_assessment(
                    result, task_id=args.task, agent_name=args.agent, db_path=db_path
                )
            _print(result)
            return 0 if result["decision"] == "allow" else (2 if result["decision"] == "approval" else 1)
        if cmd == "history":
            import argparse
            p = argparse.ArgumentParser()
            p.add_argument("--task", default=None)
            p.add_argument("--limit", type=int, default=50)
            args = p.parse_args(argv[1:])
            _print(list_history(task_id=args.task, limit=args.limit, db_path=db_path))
            return 0
        print(f"unknown: {cmd}", file=sys.stderr)
        return 2
    except Exception as e:
        print(f"error: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
