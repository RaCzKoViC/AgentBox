"""Operations Autopilot REST API (v5.6)."""
from __future__ import annotations

from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from ..deps import Actor, get_actor, require_role

router = APIRouter(tags=["ops"])


class RemediateBody(BaseModel):
    dry_run: bool = True
    playbook_id: Optional[str] = None
    approval_id: Optional[str] = None
    auto_low_risk: bool = True
    allow_high_risk: bool = False


class PlaybookRunBody(BaseModel):
    dry_run: bool = True
    allow_high_risk: bool = False


class PlanBody(BaseModel):
    title: Optional[str] = None


@router.get("/api/v1/ops/status")
def ops_status(_actor: Actor = Depends(get_actor)):
    from ops_autopilot.remediation import status
    return status()


@router.get("/api/v1/ops/scan")
def ops_scan(_actor: Actor = Depends(get_actor)):
    from ops_autopilot.remediation import scan
    return scan(dry_run=True)


@router.post("/api/v1/ops/remediate")
def ops_remediate(body: RemediateBody, _actor: Actor = Depends(require_role("operator"))):
    from ops_autopilot.remediation import remediate
    try:
        return remediate(
            dry_run=body.dry_run,
            auto_low_risk=body.auto_low_risk,
            playbook_id=body.playbook_id,
            approval_id=body.approval_id,
            allow_high_risk=body.allow_high_risk,
        )
    except ValueError as e:
        raise HTTPException(400, str(e))


@router.get("/api/v1/ops/playbooks")
def ops_playbooks(_actor: Actor = Depends(get_actor)):
    from ops_autopilot.playbooks import list_playbooks
    items = list_playbooks()
    return {"playbooks": items, "count": len(items)}


@router.post("/api/v1/ops/playbooks/{playbook_id}/run")
def ops_playbook_run(playbook_id: str, body: PlaybookRunBody, _actor: Actor = Depends(require_role("operator"))):
    from ops_autopilot.playbooks import run_playbook
    try:
        return run_playbook(
            playbook_id,
            dry_run=body.dry_run,
            triggered_by="api",
            allow_high_risk=body.allow_high_risk,
        )
    except ValueError as e:
        raise HTTPException(404, str(e))


@router.get("/api/v1/ops/playbook-runs")
def ops_playbook_runs(playbook_id: Optional[str] = None, limit: int = 50, _actor: Actor = Depends(get_actor)):
    from ops_autopilot.store import list_playbook_runs
    return {"runs": list_playbook_runs(playbook_id=playbook_id, limit=limit)}


@router.get("/api/v1/ops/remediations")
def ops_remediations(status: Optional[str] = None, limit: int = 50, _actor: Actor = Depends(get_actor)):
    from ops_autopilot.store import list_remediations
    return {"actions": list_remediations(status=status, limit=limit)}


@router.get("/api/v1/ops/drift")
def ops_drift(history: bool = False, limit: int = 20, _actor: Actor = Depends(get_actor)):
    from ops_autopilot.drift import detect_all
    from ops_autopilot.store import list_drift
    if history:
        return {"snapshots": list_drift(limit=limit)}
    return detect_all(persist=True)


@router.post("/api/v1/ops/drift/reset-baseline")
def ops_drift_reset(_actor: Actor = Depends(require_role("operator"))):
    from ops_autopilot.drift import reset_baseline
    return reset_baseline()


@router.get("/api/v1/ops/forecast")
def ops_forecast(_actor: Actor = Depends(get_actor)):
    from ops_autopilot.forecast import forecast
    return forecast()


@router.post("/api/v1/ops/cleanup")
def ops_cleanup(dry_run: bool = True, _actor: Actor = Depends(require_role("operator"))):
    from ops_autopilot.cleanup import cleanup
    return cleanup(dry_run=dry_run)


@router.get("/api/v1/ops/backup-schedule")
def ops_backup_schedule(_actor: Actor = Depends(get_actor)):
    from ops_autopilot.backup_schedule import schedule_status
    return schedule_status()


@router.get("/api/v1/ops/readiness")
def ops_readiness(target: Optional[str] = None, _actor: Actor = Depends(get_actor)):
    from ops_autopilot.readiness import upgrade_readiness
    return upgrade_readiness(target_version=target)


