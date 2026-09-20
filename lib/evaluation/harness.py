"""Evaluation harness — run suites, score, gate, baseline."""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Any, Optional

_HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(_HERE.parent))

from storage import db as dbmod  # noqa: E402
from evaluation import store  # noqa: E402
from evaluation.suites import get_suite, list_suites, sync_suites_to_db  # noqa: E402
from evaluation.cases import run_case  # noqa: E402
from evaluation.metrics import aggregate_scores  # noqa: E402
from evaluation.baselines import set_baseline, get_baseline  # noqa: E402
from evaluation.regressions import detect_regressions  # noqa: E402
from evaluation.quality_gates import check_gate  # noqa: E402


def evaluate(
    subject: Optional[dict[str, Any]] = None,
    benchmark_suite: str = "golden",
    variants: Any = None,
    baseline: Any = None,
    constraints: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    subject = subject or {"type": "platform", "id": "agentbox"}
    return run_suite(
        benchmark_suite,
        subject_type=subject.get("type", "platform"),
        subject_id=subject.get("id", "agentbox"),
        variant=(variants[0] if isinstance(variants, list) and variants else variants) or "",
        set_as_baseline=bool(constraints and constraints.get("set_baseline")),
        threshold=(constraints or {}).get("threshold"),
    )


def run_suite(
    suite_id: str,
    *,
    subject_type: str = "platform",
    subject_id: str = "agentbox",
    variant: str = "",
    set_as_baseline: bool = False,
    threshold: Optional[float] = None,
    context: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    sync_suites_to_db()
    suite = get_suite(suite_id)
    if not suite:
        raise ValueError(f"suite not found: {suite_id}")

    run_id = dbmod.new_id("erun_")
    now = dbmod.utc_now()
    with dbmod.connect() as conn:
        store.ensure_schema(conn)
        store.insert_run(conn, {
            "id": run_id,
            "suite_id": suite["id"],
            "subject_type": subject_type,
            "subject_id": subject_id,
            "variant": variant or "",
            "status": "running",
            "started_at": now,
            "created_at": now,
            "metadata": {"suite_version": suite.get("version")},
        })
        conn.commit()

    case_results = []
    ctx = {"suite_id": suite["id"], "run_id": run_id, **(context or {})}
    for case in suite.get("cases") or []:
        result = run_case(case, context=ctx)
        case_results.append(result)
        with dbmod.connect() as conn:
            store.ensure_schema(conn)
            store.insert_result(conn, {
                "id": dbmod.new_id("eres_"),
                "evaluation_run_id": run_id,
                "case_id": result["case_id"],
                "success": result["success"],
                "scores": result["scores"],
                "metrics": result["metrics"],
                "artifacts": result["artifacts"],
                "error": result.get("error"),
            })
            conn.commit()

    summary = aggregate_scores(case_results)
    regressions = detect_regressions(suite["id"], summary, evaluation_run_id=run_id)
    gate = check_gate(summary, case_results, threshold=threshold, regressions=regressions)

    # If no baseline yet and all passed, auto-set baseline
    existing_bl = get_baseline(suite["id"])
    baseline_set = None
    if set_as_baseline or (existing_bl is None and gate["passed"]):
        baseline_set = set_baseline(
            suite["id"], summary,
            subject_type=subject_type, subject_id=subject_id,
            evaluation_run_id=run_id,
        )

    status = "passed" if gate["passed"] else "failed"
    finished = dbmod.utc_now()
    with dbmod.connect() as conn:
        store.ensure_schema(conn)
        store.update_run(
            conn, run_id,
            status=status,
            score=summary["score"],
            gate_status=gate["status"],
            finished_at=finished,
            metadata={
                "suite_version": suite.get("version"),
                "summary": summary,
                "gate": gate,
                "regressions": {
                    "has_regression": regressions.get("has_regression"),
                    "events": regressions.get("events"),
                },
            },
        )
        conn.commit()

    return {
        "run_id": run_id,
        "suite_id": suite["id"],
        "status": status,
        "gate": gate,
        "summary": summary,
        "results": case_results,
        "regressions": regressions,
        "baseline": baseline_set or existing_bl,
        "score": summary["score"],
    }
