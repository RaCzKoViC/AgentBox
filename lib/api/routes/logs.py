from __future__ import annotations
import re
from pathlib import Path
from fastapi import APIRouter, Depends, Query
from ..deps import Actor, get_actor, DATA_ROOT

router = APIRouter(tags=["logs"])
_SECRET_RE = re.compile(r"(?i)(token|password|api[_-]?key|secret|authorization)\s*[:=]\s*\S+")

def _sanitize(line: str) -> str:
    return _SECRET_RE.sub(r"\1=[redacted]", line)

def _tail(path: Path, limit: int) -> list[str]:
    if not path.is_file():
        return []
    try:
        lines = path.read_text(errors="replace").splitlines()
        return [_sanitize(x) for x in lines[-limit:]]
    except Exception:
        return []

@router.get("/api/v1/logs")
def logs(limit: int = Query(100, ge=1, le=2000), _actor: Actor = Depends(get_actor)):
    return {
        "daemon": _tail(DATA_ROOT / "logs" / "daemon.log", limit),
        "web": _tail(DATA_ROOT / "logs" / "web.log", limit),
    }

@router.get("/api/v1/logs/daemon")
def logs_daemon(limit: int = 200, _actor: Actor = Depends(get_actor)):
    return {"items": _tail(DATA_ROOT / "logs" / "daemon.log", limit)}

@router.get("/api/v1/logs/task/{task_id}")
def logs_task(task_id: str, limit: int = 200, _actor: Actor = Depends(get_actor)):
    from storage import db as dbmod
    events = dbmod.list_events(task_id=task_id, limit=limit)
    return {"items": [{"ts": e.get("created_at") or e.get("ts"), "message": _sanitize(str(e.get("message") or ""))} for e in events]}

@router.get("/api/v1/logs/run/{run_id}")
def logs_run(run_id: str, limit: int = 200, _actor: Actor = Depends(get_actor)):
    from storage import db as dbmod
    r = dbmod.get_run(run_id)
    if not r:
        return {"items": []}
    return logs_task(r.get("task_id", ""), limit, _actor)
