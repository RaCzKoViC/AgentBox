"""Intelligence REST API (v5.2) — status, search, router."""
from __future__ import annotations

from typing import Any, Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from ..deps import Actor, get_actor, require_role

router = APIRouter(tags=["intelligence"])


class SearchBody(BaseModel):
    query: str
    project_id: Optional[str] = None
    top_k: int = 10


class RouterBody(BaseModel):
    task: str = ""
    task_type: Optional[str] = None
    privacy: str = "ANY_APPROVED"
    complexity: Optional[str] = None
    agent_role: str = "coder"
    budget_remaining: Optional[float] = None


@router.get("/api/v1/intelligence/status")
def intelligence_status(_actor: Actor = Depends(get_actor)):
    from intelligence.embeddings import model_info
    from intelligence.semantic_index import status as idx_status
    from intelligence.model_router import list_models, ensure_registry
    from intelligence.experience_memory import list_memories
    from intelligence.quality_signals import summary as qsum
    from intelligence.vector_store import stats as vstats

    ensure_registry()
    return {
        "version": "5.2.0",
        "embedding": model_info(),
        "index": idx_status(),
        "vector_store": vstats(),
        "models": list_models(),
        "memories": len(list_memories(limit=1000)),
        "quality": qsum(),
    }


@router.get("/api/v1/intelligence/search")
def intelligence_search(
    q: str,
    project_id: Optional[str] = None,
    top_k: int = 10,
    _actor: Actor = Depends(get_actor),
):
    from intelligence.retrieval import retrieve_context

    return retrieve_context(q, project_id=project_id, top_k=top_k)


@router.post("/api/v1/intelligence/search")
def intelligence_search_post(body: SearchBody, _actor: Actor = Depends(get_actor)):
    from intelligence.retrieval import retrieve_context

    return retrieve_context(body.query, project_id=body.project_id, top_k=body.top_k)


@router.post("/api/v1/intelligence/router")
def intelligence_router(body: RouterBody, _actor: Actor = Depends(get_actor)):
    from intelligence.model_router import route

    return route(
        body.task_type,
        title=body.task or body.task_type or "task",
        description=body.task,
        complexity=body.complexity,
        agent_role=body.agent_role,
        privacy=body.privacy,
        budget_remaining=body.budget_remaining,
    )


@router.get("/api/v1/intelligence/router")
def intelligence_router_get(
    task: str = "coding",
    privacy: str = "ANY_APPROVED",
    _actor: Actor = Depends(get_actor),
):
    from intelligence.model_router import route

    known = {
        "coding", "bugfix", "refactor", "research", "security", "performance",
        "documentation", "testing", "architecture", "deployment", "data_analysis",
    }
    if task in known:
        return route(task, title=task, privacy=privacy)
    return route(None, title=task, description=task, privacy=privacy)
