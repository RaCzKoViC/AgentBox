"""AgentBox v5.5 — Self-Improvement, Evaluation & Benchmarking."""
from __future__ import annotations

VERSION = "5.5.0"

__all__ = ["VERSION", "evaluate", "list_suites", "run_suite"]


def evaluate(*args, **kwargs):
    from evaluation.harness import evaluate as _evaluate
    return _evaluate(*args, **kwargs)


def list_suites(*args, **kwargs):
    from evaluation.suites import list_suites as _ls
    return _ls(*args, **kwargs)


def run_suite(*args, **kwargs):
    from evaluation.harness import run_suite as _rs
    return _rs(*args, **kwargs)
