"""AgentBox v5.5 — Benchmark helpers (tasks/agents/models/tools/workflows)."""
from __future__ import annotations

VERSION = "5.5.0"

__all__ = ["VERSION", "list_benchmarks"]


def list_benchmarks():
    from benchmarks.registry import list_benchmarks as _lb
    return _lb()
