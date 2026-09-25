"""Health remediation — low-risk auto; high-risk → approval."""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Any, Optional

_HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(_HERE.parent))

from storage import db as dbmod  # noqa: E402
from ops_autopilot import store  # noqa: E402
from ops_autopilot.playbooks import list_playbooks, run_playbook, PLAYBOOKS  # noqa: E402

LOW_RISK_AUTO = {
    "clear_stale_pids",
    "prune_old_logs",
    "restart_web_if_down",
    # smart_backup is low-risk but only when schedule says so — included in scan suggestions
    "smart_backup",
}

HIGH_RISK = {"quarantine_worker", "restore_backup"}


def status() -> dict[str, Any]:
    from ops.diagnostics import doctor
    from ops_autopilot.forecast import forecast
    from ops.lifecycle import status as life_status

    doc = doctor()
    fc = forecast()
    life = life_status()
    pending = store.list_remediations(status="awaiting_approval", limit=20)
    recent = store.list_remediations(limit=10)
    plans = store.list_maintenance_plans(limit=5)
    try:
        from ops_autopilot.health_registry import evaluate as health_evaluate
        health = health_evaluate(persist=False)
    except Exception as e:
        health = {"ok": False, "score": 0, "status": "unknown", "error": str(e)}
    try:
        from ops_autopilot.incidents import list_incidents
        open_incidents = list_incidents(status="open", limit=20)
    except Exception:
        open_incidents = []
    return {
        "ok": doc.get("ok", False) and fc.get("level") != "critical" and health.get("status") != "critical",
        "doctor": {"health": doc.get("health"), "ok": doc.get("ok"), "failed": doc.get("failed"), "version": doc.get("version")},
        "forecast": {"level": fc.get("level"), "signals": fc.get("signals"), "resources": fc.get("resources")},
        "lifecycle": life,
        "playbooks": list_playbooks(),
        "pending_approvals": pending,
        "recent_actions": recent,
        "maintenance_plans": plans,
        "health": health,
        "open_incidents": open_incidents,
        "version": _platform_version(),
    }


def scan(*, dry_run: bool = True) -> dict[str, Any]:
    """Scan platform health and propose / optionally auto-apply low-risk fixes."""
    from ops.diagnostics import doctor
    from ops.recovery import scan_stale_pids
    from ops.lifecycle import web_status
    from ops_autopilot.forecast import forecast
    from ops_autopilot.drift import detect_all
    from ops_autopilot.backup_schedule import should_backup

    doc = doctor()
    fc = forecast()
    stale = scan_stale_pids()
    web = web_status()
    drift = detect_all(persist=True)
    backup_dec = should_backup()

    proposals: list[dict[str, Any]] = []

    if stale:
        proposals.append({
            "playbook_id": "clear_stale_pids",
            "risk_level": "LOW",
            "reason": f"{len(stale)} stale PID file(s)",
            "auto": True,
        })
    if any(s["code"] in ("logs_warn", "logs_crit") for s in fc.get("signals", [])):
        proposals.append({
            "playbook_id": "prune_old_logs",
            "risk_level": "LOW",
            "reason": "log volume above threshold",
            "auto": True,
        })
    if not web.get("running"):
        proposals.append({
            "playbook_id": "restart_web_if_down",
            "risk_level": "LOW",
            "reason": "web not running",
            "auto": True,
        })
    if backup_dec.get("needed"):
        proposals.append({
            "playbook_id": "smart_backup",
            "risk_level": "LOW",
            "reason": ",".join(backup_dec.get("reasons") or ["schedule"]),
            "auto": True,
        })
    if drift.get("drifted"):
        proposals.append({
            "playbook_id": "detect_config_drift",
            "risk_level": "LOW",
            "reason": "drift detected (informational re-scan)",
            "auto": True,
        })

    # High-risk suggestions (never auto)
    try:
        from distributed.registry import list_workers
        for w in list_workers():
            # suggest quarantine for workers that look unhealthy for a long time — heuristic: status error
            if w.get("status") in ("error", "unhealthy"):
                proposals.append({
                    "playbook_id": "quarantine_worker",
                    "risk_level": "HIGH",
                    "reason": f"worker {w.get('id')} status={w.get('status')}",
                    "auto": False,
                    "target": w.get("id"),
                })
    except Exception:
        pass

    return {
        "ok": True,
        "dry_run": dry_run,
        "doctor": {"health": doc.get("health"), "failed": doc.get("failed")},
        "forecast_level": fc.get("level"),
        "drifted": drift.get("drifted"),
        "proposals": proposals,
        "stale_pid_count": len(stale),
        "web_running": bool(web.get("running")),
        "backup": backup_dec,
    }


