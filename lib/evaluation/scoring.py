"""Scoring helpers for individual cases."""
from __future__ import annotations

from typing import Any


def score_case(success: bool, scores: dict[str, Any] | None = None,
               runtime_ms: float = 0.0, cost: float = 0.0) -> dict[str, Any]:
    scores = dict(scores or {})
    if "correctness" not in scores:
        scores["correctness"] = 1.0 if success else 0.0
    if "quality" not in scores:
        scores["quality"] = scores["correctness"]
    if "safety" not in scores:
        scores["safety"] = 1.0
    if "efficiency" not in scores:
        # faster is better; stub: 1.0 if under 5s
        scores["efficiency"] = 1.0 if runtime_ms < 5000 else 0.7
    if "cost" not in scores:
        scores["cost"] = 1.0 if cost <= 0.01 else max(0.0, 1.0 - cost)
    if "latency" not in scores:
        scores["latency"] = 1.0 if runtime_ms < 2000 else 0.8
    if "robustness" not in scores:
        scores["robustness"] = scores["correctness"]
    return scores
