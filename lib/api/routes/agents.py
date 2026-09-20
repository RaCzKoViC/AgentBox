from __future__ import annotations
from fastapi import APIRouter, Depends
from ..deps import Actor, get_actor, require_role, audit
from ..errors import APIError

router = APIRouter(tags=["agents"])

@router.get("/api/v1/agents")
def list_agents(_actor: Actor = Depends(get_actor)):
    from storage import db as dbmod
    conn = dbmod.connect()
    try:
        rows = conn.execute("SELECT * FROM agents ORDER BY name").fetchall()
        return {"items": [dict(r) for r in rows]}
    finally:
        conn.close()

@router.get("/api/v1/agents/{agent_name}")
def get_agent(agent_name: str, _actor: Actor = Depends(get_actor)):
    from storage import db as dbmod
    conn = dbmod.connect()
    try:
        row = conn.execute("SELECT * FROM agents WHERE name=? OR id=?", (agent_name, agent_name)).fetchone()
        if not row:
            raise APIError("AGENT_NOT_FOUND", "Agent not found", status_code=404)
        return dict(row)
    finally:
        conn.close()

@router.get("/api/v1/agents/{agent_name}/status")
def agent_status(agent_name: str, _actor: Actor = Depends(get_actor)):
    a = get_agent(agent_name, _actor)
    return {"name": a.get("name"), "status": a.get("status"), "provider": a.get("provider"), "model": a.get("model")}

@router.get("/api/v1/agents/{agent_name}/runs")
def agent_runs(agent_name: str, _actor: Actor = Depends(get_actor)):
    from storage import db as dbmod
    conn = dbmod.connect()
    try:
        rows = conn.execute(
            "SELECT * FROM agent_runs WHERE agent_name=? ORDER BY created_at DESC LIMIT 50",
            (agent_name,),
        ).fetchall()
        return {"items": [dict(r) for r in rows]}
    except Exception:
        return {"items": []}
    finally:
        conn.close()

@router.post("/api/v1/agents/{agent_name}/enable")
def enable_agent(agent_name: str, actor: Actor = Depends(require_role("admin"))):
    from storage import db as dbmod
    conn = dbmod.connect()
    try:
        cur = conn.execute("UPDATE agents SET status='active' WHERE name=? OR id=?", (agent_name, agent_name))
        conn.commit()
        if cur.rowcount == 0:
            raise APIError("AGENT_NOT_FOUND", "Agent not found", status_code=404)
        audit("POST", f"/api/v1/agents/{agent_name}/enable", actor, 200)
        return {"ok": True, "status": "active"}
    finally:
        conn.close()

@router.post("/api/v1/agents/{agent_name}/disable")
def disable_agent(agent_name: str, actor: Actor = Depends(require_role("admin"))):
    from storage import db as dbmod
    conn = dbmod.connect()
    try:
        cur = conn.execute("UPDATE agents SET status='disabled' WHERE name=? OR id=?", (agent_name, agent_name))
        conn.commit()
        if cur.rowcount == 0:
            raise APIError("AGENT_NOT_FOUND", "Agent not found", status_code=404)
        audit("POST", f"/api/v1/agents/{agent_name}/disable", actor, 200)
        return {"ok": True, "status": "disabled"}
    finally:
        conn.close()
