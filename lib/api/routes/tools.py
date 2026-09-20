"""Tools REST API (v5.4) — list/search/run/health."""
from __future__ import annotations

from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from ..deps import Actor, get_actor, require_role

router = APIRouter(tags=["tools"])


class ToolRunBody(BaseModel):
    input: dict[str, Any] = Field(default_factory=dict)
    task_id: Optional[str] = None
    agent_name: Optional[str] = None


class DiscoverBody(BaseModel):
    register: bool = True


class FindBody(BaseModel):
    need: str
    max_risk: Optional[str] = None
    category: Optional[str] = None


@router.get("/api/v1/tools")
def list_tools(category: Optional[str] = None, q: Optional[str] = None, _actor: Actor = Depends(get_actor)):
    from tools import registry
    registry.ensure_builtins()
    tools = registry.list_tools(category=category, query=q)
    return {"tools": tools, "count": len(tools)}


@router.get("/api/v1/tools/search")
def search_tools(q: str, _actor: Actor = Depends(get_actor)):
    from tools.capability import find_tools
    from tools import registry
    registry.ensure_builtins()
    matches = find_tools(q)
    if not matches:
        matches = registry.search_tools(q)
    return {"query": q, "matches": matches, "count": len(matches)}


@router.post("/api/v1/tools/find")
def find_tools_api(body: FindBody, _actor: Actor = Depends(get_actor)):
    from tools.capability import find_tools
    constraints = {}
    if body.max_risk:
        constraints["max_risk"] = body.max_risk
    if body.category:
        constraints["category"] = body.category
    matches = find_tools(body.need, constraints=constraints)
    return {"need": body.need, "matches": matches}


@router.get("/api/v1/tools/health")
def tools_health(_actor: Actor = Depends(get_actor)):
    from tools.discovery import health_all
    return {"health": health_all()}


@router.post("/api/v1/tools/discover")
def tools_discover(body: Optional[DiscoverBody] = None, _actor: Actor = Depends(require_role("operator"))):
    from tools.discovery import discover
    reg = True if body is None else body.register
    return discover(register=reg)


@router.get("/api/v1/tools/{tool_id}")
def get_tool(tool_id: str, _actor: Actor = Depends(get_actor)):
    from tools import registry
    t = registry.get_tool(tool_id)
    if not t:
        raise HTTPException(404, "tool not found")
    return t


@router.post("/api/v1/tools/{tool_id}/run")
def run_tool(tool_id: str, body: ToolRunBody, _actor: Actor = Depends(require_role("operator"))):
    from tools.executor import execute_tool
    result = execute_tool(
        tool_id,
        body.input,
        task_context={"task_id": body.task_id} if body.task_id else {},
        agent_context={"agent_name": body.agent_name or _actor.actor},
    )
    return result


@router.post("/api/v1/tools/{tool_id}/test")
def test_tool(tool_id: str, _actor: Actor = Depends(require_role("operator"))):
    from tools.discovery import health_check_tool
    return health_check_tool(tool_id)


@router.get("/api/v1/tool-runs")
def list_tool_runs(tool_id: Optional[str] = None, limit: int = 50, _actor: Actor = Depends(get_actor)):
    from storage import db as dbmod
    from tools.registry import ensure_schema
    ensure_schema()
    with dbmod.connect() as conn:
        if tool_id:
            rows = conn.execute(
                "SELECT * FROM tool_calls WHERE tool_id=? ORDER BY created_at DESC LIMIT ?",
                (tool_id, limit),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM tool_calls ORDER BY created_at DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return {"runs": [dict(r) for r in rows]}


@router.get("/api/v1/mcp")
def list_mcp(_actor: Actor = Depends(get_actor)):
    from tools import mcp_client
    return {"servers": mcp_client.list_servers(), "sdk_available": mcp_client.mcp_available()}


@router.get("/api/v1/capabilities")
def list_capabilities(_actor: Actor = Depends(get_actor)):
    from tools import registry
    registry.ensure_builtins()
    caps = set()
    for t in registry.list_tools():
        for c in t.get("capabilities") or []:
            caps.add(c)
    return {"capabilities": sorted(caps)}