def remediate(
    *,
    dry_run: bool = True,
    auto_low_risk: bool = True,
    playbook_id: Optional[str] = None,
    approval_id: Optional[str] = None,
    allow_high_risk: bool = False,
) -> dict[str, Any]:
    """Apply remediation. Low-risk auto when auto_low_risk; high-risk needs approval."""
    if playbook_id:
        p = PLAYBOOKS.get(playbook_id)
        if not p:
            raise ValueError(f"unknown playbook: {playbook_id}")
        risk = p["risk_level"]
        if risk == "HIGH" and not allow_high_risk and not approval_id:
            # create approval and stop
            from policy.approvals import create_approval
            appr = create_approval(
                task_id=None,
                gate="ops_remediation",
                approval_type="ops_high_risk",
                reason=f"High-risk playbook {playbook_id} requires approval",
                risk_score=80,
                payload={"playbook_id": playbook_id},
                requested_by="ops_autopilot",
            )
            # record remediation awaiting
            aid = dbmod.new_id("rem_")
            with dbmod.connect() as conn:
                store.ensure_schema(conn)
                store.insert_remediation(
                    conn,
                    {
                        "id": aid,
                        "action_type": playbook_id,
                        "risk_level": "HIGH",
                        "status": "awaiting_approval",
                        "dry_run": True,
                        "target": playbook_id,
                        "detail": {"approval": appr},
                        "approval_id": appr.get("id"),
                    },
                )
                conn.commit()
            return {
                "ok": True,
                "status": "awaiting_approval",
                "playbook_id": playbook_id,
                "approval_id": appr.get("id"),
                "remediation_id": aid,
                "message": "High-risk action queued for human approval",
            }

        if approval_id:
            from policy.approvals import get_approval
            ap = get_approval(approval_id)
            if not ap or ap.get("status") != "approved":
                return {
                    "ok": False,
                    "error": "approval not found or not approved",
                    "approval_id": approval_id,
                    "approval_status": (ap or {}).get("status"),
                }
            allow_high_risk = True

        result = run_playbook(
            playbook_id,
            dry_run=dry_run,
            triggered_by="remediate",
            allow_high_risk=allow_high_risk and risk == "HIGH",
        )
        return {"ok": result.get("status") in ("passed", "awaiting_approval"), "actions": [result]}

    # Batch from scan
    sc = scan(dry_run=True)
    actions = []
    for prop in sc.get("proposals") or []:
        pid = prop["playbook_id"]
        if prop.get("risk_level") == "HIGH":
            if dry_run:
                actions.append({
                    "playbook_id": pid,
                    "status": "proposed_high_risk",
                    "dry_run": True,
                    "reason": prop.get("reason"),
                })
            else:
                # create approval, do not apply
                r = remediate(playbook_id=pid, dry_run=True, allow_high_risk=False)
                actions.append(r)
            continue
        if not auto_low_risk and not dry_run:
            actions.append({"playbook_id": pid, "status": "skipped_no_auto", "dry_run": dry_run})
            continue
        # For dry_run always run playbook in dry mode; for real only LOW auto
        r = run_playbook(pid, dry_run=dry_run, triggered_by="remediate_auto")
        actions.append(r)

    return {
        "ok": True,
        "dry_run": dry_run,
        "scan": {k: sc[k] for k in ("doctor", "forecast_level", "drifted", "proposals") if k in sc},
        "actions": actions,
    }


def apply_approved(approval_id: str, playbook_id: str) -> dict[str, Any]:
    return remediate(playbook_id=playbook_id, dry_run=False, approval_id=approval_id, allow_high_risk=True)


def _platform_version() -> str:
    try:
        from ops.paths import read_version
        return read_version()
    except Exception:
        return "5.6.3"
