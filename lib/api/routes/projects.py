from __future__ import annotations
from fastapi import APIRouter, Depends
from ..deps import Actor, get_actor, require_role, audit
from ..schemas import ProjectCreate
from storage import db as dbmod

router = APIRouter(tags=["projects"])

@router.get("/api/v1/projects")
def list_projects(_actor: Actor = Depends(get_actor)):
    conn = dbmod.connect()
    try:
        rows = conn.execute(
            "SELECT project_id AS path, COUNT(*) AS tasks FROM tasks GROUP BY project_id ORDER BY path"
        ).fetchall()
        return {"items": [dict(r) for r in rows]}
    finally:
        conn.close()

@router.get("/api/v1/projects/{project_id}")
def get_project(project_id: str, _actor: Actor = Depends(get_actor)):
    conn = dbmod.connect()
    try:
        rows = conn.execute(
            "SELECT * FROM tasks WHERE project_id=? OR project_id LIKE ? ORDER BY created_at DESC LIMIT 50",
            (project_id, f"%{project_id}%"),
        ).fetchall()
        return {"project": project_id, "tasks": [dict(r) for r in rows]}
    finally:
        conn.close()

@router.post("/api/v1/projects")
def create_project(body: ProjectCreate, actor: Actor = Depends(require_role("admin"))):
    audit("POST", "/api/v1/projects", actor, 201)
    return {"path": body.path, "name": body.name or body.path, "ok": True}

@router.post("/api/v1/projects/refresh")
def refresh_projects(actor: Actor = Depends(require_role("admin"))):
    audit("POST", "/api/v1/projects/refresh", actor, 200)
    return list_projects(actor)
