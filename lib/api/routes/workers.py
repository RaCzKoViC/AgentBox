"""Worker registry + enrollment + heartbeat REST API (v5.1)."""
from __future__ import annotations

from typing import Any, Optional

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field

from ..deps import Actor, get_actor, require_role, require_worker, audit, is_tailscale_addr
from ..errors import APIError

router = APIRouter(tags=["workers"])


class EnrollBody(BaseModel):
    token: str
    name: str = "worker"
    hostname: str = ""
    tailscale_ip: str = ""
    platform: str = ""
    architecture: str = ""
    version: str = "5.1.0"
    capabilities: dict[str, Any] = Field(default_factory=dict)
    labels: list[str] = Field(default_factory=list)
    max_parallel_tasks: int = 1
    protocol_version: int = 1


class HeartbeatBody(BaseModel):
    cpu_percent: float = 0.0
    memory_percent: float = 0.0
    disk_percent: float = 0.0
    load1: float = 0.0
    active_tasks: int = 0
    version: str = ""
    health: str = "healthy"
    metadata: dict[str, Any] = Field(default_factory=dict)


class ResultBody(BaseModel):
    ok: bool = True
    result: dict[str, Any] = Field(default_factory=dict)
    error: str = ""


class QuarantineBody(BaseModel):
    reason: str = "manual"


class AssignBody(BaseModel):
    task_id: str
    run_id: str = ""
    requirements: dict[str, Any] = Field(default_factory=dict)
    payload: dict[str, Any] = Field(default_factory=dict)
    worker_id: Optional[str] = None


# ---- public enrollment (token-gated; Tailscale/loopback) ----

@router.post("/api/v1/workers/enroll")
def enroll_worker(body: EnrollBody, request: Request):
    remote = request.client.host if request.client else ""
    if not is_tailscale_addr(remote):
        raise APIError("FORBIDDEN", "enrollment only from Tailscale/loopback", status_code=403)
    from distributed import enrollment
    try:
        result = enrollment.enroll(
            body.token,
            name=body.name,
            hostname=body.hostname,
            tailscale_ip=body.tailscale_ip or remote,
            platform=body.platform,
            architecture=body.architecture,
            version=body.version,
            capabilities=body.capabilities,
            labels=body.labels,
            max_parallel_tasks=body.max_parallel_tasks,
            protocol_version=body.protocol_version,
            auto_approve=True,
        )
    except PermissionError as e:
        raise APIError("ENROLL_DENIED", str(e), status_code=403) from e
    except ValueError as e:
        raise APIError("ENROLL_INVALID", str(e), status_code=400) from e
    audit("POST", "/api/v1/workers/enroll", Actor("worker", result["worker_id"]), 200, remote=remote)
    return result


@router.post("/api/v1/workers/heartbeat")
def heartbeat(body: HeartbeatBody, actor: Actor = Depends(require_worker)):
    from distributed import heartbeat as hb
    try:
        return hb.process_heartbeat(
            actor.worker_id,
            cpu_percent=body.cpu_percent,
            memory_percent=body.memory_percent,
            disk_percent=body.disk_percent,
            load1=body.load1,
            active_tasks=body.active_tasks,
            version=body.version,
            health=body.health,
            metadata=body.metadata,
        )
    except KeyError as e:
        raise APIError("WORKER_NOT_FOUND", str(e), status_code=404) from e


@router.get("/api/v1/workers/{worker_id}/assignment")
def get_assignment(worker_id: str, actor: Actor = Depends(require_worker)):
    if actor.worker_id != worker_id and actor.role != "admin":
        raise APIError("FORBIDDEN", "worker mismatch", status_code=403)
    from distributed import routing
    asgn = routing.poll_assignment(worker_id)
    return {"assignment": asgn}


@router.post("/api/v1/workers/{worker_id}/assignment/{assignment_id}/accept")
def accept_assignment(worker_id: str, assignment_id: str, actor: Actor = Depends(require_worker)):
    if actor.worker_id != worker_id:
        raise APIError("FORBIDDEN", "worker mismatch", status_code=403)
    from distributed import routing
    try:
        return routing.accept_assignment(worker_id, assignment_id)
    except KeyError as e:
        raise APIError("NOT_FOUND", str(e), status_code=404) from e
    except RuntimeError as e:
        raise APIError("CONFLICT", str(e), status_code=409) from e


@router.post("/api/v1/workers/{worker_id}/assignment/{assignment_id}/result")
def assignment_result(
    worker_id: str, assignment_id: str, body: ResultBody, actor: Actor = Depends(require_worker)
):
    if actor.worker_id != worker_id:
        raise APIError("FORBIDDEN", "worker mismatch", status_code=403)
    from distributed import routing
    try:
        return routing.complete_assignment(
            worker_id, assignment_id, ok=body.ok, result=body.result, error=body.error
        )
    except KeyError as e:
        raise APIError("NOT_FOUND", str(e), status_code=404) from e


@router.post("/api/v1/workers/{worker_id}/artifacts")
def upload_artifacts_stub(worker_id: str, actor: Actor = Depends(require_worker)):
    """Stub artifact upload endpoint — metadata only in v5.1."""
    if actor.worker_id != worker_id:
        raise APIError("FORBIDDEN", "worker mismatch", status_code=403)
    return {"ok": True, "accepted": True, "note": "metadata stub — full chunked upload in later patch"}


# ---- admin APIs ----

