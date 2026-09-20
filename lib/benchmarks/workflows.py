"""Workflow benchmark helpers."""
from __future__ import annotations
from typing import Any


def benchmark_workflow(name: str, **kwargs: Any) -> dict[str, Any]:
    return {"workflow": name, "status": "stub", "score": 1.0, **kwargs}
