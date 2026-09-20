from __future__ import annotations
from typing import Optional
from fastapi import APIRouter, Depends, Query
from ..deps import Actor, get_actor, require_role, audit
from ..errors import APIError
from ..schemas import CommentIn

router = APIRouter(tags=["approvals"])

@router.get("/api/v1/approvals")
def list_approvals(status: Optional[str] = "pending", limit: int = Query(50, ge=1, le=500), _actor: Actor = Depends(get_actor)):
    from policy import approvals as appr
    items = appr.list_approvals(status=status)
    return {"items": items[:limit]}

@router.get("/api/v1/approvals/{approval_id}")
def get_approval(approval_id: str, _actor: Actor = Depends(get_actor)):
    from policy import approvals as appr
    a = appr.get_approval(approval_id)
    if not a:
        raise APIError("APPROVAL_NOT_FOUND", "Approval not found", status_code=404)
    return a

@router.post("/api/v1/approvals/{approval_id}/approve")
def approve(approval_id: str, body: CommentIn = CommentIn(), actor: Actor = Depends(require_role("operator"))):
    from policy import approvals as appr
    out = appr.resolve_approval(approval_id, status="approved", reason=body.comment or "approved via API")
    audit("POST", f"/api/v1/approvals/{approval_id}/approve", actor, 200)
    return out

@router.post("/api/v1/approvals/{approval_id}/reject")
def reject(approval_id: str, body: CommentIn = CommentIn(), actor: Actor = Depends(require_role("operator"))):
    from policy import approvals as appr
    out = appr.resolve_approval(approval_id, status="rejected", reason=body.reason or body.comment or "rejected via API")
    audit("POST", f"/api/v1/approvals/{approval_id}/reject", actor, 200)
    return out
