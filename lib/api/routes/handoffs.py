from __future__ import annotations
from typing import Optional
from fastapi import APIRouter, Depends, Query
from ..deps import Actor, get_actor, require_role, audit
from ..errors import APIError
from ..schemas import HandoffCreate, CommentIn

router = APIRouter(tags=["handoffs"])

@router.get("/api/v1/handoffs")
def list_handoffs(status: Optional[str] = None, limit: int = Query(50, ge=1, le=500), _actor: Actor = Depends(get_actor)):
    from storage import db as dbmod
    conn = dbmod.connect()
    try:
        # table may be agent_handoffs
        for table in ("agent_handoffs", "handoffs"):
            try:
                if status:
                    rows = conn.execute(f"SELECT * FROM {table} WHERE status=? ORDER BY created_at DESC LIMIT ?", (status, limit)).fetchall()
                else:
                    rows = conn.execute(f"SELECT * FROM {table} ORDER BY created_at DESC LIMIT ?", (limit,)).fetchall()
                return {"items": [dict(r) for r in rows]}
            except Exception:
                continue
        return {"items": []}
    finally:
        conn.close()

@router.get("/api/v1/handoffs/{handoff_id}")
def get_handoff(handoff_id: str, _actor: Actor = Depends(get_actor)):
    from storage import db as dbmod
    conn = dbmod.connect()
    try:
        for table in ("agent_handoffs", "handoffs"):
            try:
                row = conn.execute(f"SELECT * FROM {table} WHERE id=?", (handoff_id,)).fetchone()
                if row:
                    return dict(row)
            except Exception:
                continue
        raise APIError("HANDOFF_NOT_FOUND", "Handoff not found", status_code=404)
    finally:
        conn.close()

@router.post("/api/v1/handoffs")
def create_handoff(body: HandoffCreate, actor: Actor = Depends(require_role("operator"))):
    from handoffs import engine
    out = engine.create_handoff(
        task_id=body.task_id,
        source_agent=body.source_agent,
        target_agent=body.target_agent,
        reason=body.reason,
        required=body.required,
    )
    audit("POST", "/api/v1/handoffs", actor, 201, task_id=body.task_id)
    return out

@router.post("/api/v1/handoffs/{handoff_id}/approve")
def approve_handoff(handoff_id: str, body: CommentIn = CommentIn(), actor: Actor = Depends(require_role("operator"))):
    from handoffs import engine
    fn = getattr(engine, "accept_handoff", None) or getattr(engine, "approve_handoff", None)
    if not fn:
        raise APIError("NOT_SUPPORTED", "approve not available", status_code=501)
    out = fn(handoff_id)
    audit("POST", f"/api/v1/handoffs/{handoff_id}/approve", actor, 200)
    return out

@router.post("/api/v1/handoffs/{handoff_id}/reject")
def reject_handoff(handoff_id: str, body: CommentIn = CommentIn(), actor: Actor = Depends(require_role("operator"))):
    from handoffs import engine
    out = engine.reject_handoff(handoff_id, reason=body.reason or body.comment or "rejected")
    audit("POST", f"/api/v1/handoffs/{handoff_id}/reject", actor, 200)
    return out

@router.post("/api/v1/handoffs/{handoff_id}/retry")
def retry_handoff(handoff_id: str, actor: Actor = Depends(require_role("operator"))):
    from storage import db as dbmod
    conn = dbmod.connect()
    try:
        for table in ("agent_handoffs", "handoffs"):
            try:
                cur = conn.execute(f"UPDATE {table} SET status='pending' WHERE id=?", (handoff_id,))
                conn.commit()
                if cur.rowcount:
                    audit("POST", f"/api/v1/handoffs/{handoff_id}/retry", actor, 200)
                    return {"id": handoff_id, "status": "pending"}
            except Exception:
                continue
        raise APIError("HANDOFF_NOT_FOUND", "Handoff not found", status_code=404)
    finally:
        conn.close()
