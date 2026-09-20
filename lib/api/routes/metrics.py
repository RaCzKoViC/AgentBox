from __future__ import annotations
from fastapi import APIRouter, Depends
from ..deps import Actor, get_actor, system_stats

router = APIRouter(tags=["metrics"])

@router.get("/api/v1/metrics")
def metrics(_actor: Actor = Depends(get_actor)):
    from storage import db as dbmod
    conn = dbmod.connect()
    try:
        rows = conn.execute(
            "SELECT metric_name, metric_value, labels_json, created_at FROM metrics ORDER BY created_at DESC LIMIT 200"
        ).fetchall()
        items = [dict(r) for r in rows]
    except Exception:
        items = []
    finally:
        conn.close()
    ws_count = 0
    try:
        from ..websocket import HUB
        ws_count = HUB.count
    except Exception:
        pass
    return {"items": items, "websocket_connections": ws_count, "system": system_stats()}

@router.get("/api/v1/metrics/system")
def metrics_system(_actor: Actor = Depends(get_actor)):
    return system_stats()

@router.get("/api/v1/metrics/tasks")
def metrics_tasks(_actor: Actor = Depends(get_actor)):
    from storage import db as dbmod
    return {"by_status": dbmod.count_by_status(), "queue": dbmod.queue_stats()}

@router.get("/api/v1/metrics/agents")
def metrics_agents(_actor: Actor = Depends(get_actor)):
    from storage import db as dbmod
    conn = dbmod.connect()
    try:
        rows = conn.execute("SELECT status, COUNT(*) AS c FROM agents GROUP BY status").fetchall()
        return {"by_status": {r["status"]: r["c"] for r in rows}}
    finally:
        conn.close()

@router.get("/api/v1/metrics/providers")
def metrics_providers(_actor: Actor = Depends(get_actor)):
    return {"items": [
        {"name": "codex", "available": True},
        {"name": "claude", "available": False},
        {"name": "stub", "available": True},
    ]}
