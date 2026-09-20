#!/usr/bin/env python3
"""Tool selection scoring."""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Any, Optional

_HERE = Path(__file__).resolve().parent

# weights from spec §9
W_CAP = 0.35
W_POLICY = 0.20
W_REL = 0.15
W_LAT = 0.10
W_COST = 0.10
W_LOCAL = 0.05
W_HIST = 0.05


def _ensure_path() -> None:
    lib = str(_HERE.parent)
    if lib not in sys.path:
        sys.path.insert(0, lib)


def score_tool(
    tool: dict[str, Any],
    need: str = "",
    capabilities: Optional[list[str]] = None,
    constraints: Optional[dict] = None,
    db_path: Optional[str] = None,
) -> dict[str, Any]:
    constraints = constraints or {}
    capabilities = capabilities or []
    t_caps = [str(c).lower() for c in (tool.get("capabilities") or [])]
    # capability match 0-100
    if any(c in t_caps for c in capabilities):
        cap_score = 100.0
    elif need and need.lower() in (tool.get("id") or "").lower():
        cap_score = 90.0
    elif need and need.lower() in " ".join(t_caps):
        cap_score = 70.0
    else:
        cap_score = 40.0

    # policy fit: lower risk preferred unless need requires high
    risk = (tool.get("risk_level") or "LOW").upper()
    risk_map = {"LOW": 100, "MODERATE": 80, "ELEVATED": 60, "HIGH": 40, "CRITICAL": 10}
    policy_score = float(risk_map.get(risk, 50))
    if tool.get("health_status") == "quarantined":
        policy_score = 0
    if tool.get("enabled") == 0:
        policy_score = 0

    rel = tool.get("reliability_score")
    if rel is None and isinstance(tool.get("reliability"), dict):
        rel = tool["reliability"].get("reliability_score")
    rel_score = float(rel if rel is not None else 70)

    avg_lat = tool.get("avg_latency_ms") or (tool.get("reliability") or {}).get("avg_latency_ms") or 200
    # lower latency better; map 0-5000ms → 100-0
    lat_score = max(0.0, 100.0 - (float(avg_lat) / 50.0))

    cost = 10.0
    cp = tool.get("cost_profile") or {}
    if isinstance(cp, dict) and cp.get("units"):
        cost = float(cp.get("units") or 10)
    cost_score = max(0.0, 100.0 - cost)

    local_score = 100.0 if (tool.get("execution_mode") or "local") == "local" else 50.0
    if constraints.get("prefer_local") is False:
        local_score = 50.0

    hist = float(tool.get("success_count") or 0)
    fail = float(tool.get("failure_count") or 0)
    hist_score = 50.0
    if hist + fail > 0:
        hist_score = 100.0 * hist / (hist + fail)

    total = (
        W_CAP * cap_score
        + W_POLICY * policy_score
        + W_REL * rel_score
        + W_LAT * lat_score
        + W_COST * cost_score
        + W_LOCAL * local_score
        + W_HIST * hist_score
    )
    out = dict(tool)
    out["score"] = round(total, 2)
    out["score_breakdown"] = {
        "capability": round(cap_score, 1),
        "policy": round(policy_score, 1),
        "reliability": round(rel_score, 1),
        "latency": round(lat_score, 1),
        "cost": round(cost_score, 1),
        "locality": round(local_score, 1),
        "history": round(hist_score, 1),
    }
    out["matched_need"] = need
    return out
