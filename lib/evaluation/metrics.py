"""Evaluation metrics aggregation."""
from __future__ import annotations

from typing import Any


DIMENSIONS = (
    "correctness",
    "quality",
    "safety",
    "efficiency",
    "cost",
    "latency",
    "robustness",
)


def aggregate_scores(case_results: list[dict[str, Any]]) -> dict[str, Any]:
    """Aggregate per-case scores into overall metrics."""
    if not case_results:
        return {
            "score": 0.0,
            "pass_rate": 0.0,
            "passed": 0,
            "failed": 0,
            "total": 0,
            "dimensions": {d: 0.0 for d in DIMENSIONS},
        }
    passed = sum(1 for r in case_results if r.get("success"))
    total = len(case_results)
    dims: dict[str, list[float]] = {d: [] for d in DIMENSIONS}
    for r in case_results:
        scores = r.get("scores") or {}
        for d in DIMENSIONS:
            if d in scores and scores[d] is not None:
                dims[d].append(float(scores[d]))
        # default correctness from success
        if "correctness" not in scores:
            dims["correctness"].append(1.0 if r.get("success") else 0.0)
    dim_avg = {d: (sum(v) / len(v) if v else 0.0) for d, v in dims.items()}
    # overall score: mean of available dimensions, weighted toward correctness
    weights = {"correctness": 0.4, "quality": 0.15, "safety": 0.15, "efficiency": 0.1,
               "cost": 0.05, "latency": 0.05, "robustness": 0.1}
    score = 0.0
    wsum = 0.0
    for d, w in weights.items():
        if dims[d]:
            score += dim_avg[d] * w
            wsum += w
    if wsum > 0:
        score = score / wsum
    else:
        score = passed / total if total else 0.0
    latencies = []
    for r in case_results:
        m = r.get("metrics") or {}
        if m.get("runtime_ms") is not None:
            latencies.append(float(m["runtime_ms"]))
    return {
        "score": round(score, 4),
        "pass_rate": round(passed / total, 4) if total else 0.0,
        "passed": passed,
        "failed": total - passed,
        "total": total,
        "dimensions": {k: round(v, 4) for k, v in dim_avg.items()},
        "avg_runtime_ms": round(sum(latencies) / len(latencies), 2) if latencies else 0.0,
    }
