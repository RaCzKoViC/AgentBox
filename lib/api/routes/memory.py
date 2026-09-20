from __future__ import annotations
from fastapi import APIRouter, Depends, Query
from ..deps import Actor, get_actor

router = APIRouter(tags=["memory"])

@router.get("/api/v1/memory")
def list_memory(limit: int = Query(50, ge=1, le=500), _actor: Actor = Depends(get_actor)):
    from storage import db as dbmod
    conn = dbmod.connect()
    try:
        rows = conn.execute("SELECT * FROM memories ORDER BY updated_at DESC LIMIT ?", (limit,)).fetchall()
        return {"items": [dict(r) for r in rows]}
    finally:
        conn.close()

@router.get("/api/v1/memory/search")
def search_memory(q: str = Query(...), limit: int = 50, _actor: Actor = Depends(get_actor)):
    from storage import db as dbmod
    conn = dbmod.connect()
    try:
        rows = conn.execute(
            "SELECT * FROM memories WHERE content LIKE ? OR title LIKE ? ORDER BY updated_at DESC LIMIT ?",
            (f"%{q}%", f"%{q}%", limit),
        ).fetchall()
        return {"items": [dict(r) for r in rows], "q": q}
    finally:
        conn.close()

@router.get("/api/v1/memory/project/{project_id}")
def memory_project(project_id: str, _actor: Actor = Depends(get_actor)):
    from storage import db as dbmod
    conn = dbmod.connect()
    try:
        rows = conn.execute(
            "SELECT * FROM memories WHERE scope='project' AND scope_key=? ORDER BY updated_at DESC LIMIT 100",
            (project_id,),
        ).fetchall()
        return {"items": [dict(r) for r in rows]}
    finally:
        conn.close()

@router.get("/api/v1/memory/task/{task_id}")
def memory_task(task_id: str, _actor: Actor = Depends(get_actor)):
    from storage import db as dbmod
    conn = dbmod.connect()
    try:
        rows = conn.execute(
            "SELECT * FROM memories WHERE scope='task' AND scope_key=? ORDER BY updated_at DESC LIMIT 100",
            (task_id,),
        ).fetchall()
        return {"items": [dict(r) for r in rows]}
    finally:
        conn.close()
