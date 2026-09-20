from __future__ import annotations
from typing import Optional
from fastapi import APIRouter, Depends, Query
from ..deps import Actor, get_actor, require_role, audit
from ..errors import APIError
from ..schemas import TaskCreate

router = APIRouter(tags=["tasks"])

@router.get("/api/v1/tasks")
def list_tasks(
    status: Optional[str] = None,
    project_id: Optional[str] = None,
    provider: Optional[str] = None,
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
    _actor: Actor = Depends(get_actor),
):
    from storage import db as dbmod
    tasks = dbmod.list_tasks(status=status)
    if project_id:
        tasks = [t for t in tasks if t.get("project_id") == project_id]
    if provider:
        tasks = [t for t in tasks if t.get("provider") == provider]
    total = len(tasks)
    return {"items": tasks[offset:offset+limit], "total": total, "limit": limit, "offset": offset}

@router.post("/api/v1/tasks")
def create_task(body: TaskCreate, actor: Actor = Depends(require_role("operator"))):
    from storage import db as dbmod
    project = body.project or body.project_id or "/tmp/agentbox-api"
    t = dbmod.create_task(
        project_id=project,
        title=body.title,
        description=body.description,
        provider=body.provider,
        model=body.model,
        priority=body.priority,
    )
    audit("POST", "/api/v1/tasks", actor, 201, task_id=t.get("id", ""))
    return t

@router.get("/api/v1/tasks/{task_id}")
def get_task(task_id: str, _actor: Actor = Depends(get_actor)):
    from storage import db as dbmod
    t = dbmod.get_task(task_id)
    if not t:
        raise APIError("TASK_NOT_FOUND", "Task does not exist", status_code=404)
    return t

@router.post("/api/v1/tasks/{task_id}/queue")
def queue_task(task_id: str, actor: Actor = Depends(require_role("operator"))):
    from storage import db as dbmod
    if not dbmod.get_task(task_id):
        raise APIError("TASK_NOT_FOUND", "Task does not exist", status_code=404)
    out = dbmod.set_task_status(task_id, "queued")
    audit("POST", f"/api/v1/tasks/{task_id}/queue", actor, 200, task_id=task_id)
    return out

@router.post("/api/v1/tasks/{task_id}/pause")
def pause_task(task_id: str, actor: Actor = Depends(require_role("operator"))):
    from storage import db as dbmod
    if not dbmod.get_task(task_id):
        raise APIError("TASK_NOT_FOUND", "Task does not exist", status_code=404)
    out = dbmod.set_task_status(task_id, "paused")
    audit("POST", f"/api/v1/tasks/{task_id}/pause", actor, 200, task_id=task_id)
    return out

@router.post("/api/v1/tasks/{task_id}/resume")
def resume_task(task_id: str, actor: Actor = Depends(require_role("operator"))):
    from storage import db as dbmod
    if not dbmod.get_task(task_id):
        raise APIError("TASK_NOT_FOUND", "Task does not exist", status_code=404)
    out = dbmod.set_task_status(task_id, "queued")
    audit("POST", f"/api/v1/tasks/{task_id}/resume", actor, 200, task_id=task_id)
    return out

@router.post("/api/v1/tasks/{task_id}/cancel")
def cancel_task(task_id: str, actor: Actor = Depends(require_role("operator"))):
    from storage import db as dbmod
    if not dbmod.get_task(task_id):
        raise APIError("TASK_NOT_FOUND", "Task does not exist", status_code=404)
    out = dbmod.set_task_status(task_id, "cancelled")
    audit("POST", f"/api/v1/tasks/{task_id}/cancel", actor, 200, task_id=task_id)
    return out

@router.get("/api/v1/tasks/{task_id}/timeline")
def task_timeline(task_id: str, limit: int = 200, _actor: Actor = Depends(get_actor)):
    try:
        from observability import timeline as tl
        return {"items": tl.timeline(task_id, limit=limit)}
    except Exception:
        from storage import db as dbmod
        return {"items": dbmod.list_events(task_id=task_id, limit=limit)}

@router.get("/api/v1/tasks/{task_id}/artifacts")
def task_artifacts(task_id: str, _actor: Actor = Depends(get_actor)):
    from artifacts import store as art
    return {"items": art.list_artifacts(task_id=task_id)}
