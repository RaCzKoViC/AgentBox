"""Benchmark runners — thin wrapper over evaluation harness."""
from __future__ import annotations
import sys
from pathlib import Path
from typing import Any, Optional

_HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(_HERE.parent))

from evaluation.harness import run_suite  # noqa: E402


def run_benchmark(suite_id: str, **kwargs: Any) -> dict[str, Any]:
    return run_suite(suite_id, **kwargs)
