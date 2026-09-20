"""A/B testing stub — stable assignment by task_id."""
from __future__ import annotations

import hashlib
from typing import Any, Optional


def assign_variant(task_id: str, variants: list[str], *, ratios: Optional[list[float]] = None) -> str:
    """Deterministic A/B assignment stable per task_id."""
    if not variants:
        raise ValueError("variants required")
    if len(variants) == 1:
        return variants[0]
    ratios = ratios or [1.0 / len(variants)] * len(variants)
    if len(ratios) != len(variants):
        raise ValueError("ratios length must match variants")
    total = sum(ratios) or 1.0
    norms = [r / total for r in ratios]
    h = int(hashlib.sha256(task_id.encode()).hexdigest()[:8], 16)
    x = (h % 10000) / 10000.0
    acc = 0.0
    for v, r in zip(variants, norms):
        acc += r
        if x < acc:
            return v
    return variants[-1]


def describe_experiment(name: str, variants: list[str], ratios: Optional[list[float]] = None) -> dict[str, Any]:
    return {
        "name": name,
        "variants": variants,
        "ratios": ratios or [1.0 / len(variants)] * len(variants),
        "status": "stub",
        "note": "A/B stub — assignment only; no auto promotion",
    }