@router.get("/api/v1/workers")
def list_workers(status: Optional[str] = None, _actor: Actor = Depends(get_actor)):
    from distributed import registry
    registry.mark_offline_stale()
    items = registry.list_workers(status=status)
    return {"items": items, "counts": registry.counts()}


@router.get("/api/v1/workers/{worker_id}")
def show_worker(worker_id: str, _actor: Actor = Depends(get_actor)):
    from distributed import registry
    from storage import db as dbmod
    w = registry.get_worker(worker_id)
    if not w:
        raise APIError("WORKER_NOT_FOUND", "Worker not found", status_code=404)
    with dbmod.connect() as conn:
        metrics = [
            dict(r)
            for r in conn.execute(
                "SELECT * FROM worker_metrics WHERE worker_id=? ORDER BY id DESC LIMIT 20",
                (w["id"],),
            ).fetchall()
        ]
        events = [
            dict(r)
            for r in conn.execute(
                "SELECT * FROM worker_events WHERE worker_id=? ORDER BY id DESC LIMIT 50",
                (w["id"],),
            ).fetchall()
        ]
        assignments = [
            dict(r)
            for r in conn.execute(
                "SELECT * FROM worker_assignments WHERE worker_id=? ORDER BY assigned_at DESC LIMIT 20",
                (w["id"],),
            ).fetchall()
        ]
    return {**w, "metrics": metrics, "events": events, "assignments": assignments}


@router.post("/api/v1/workers/token")
def create_token(ttl_minutes: int = 60, actor: Actor = Depends(require_role("admin"))):
    from distributed import enrollment
    tok = enrollment.create_enrollment_token(ttl_minutes=ttl_minutes)
    audit("POST", "/api/v1/workers/token", actor, 200)
    return tok


@router.post("/api/v1/workers/assign")
def assign_task(body: AssignBody, actor: Actor = Depends(require_role("operator"))):
    """Admin/operator: route + create assignment (policy/budget still apply upstream)."""
    from distributed import routing
    # light policy gate — sensitive actions still go through existing engines
    try:
        from policy import risk as riskmod
        assessment = riskmod.assess_risk(action="agent.delegate", resource=body.task_id or "worker")
        decision = (assessment.get("decision") or assessment.get("risk_level") or "").lower()
        if decision in ("deny", "blocked", "critical") and assessment.get("decision") == "deny":
            raise APIError("RISK_BLOCKED", "risk engine denied assign", status_code=403)
    except APIError:
        raise
    except Exception:
        pass
    wid = body.worker_id
    decision = None
    if not wid:
        decision = routing.select_worker(task_id=body.task_id, requirements=body.requirements)
        wid = decision.worker_id
    if not wid:
        raise APIError("NO_WORKER", "no eligible worker", status_code=409)
    try:
        asgn = routing.create_assignment(
            wid, body.task_id, run_id=body.run_id, payload=body.payload or {"mode": "stub"}
        )
    except PermissionError as e:
        raise APIError("ASSIGN_DENIED", str(e), status_code=403) from e
    audit("POST", "/api/v1/workers/assign", actor, 200, task_id=body.task_id)
    return {"assignment": asgn, "decision": decision.to_dict() if decision else {"worker_id": wid}}


@router.post("/api/v1/workers/{worker_id}/drain")
def drain_worker(worker_id: str, actor: Actor = Depends(require_role("admin"))):
    from distributed import quarantine
    try:
        w = quarantine.drain(worker_id)
    except KeyError:
        raise APIError("WORKER_NOT_FOUND", "Worker not found", status_code=404)
    audit("POST", f"/api/v1/workers/{worker_id}/drain", actor, 200)
    return w


@router.post("/api/v1/workers/{worker_id}/quarantine")
def quarantine_worker(
    worker_id: str, body: QuarantineBody = QuarantineBody(), actor: Actor = Depends(require_role("admin"))
):
    from distributed import quarantine
    try:
        w = quarantine.quarantine(worker_id, reason=body.reason)
    except KeyError:
        raise APIError("WORKER_NOT_FOUND", "Worker not found", status_code=404)
    audit("POST", f"/api/v1/workers/{worker_id}/quarantine", actor, 200)
    return w


@router.post("/api/v1/workers/{worker_id}/unquarantine")
def unquarantine_worker(worker_id: str, actor: Actor = Depends(require_role("admin"))):
    from distributed import quarantine
    try:
        w = quarantine.unquarantine(worker_id)
    except KeyError:
        raise APIError("WORKER_NOT_FOUND", "Worker not found", status_code=404)
    audit("POST", f"/api/v1/workers/{worker_id}/unquarantine", actor, 200)
    return w


@router.delete("/api/v1/workers/{worker_id}")
def delete_worker(worker_id: str, actor: Actor = Depends(require_role("admin"))):
    from distributed import registry
    try:
        ok = registry.remove_worker(worker_id)
    except RuntimeError as e:
        raise APIError("CONFLICT", str(e), status_code=409) from e
    if not ok:
        raise APIError("WORKER_NOT_FOUND", "Worker not found", status_code=404)
    audit("DELETE", f"/api/v1/workers/{worker_id}", actor, 200)
    return {"ok": True}


@router.post("/api/v1/workers/failover/dry-run")
def failover_dry_run(
    failed_worker_id: str, task_id: str = "", actor: Actor = Depends(require_role("admin"))
):
    from distributed import failover
    plan = failover.dry_run(failed_worker_id, task_id=task_id)
    audit("POST", "/api/v1/workers/failover/dry-run", actor, 200)
    return plan
