from __future__ import annotations
from typing import Any, Optional
from pydantic import BaseModel, Field

class TaskCreate(BaseModel):
    title: str
    description: str = ""
    project_id: str = ""
    project: str = ""
    provider: str = ""
    priority: int = 50
    model: str = ""

class CommentIn(BaseModel):
    comment: str = ""
    reason: str = ""

class HandoffCreate(BaseModel):
    task_id: str
    source_agent: str
    target_agent: str
    reason: str = ""
    required: bool = True

class RiskCheckIn(BaseModel):
    action: str
    resource: str = ""
    task_id: str = ""

class BudgetCreate(BaseModel):
    scope_type: str = "global"
    scope_id: Optional[str] = None
    metric: str
    limit_value: float
    period: str = "daily"
    enabled: bool = True

class PolicyCreate(BaseModel):
    scope_type: str = "global"
    scope_id: Optional[str] = None
    category: str
    action: str
    effect: str
    config_json: Optional[dict[str, Any]] = None
    enabled: bool = True

class PolicyPatch(BaseModel):
    effect: Optional[str] = None
    enabled: Optional[bool] = None
    config_json: Optional[dict[str, Any]] = None

class LoginIn(BaseModel):
    token: str

class SettingsPatch(BaseModel):
    values: dict[str, Any] = Field(default_factory=dict)

class ProjectCreate(BaseModel):
    path: str
    name: str = ""

