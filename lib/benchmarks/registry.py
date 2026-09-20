"""Benchmark registry facade over evaluation suites."""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

_HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(_HERE.parent))

from evaluation.suites import list_suites, get_suite  # noqa: E402


def list_benchmarks() -> list[dict[str, Any]]:
    suites = list_suites(sync=True)
    return [
        {
            "id": s["id"],
            "name": s.get("name") or s["id"],
            "version": s.get("version"),
            "case_count": s.get("case_count") or len(s.get("cases") or []),
            "description": s.get("description") or "",
            "path": s.get("path") or "",
        }
        for s in suites
    ]


def get_benchmark(suite_id: str) -> Any:
    return get_suite(suite_id)
