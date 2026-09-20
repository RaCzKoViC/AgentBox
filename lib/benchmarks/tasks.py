"""Task-level benchmark stubs."""
from __future__ import annotations
from typing import Any


def benchmark_task(task_type: str, **kwargs: Any) -> dict[str, Any]:
    return {"task_type": task_type, "status": "stub", "score": 1.0, **kwargs}