@router.get("/api/v1/ops/plans")
def ops_plans(limit: int = 20, _actor: Actor = Depends(get_actor)):
    from ops_autopilot.store import list_maintenance_plans
    return {"plans": list_maintenance_plans(limit=limit)}


@router.post("/api/v1/ops/plans")
def ops_plan_create(body: PlanBody, _actor: Actor = Depends(require_role("operator"))):
    from ops_autopilot.readiness import plan_maintenance
    return plan_maintenance(title=body.title)


@router.post("/api/v1/ops/daemon/start")
def ops_daemon_start(_actor: Actor = Depends(require_role("operator"))):
    """Start the agentboxd daemon (dashboard quick action)."""
    from ops.lifecycle import start
    return start(components=["daemon"])


class RunbookRunBody(BaseModel):
    dry_run: bool = True
    allow_high_risk: bool = False


class RestoreDrillBody(BaseModel):
    backup_id: Optional[str] = None
    approve_destructive: bool = False
    note: Optional[str] = None


class IncidentCloseBody(BaseModel):
    message: str = "closed via API"
    confirmed: bool = True


@router.get("/api/v1/ops/health-score")
def ops_health_score(_actor: Actor = Depends(get_actor)):
    from ops_autopilot.health_registry import evaluate
    return evaluate(persist=True)


@router.get("/api/v1/ops/incidents")
def ops_incidents(status: Optional[str] = None, limit: int = 50, _actor: Actor = Depends(get_actor)):
    from ops_autopilot.incidents import list_incidents
    items = list_incidents(status=status, limit=limit)
    return {"incidents": items, "count": len(items)}


@router.get("/api/v1/ops/incidents/{incident_id}")
def ops_incident_get(incident_id: str, _actor: Actor = Depends(get_actor)):
    from ops_autopilot.incidents import get_incident
    inc = get_incident(incident_id)
    if not inc:
        raise HTTPException(404, "incident not found")
    return inc


@router.post("/api/v1/ops/incidents/{incident_id}/close")
def ops_incident_close(incident_id: str, body: IncidentCloseBody, _actor: Actor = Depends(require_role("operator"))):
    from ops_autopilot.incidents import close_incident
    try:
        return close_incident(
            incident_id,
            message=body.message,
            resolution={"message": body.message, "confirmed": body.confirmed},
        )
    except ValueError as e:
        raise HTTPException(400, str(e))


@router.get("/api/v1/ops/runbooks")
def ops_runbooks(_actor: Actor = Depends(get_actor)):
    from ops_autopilot.runbooks import list_runbooks
    items = list_runbooks()
    return {"runbooks": items, "count": len(items)}


@router.post("/api/v1/ops/runbooks/{runbook_id}/run")
def ops_runbook_run(runbook_id: str, body: RunbookRunBody, _actor: Actor = Depends(require_role("operator"))):
    from ops_autopilot.runbooks import run_runbook
    try:
        return run_runbook(
            runbook_id,
            dry_run=body.dry_run,
            allow_high_risk=body.allow_high_risk,
            triggered_by="api",
        )
    except ValueError as e:
        raise HTTPException(404, str(e))


@router.post("/api/v1/ops/restore-drill")
def ops_restore_drill(body: RestoreDrillBody = RestoreDrillBody(), _actor: Actor = Depends(require_role("operator"))):
    from ops_autopilot.restore_drill import run_restore_drill
    return run_restore_drill(
        backup_id=body.backup_id,
        approve_destructive=body.approve_destructive,
        note=body.note or "api restore-drill",
    )


@router.get("/api/v1/ops/restore-drills")
def ops_restore_drills(limit: int = 20, _actor: Actor = Depends(get_actor)):
    from ops_autopilot.restore_drill import list_drills
    items = list_drills(limit=limit)
    return {"drills": items, "count": len(items)}


@router.post("/api/v1/ops/anomaly-scan")
def ops_anomaly_scan(persist: bool = True, raise_incidents: bool = True, _actor: Actor = Depends(require_role("operator"))):
    from ops_autopilot.anomalies import detect
    return detect(persist=persist, raise_incidents=raise_incidents)

