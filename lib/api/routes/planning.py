"""Planning REST API (v5.3) — goals, plans, workflows, reflections."""
from __future__ import annotations

from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from ..deps import Actor, get_actor, require_role

router = APIRouter(tags=["planning"])


class GoalCreate(BaseModel):
    title: str
    description: str = ""
    project_id: str = ""
    template: Optional[str] = None
    priority: int = 100


class PlanCreate(BaseModel):
    template: Optional[str] = None


class PlanRevise(BaseModel):
    reason: str = "api revision"
    insert_retry: bool = True


class WorkflowRunBody(BaseModel):
    title: str = ""
    description: str = ""
    project_id: str = ""


class ReflectBody(BaseModel):
    goal_id: str
    task_id: str = ""
    plan_id: str = ""
    status: str = "failed"
    error: str = ""


@router.get("/api/v1/goals")
def list_goals(status: Optional[str] = None, _actor: Actor = Depends(get_actor)):
    from planning import store
    return {"goals": store.list_goals(status=status)}


@router.post("/api/v1/goals")
def create_goal(body: GoalCreate, _actor: Actor = Depends(require_role("operator"))):
    from planning.planner import create_goal, plan_from_template
    if body.template:
        return plan_from_template(body.title, body.description, template=body.template, project_id=body.project_id)
    return create_goal(body.title, body.description, project_id=body.project_id, priority=body.priority)


@router.get("/api/v1/goals/{goal_id}")
def get_goal(goal_id: str, _actor: Actor = Depends(get_actor)):
    from planning import store
    from planning.goal_tracker import goal_progress
    g = store.get_goal(goal_id)
    if not g:
        raise HTTPException(404, "goal not found")
    try:
        g["progress"] = goal_progress(goal_id)
    except Exception as exc:
        g["progress_error"] = str(exc)
    g["plans"] = store.list_plans(goal_id=goal_id)
    return g


@router.post("/api/v1/goals/{goal_id}/plan")
def plan_goal(goal_id: str, body: Optional[PlanCreate] = None, _actor: Actor = Depends(require_role("operator"))):
    from planning.planner import generate_plan
    tpl = body.template if body else None
    try:
        return generate_plan(goal_id, template=tpl)
    except KeyError as exc:
        raise HTTPException(404, str(exc))
    except ValueError as exc:
        raise HTTPException(400, str(exc))


@router.get("/api/v1/plans")
def list_plans(goal_id: Optional[str] = None, _actor: Actor = Depends(get_actor)):
    from planning import store
    return {"plans": store.list_plans(goal_id=goal_id)}


@router.get("/api/v1/plans/{plan_id}")
def get_plan(plan_id: str, _actor: Actor = Depends(get_actor)):
    from planning import store
    p = store.get_plan(plan_id)
    if not p:
        raise HTTPException(404, "plan not found")
    return p


@router.post("/api/v1/plans/{plan_id}/revise")
def revise(plan_id: str, body: PlanRevise, _actor: Actor = Depends(require_role("operator"))):
    from planning.plan_revision import revise_plan
    try:
        return revise_plan(plan_id, reason=body.reason, insert_retry=body.insert_retry)
    except KeyError as exc:
        raise HTTPException(404, str(exc))
    except ValueError as exc:
        raise HTTPException(400, str(exc))


@router.get("/api/v1/workflows")
def workflows(_actor: Actor = Depends(get_actor)):
    from planning.workflow_templates import list_templates
    return {"workflows": list_templates()}


@router.post("/api/v1/workflows/{name}/run")
def run_workflow(name: str, body: WorkflowRunBody, _actor: Actor = Depends(require_role("operator"))):
    from planning.planner import plan_from_template
    title = body.title or f"Workflow {name}"
    return plan_from_template(title, body.description, template=name, project_id=body.project_id)


@router.get("/api/v1/reflections")
def reflections(goal_id: Optional[str] = None, _actor: Actor = Depends(get_actor)):
    from planning import store
    return {"reflections": store.list_reflections(goal_id=goal_id)}


@router.post("/api/v1/reflections")
def create_reflection(body: ReflectBody, _actor: Actor = Depends(require_role("operator"))):
    from planning.reflection import reflect
    return reflect(
        goal_id=body.goal_id,
        task_id=body.task_id,
        plan_id=body.plan_id,
        run_result={"status": body.status, "error": body.error, "attempt": 1},
    )
