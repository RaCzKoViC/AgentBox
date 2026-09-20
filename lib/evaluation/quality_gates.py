"""Quality gates — fail run if score below threshold or critical cases fail."""
from __future__ import annotations

import os
from typing import Any, Optional


def default_threshold() -> float:
    env = os.environ.get("AGENTBOX_EVAL_THRESHOLD")
    if env:
        try:
            return float(env)
        except ValueError:
            pass
    return 0.80


def check_gate(
    summary: dict[str, Any],
    case_results: list[dict[str, Any]],
    *,
    threshold: Optional[float] = None,
    regressions: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    thr = default_threshold() if threshold is None else float(threshold)
    score = float(summary.get("score") or 0)
    reasons: list[str] = []
    critical_fails = [
        r for r in case_results
        if r.get("critical", True) and not r.get("success")
    ]
    if critical_fails:
        reasons.append(
            f"critical_cases_failed:{','.join(r.get('case_id','?') for r in critical_fails)}"
        )
    if score < thr:
        reasons.append(f"score_below_threshold:{score:.4f}<{thr:.4f}")
    if regressions and regressions.get("has_regression"):
        kinds = [e.get("kind") for e in regressions.get("events") or []]
        reasons.append(f"regression_detected:{','.join(kinds)}")

    passed = len(reasons) == 0
    return {
        "passed": passed,
        "status": "PASS" if passed else "FAIL",
        "threshold": thr,
        "score": score,
        "reasons": reasons,
    }
