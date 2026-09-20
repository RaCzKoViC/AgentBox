"""Tool benchmark helpers."""
from __future__ import annotations
from typing import Any


def benchmark_tool(tool_id: str, **kwargs: Any) -> dict[str, Any]:
    return {"tool_id": tool_id, "status": "stub", "score": 1.0, **kwargs}
