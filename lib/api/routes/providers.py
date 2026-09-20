from __future__ import annotations
from fastapi import APIRouter, Depends
from ..deps import Actor, get_actor
from ..errors import APIError

router = APIRouter(tags=["providers"])
PROVIDERS = [
    {"name": "codex", "available": True, "active_runs": 0, "errors_last_hour": 0},
    {"name": "claude", "available": False, "active_runs": 0, "errors_last_hour": 0},
    {"name": "stub", "available": True, "active_runs": 0, "errors_last_hour": 0},
]

@router.get("/api/v1/providers")
def list_providers(_actor: Actor = Depends(get_actor)):
    return {"items": PROVIDERS}

@router.get("/api/v1/providers/{provider}")
def get_provider(provider: str, _actor: Actor = Depends(get_actor)):
    for p in PROVIDERS:
        if p["name"] == provider:
            return p
    raise APIError("PROVIDER_NOT_FOUND", "Unknown provider", status_code=404)

@router.get("/api/v1/providers/{provider}/health")
def provider_health(provider: str, _actor: Actor = Depends(get_actor)):
    p = get_provider(provider, _actor)
    return {"name": provider, "health": "ok" if p["available"] else "down"}
