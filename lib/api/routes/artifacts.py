from __future__ import annotations
from pathlib import Path
from fastapi import APIRouter, Depends
from fastapi.responses import FileResponse
from ..deps import Actor, get_actor, DATA_ROOT
from ..errors import APIError

router = APIRouter(tags=["artifacts"])

def _safe_path(path: str) -> Path:
    root = (DATA_ROOT / "artifacts").resolve()
    p = Path(path).resolve()
    if not str(p).startswith(str(root)):
        alt = (Path.home() / ".local/share/agentbox/v5/artifacts").resolve()
        if not str(p).startswith(str(alt)):
            raise APIError("PATH_DENIED", "Artifact path outside allowed root", status_code=403)
    if ".." in Path(path).parts:
        raise APIError("PATH_DENIED", "Path traversal blocked", status_code=403)
    return p

@router.get("/api/v1/artifacts")
def list_artifacts(task_id: str | None = None, _actor: Actor = Depends(get_actor)):
    from artifacts import store as art
    if task_id:
        return {"items": art.list_artifacts(task_id=task_id)}
    return {"items": art.list_artifacts()}

@router.get("/api/v1/artifacts/{artifact_id}")
def get_artifact(artifact_id: str, _actor: Actor = Depends(get_actor)):
    from artifacts import store as art
    a = art.get_artifact(artifact_id)
    if not a:
        raise APIError("ARTIFACT_NOT_FOUND", "Artifact not found", status_code=404)
    return a

@router.get("/api/v1/artifacts/{artifact_id}/download")
def download_artifact(artifact_id: str, _actor: Actor = Depends(get_actor)):
    from artifacts import store as art
    a = art.get_artifact(artifact_id)
    if not a:
        raise APIError("ARTIFACT_NOT_FOUND", "Artifact not found", status_code=404)
    p = _safe_path(a["path"])
    if not p.is_file():
        raise APIError("ARTIFACT_MISSING", "File missing on disk", status_code=404)
    return FileResponse(str(p), filename=p.name)

_safe_path = _safe_path
