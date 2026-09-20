from __future__ import annotations
from typing import Optional
from fastapi import APIRouter, Depends, Query
from ..deps import Actor, get_actor, require_role, audit
from ..errors import APIError

router = APIRouter(tags=["runs"])

@router.get("/api/v1/runs")
def list_runs(task_id: Optional[str] = None, limit: int = Query(50, ge=1, le=500), _actor: Actor = Depends(get_actor)):
    from storage import db as dbmod
    runs = dbmod.list_runs(task_id=task_id)
    return {"items": runs[:limit], "total": len(runs)}

@router.get("/api/v1/runs/{run_id}")
def get_run(run_id: str, _actor: Actor = Depends(get_actor)):
    from storage import db as dbmod
    r = dbmod.get_run(run_id)
    if not r:
        raise APIError("RUN_NOT_FOUND", "Run does not exist", status_code=404)
    return r

@router.get("/api/v1/runs/{run_id}/logs")
def run_logs(run_id: str, limit: int = 200, _actor: Actor = Depends(get_actor)):
    from storage import db as dbmod
    r = dbmod.get_run(run_id)
    if not r:
        raise APIError("RUN_NOT_FOUND", "Run does not exist", status_code=404)
    events = dbmod.list_events(task_id=r.get("task_id"), limit=limit)
    lines = []
    for e in events:
        msg = str(e.get("message") or "")
        low = msg.lower()
        if any(s in low for s in ("token", "password", "api_key", "secret")):
            msg = "[redacted]"
        lines.append({"ts": e.get("created_at") or e.get("ts"), "kind": e.get("kind"), "message": msg})
    return {"items": lines}

@router.post("/api/v1/runs/{run_id}/cancel")
def cancel_run(run_id: str, actor: Actor = Depends(require_role("operator"))):
    from storage import db as dbmod
    r = dbmod.get_run(run_id)
    if not r:
        raise APIError("RUN_NOT_FOUND", "Run does not exist", status_code=404)
    out = dbmod.finish_run(run_id, status="cancelled", exit_code=130)
    audit("POST", f"/api/v1/runs/{run_id}/cancel", actor, 200)
    return out
