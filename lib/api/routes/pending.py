from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel

from ..deps import Actor, audit, get_actor, require_role
from ..errors import APIError

router = APIRouter(tags=["pending"])


class PendingCreate(BaseModel):
    text: str
    context: str = ""
    source: str = "api"


class PendingPatch(BaseModel):
    status: str = "resolved"
    resolution: str = ""


@router.get("/api/v1/pending")
def list_pending(
    status: str = Query("open", pattern="^(open|resolved|all)$"),
    _actor: Actor = Depends(get_actor),
):
    from ops import pending
    items = pending.list_items(status)
    return {"items": items, "total": len(items), "status": status}


@router.get("/api/v1/pending/{item_id}")
def get_pending(item_id: str, _actor: Actor = Depends(get_actor)):
    from ops import pending
    it = pending.get(item_id)
    if not it:
        raise APIError("PENDING_NOT_FOUND", "Pending item does not exist", status_code=404)
    return it


@router.post("/api/v1/pending")
def create_pending(body: PendingCreate, actor: Actor = Depends(require_role("operator"))):
    from ops import pending
    if not body.text.strip():
        raise APIError("VALIDATION_ERROR", "text must not be empty", status_code=422)
    it = pending.add(body.text, body.context, body.source or "api")
    audit("POST", "/api/v1/pending", actor, 201)
    return it


@router.patch("/api/v1/pending/{item_id}")
def patch_pending(item_id: str, body: PendingPatch, actor: Actor = Depends(require_role("operator"))):
    from ops import pending
    if body.status not in pending.STATUSES:
        raise APIError("VALIDATION_ERROR", "status must be 'open' or 'resolved'", status_code=422)
    it = pending.set_status(item_id, body.status, body.resolution, getattr(actor, "actor", "") or actor.role)
    if not it:
        raise APIError("PENDING_NOT_FOUND", "Pending item does not exist", status_code=404)
    audit("PATCH", f"/api/v1/pending/{item_id}", actor, 200)
    return it


@router.post("/api/v1/pending/{item_id}/resolve")
def resolve_pending(item_id: str, body: Optional[PendingPatch] = None,
                    actor: Actor = Depends(require_role("operator"))):
    return patch_pending(item_id, PendingPatch(status="resolved", resolution=(body.resolution if body else "")), actor)
