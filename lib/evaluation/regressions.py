"""Regression detection vs baselines."""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any, Optional

_HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(_HERE.parent))

from storage import db as dbmod  # noqa: E402
from evaluation import store  # noqa: E402
from evaluation.baselines import get_baseline  # noqa: E402

# Default thresholds (percent)
DEFAULT_THRESHOLDS = {
    "correctness_regression_percent": 5.0,
    "score_regression_percent": 5.0,
    "cost_regression_percent": 15.0,
    "latency_regression_percent": 20.0,
    "failure_rate_regression_percent": 5.0,
}


def detect_regressions(
    suite_id: str,
    summary: dict[str, Any],
    *,
    evaluation_run_id: Optional[str] = None,
    thresholds: Optional[dict[str, float]] = None,
) -> dict[str, Any]:
    thr = {**DEFAULT_THRESHOLDS, **(thresholds or {})}
    baseline = get_baseline(suite_id)
    events: list[dict[str, Any]] = []
    if not baseline:
        return {"has_regression": False, "events": [], "baseline": None, "compared": False}

    bs = baseline.get("summary") or {}
    base_score = float(bs.get("score") or 0)
    cur_score = float(summary.get("score") or 0)
    if base_score > 0:
        drop_pct = ((base_score - cur_score) / base_score) * 100.0
        if drop_pct >= thr["score_regression_percent"]:
            events.append({
                "kind": "score_drop",
                "baseline": base_score,
                "current": cur_score,
                "drop_percent": round(drop_pct, 2),
            })

    base_pass = float(bs.get("pass_rate") or 0)
    cur_pass = float(summary.get("pass_rate") or 0)
    if base_pass > 0:
        drop_pct = ((base_pass - cur_pass) / base_pass) * 100.0
        if drop_pct >= thr["correctness_regression_percent"]:
            events.append({
                "kind": "correctness_drop",
                "baseline": base_pass,
                "current": cur_pass,
                "drop_percent": round(drop_pct, 2),
            })

    base_fail_rate = 1.0 - base_pass
    cur_fail_rate = 1.0 - cur_pass
    if cur_fail_rate - base_fail_rate >= thr["failure_rate_regression_percent"] / 100.0:
        events.append({
            "kind": "failure_rate_increase",
            "baseline": base_fail_rate,
            "current": cur_fail_rate,
        })

    base_lat = float(bs.get("avg_runtime_ms") or 0)
    cur_lat = float(summary.get("avg_runtime_ms") or 0)
    if base_lat > 0 and cur_lat > 0:
        inc_pct = ((cur_lat - base_lat) / base_lat) * 100.0
        if inc_pct >= thr["latency_regression_percent"]:
            events.append({
                "kind": "latency_increase",
                "baseline": base_lat,
                "current": cur_lat,
                "increase_percent": round(inc_pct, 2),
            })

    # persist
    with dbmod.connect() as conn:
        store.ensure_schema(conn)
        for ev in events:
            eid = dbmod.new_id("reg_")
            conn.execute(
                """INSERT INTO regression_events
                   (id, evaluation_run_id, suite_id, kind, detail_json, created_at)
                   VALUES (?,?,?,?,?,?)""",
                (eid, evaluation_run_id, suite_id, ev["kind"],
                 json.dumps(ev, default=str), dbmod.utc_now()),
            )
            ev["id"] = eid
        conn.commit()

    return {
        "has_regression": bool(events),
        "events": events,
        "baseline": baseline,
        "compared": True,
    }


def list_regressions(limit: int = 50) -> list[dict[str, Any]]:
    with dbmod.connect() as conn:
        store.ensure_schema(conn)
        rows = conn.execute(
            "SELECT * FROM regression_events ORDER BY created_at DESC LIMIT ?", (limit,)
        ).fetchall()
        out = []
        for r in rows:
            d = dict(r)
            d["detail"] = json.loads(d.pop("detail_json") or "{}")
            out.append(d)
        return out
