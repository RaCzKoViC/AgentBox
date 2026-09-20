#!/usr/bin/env python3
"""Workflow template loader/compiler — YAML under /workspace/agentbox-v5/workflows."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Optional

try:
    import yaml
except ImportError:  # pragma: no cover
    yaml = None  # type: ignore

WORKFLOWS_DIR = Path("/workspace/agentbox-v5/workflows")
# also check installed share path
_ALT = Path.home() / ".local/share/agentbox/v5/workflows"
_LIB_ALT = Path(__file__).resolve().parents[2] / "workflows"

ALIASES = {
    "feature": "software_feature",
    "software-feature": "software_feature",
    "bug": "bugfix",
    "bug_fix": "bugfix",
    "fix": "bugfix",
    "refactor": "refactor",
    "security": "security_review",
    "security_review": "security_review",
    "release": "release",
    "research": "research",
    "migration": "migration",
    "incident": "incident",
    "coding": "software_feature",
    "architecture": "software_feature",
}


def _dirs() -> list[Path]:
    out = []
    for d in (WORKFLOWS_DIR, _LIB_ALT, _ALT):
        if d.is_dir() and d not in out:
            out.append(d)
    return out


def resolve_template_name(name: Optional[str]) -> str:
    if not name:
        return "software_feature"
    key = str(name).strip().lower().replace(" ", "_").replace("-", "_")
    return ALIASES.get(key, key)


def list_templates() -> list[dict[str, Any]]:
    found: dict[str, Path] = {}
    for d in _dirs():
        for p in sorted(d.glob("*.yaml")) + sorted(d.glob("*.yml")):
            found.setdefault(p.stem, p)
    out = []
    for name, path in sorted(found.items()):
        try:
            data = load_template(name)
            stages = []
            for s in (data.get("stages") or []):
                if isinstance(s, str):
                    stages.append(s)
                elif isinstance(s, dict):
                    stages.append(s.get("agent") or s.get("name") or "")
            out.append({
                "name": name,
                "path": str(path),
                "stages": stages,
                "description": data.get("description") or "",
            })
        except Exception as exc:
            out.append({"name": name, "path": str(path), "error": str(exc)})
    return out


def _load_yaml(path: Path) -> dict:
    text = path.read_text(encoding="utf-8")
    if yaml is not None:
        data = yaml.safe_load(text) or {}
    else:
        # minimal fallback: only support our simple templates via json if .json
        raise RuntimeError("PyYAML required to load workflow templates")
    if not isinstance(data, dict):
        raise ValueError(f"template root must be mapping: {path}")
    return data


def load_template(name: str) -> dict[str, Any]:
    name = resolve_template_name(name)
    for d in _dirs():
        for ext in (".yaml", ".yml"):
            path = d / f"{name}{ext}"
            if path.is_file():
                data = _load_yaml(path)
                data.setdefault("name", name)
                data["_path"] = str(path)
                return data
    raise FileNotFoundError(f"workflow template not found: {name}")


def compile_template(
    name: str,
    goal: Optional[dict] = None,
    analysis: Optional[dict] = None,
) -> dict[str, Any]:
    tpl = load_template(name)
    analysis = analysis or {}
    goal = goal or {}
    stages = tpl.get("stages") or []
    nodes: list[dict] = []
    for i, stage in enumerate(stages):
        if isinstance(stage, str):
            agent = stage
            title = stage.replace("_", " ").title()
            desc = f"Execute {agent} stage for goal"
            meta: dict[str, Any] = {}
        else:
            agent = stage.get("agent") or stage.get("name") or f"stage_{i}"
            title = stage.get("title") or agent.replace("_", " ").title()
            desc = stage.get("description") or f"Execute {agent} for: {goal.get('title') or ''}"
            meta = dict(stage.get("meta") or {})
            if stage.get("approval_gate"):
                meta["approval_gate"] = stage["approval_gate"]
        node_id = f"stage_{agent}_{i}"
        deps = [f"stage_{(stages[i-1] if isinstance(stages[i-1], str) else (stages[i-1].get('agent') or stages[i-1].get('name'))) }_{i-1}"] if i > 0 else []
        # fix deps construction
        if i > 0:
            prev = stages[i - 1]
            prev_agent = prev if isinstance(prev, str) else (prev.get("agent") or prev.get("name"))
            deps = [f"stage_{prev_agent}_{i-1}"]
        else:
            deps = []
        nodes.append({
            "id": node_id,
            "title": title,
            "description": desc.strip(),
            "agent": agent,
            "type": "stage",
            "dependencies": deps,
            "order_index": i,
            "estimated_runtime": float((stage.get("estimated_runtime") if isinstance(stage, dict) else None) or 120),
            "estimated_cost": float((stage.get("estimated_cost") if isinstance(stage, dict) else None) or 0.05),
            "risk": analysis.get("risk") or "MEDIUM",
            "critical": True,
            "parallel_safe": bool(isinstance(stage, dict) and stage.get("parallel_safe")),
            "meta": meta,
            "status": "pending",
        })
    approvals = list(tpl.get("approvals") or analysis.get("approval_points") or ["plan"])
    retry = tpl.get("retry") or {"max_attempts": 2}
    return {
        "template": tpl.get("name") or name,
        "nodes": nodes,
        "approvals": approvals,
        "retry": retry,
        "description": tpl.get("description") or "",
    }
