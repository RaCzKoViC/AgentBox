#!/usr/bin/env python3
"""Capability model + find_tools(need, constraints) API."""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Any, Optional

_HERE = Path(__file__).resolve().parent


def _ensure_path() -> None:
    lib = str(_HERE.parent)
    if lib not in sys.path:
        sys.path.insert(0, lib)


def normalize_need(need: str) -> list[str]:
    """Expand a need string into candidate capability tokens."""
    n = (need or "").strip().lower().replace("-", "_").replace("/", ".").replace(" ", "_")
    aliases = {
        "git": ["git_status", "git_diff", "git.status", "git.diff"],
        "git_status": ["git_status", "git.status"],
        "git_diff": ["git_diff", "git.diff"],
        "read_file": ["read_file", "filesystem.read"],
        "write_file": ["write_file", "filesystem.write"],
        "shell": ["shell_exec", "shell.run"],
        "http": ["http_get", "http.get"],
        "docker": ["docker_ps", "docker.ps"],
        "remote_file_upload": ["sftp_upload", "scp_upload", "rsync_upload"],
    }
    if n in aliases:
        return aliases[n]
    # also accept dotted form
    parts = [n]
    if "." in n:
        parts.append(n.replace(".", "_"))
    if "_" in n:
        parts.append(n.replace("_", "."))
    return list(dict.fromkeys(parts))


def find_tools(
    need: str,
    constraints: Optional[dict] = None,
    task_id: Optional[str] = None,
    agent_name: Optional[str] = None,
    worker_id: Optional[str] = None,
    db_path: Optional[str] = None,
) -> list[dict[str, Any]]:
    """Find tools matching a capability need. Scores by match/policy/reliability/cost."""
    _ensure_path()
    from tools import registry
    from tools.matcher import score_tool

    constraints = dict(constraints or {})
    if task_id:
        constraints.setdefault("task_id", task_id)
    if agent_name:
        constraints.setdefault("agent_name", agent_name)
    if worker_id:
        constraints.setdefault("worker_id", worker_id)

    registry.ensure_builtins(db_path=db_path)
    caps = normalize_need(need)
    tools = registry.list_tools(enabled_only=True, db_path=db_path)
    matched: list[dict[str, Any]] = []
    for t in tools:
        t_caps = [str(c).lower() for c in (t.get("capabilities") or [])]
        hit = any(c in t_caps or c == t["id"].lower() or c in (t.get("name") or "").lower() for c in caps)
        # also soft text match on need against id/name/category
        if not hit:
            blob = f"{t.get('id')} {t.get('name')} {t.get('category')} {' '.join(t_caps)}".lower()
            hit = any(c.replace(".", " ") in blob or c.replace("_", " ") in blob or c in blob for c in caps)
            if not hit and need:
                hit = need.lower() in blob
        if not hit:
            continue
        if constraints.get("max_risk"):
            order = ["LOW", "MODERATE", "ELEVATED", "HIGH", "CRITICAL"]
            try:
                if order.index((t.get("risk_level") or "LOW").upper()) > order.index(str(constraints["max_risk"]).upper()):
                    continue
            except ValueError:
                pass
        if constraints.get("category") and t.get("category") != constraints["category"]:
            continue
        scored = score_tool(t, need=need, capabilities=caps, constraints=constraints, db_path=db_path)
        matched.append(scored)
    matched.sort(key=lambda x: x.get("score", 0), reverse=True)
    return matched
