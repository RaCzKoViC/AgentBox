"""Simple failure clustering / mining."""
from __future__ import annotations

import hashlib
import re
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any, Optional

_HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(_HERE.parent))

from storage import db as dbmod  # noqa: E402
from evaluation import store  # noqa: E402


def _fingerprint(error: Optional[str], case_id: str = "") -> str:
    msg = (error or "unknown").strip().lower()
    msg = re.sub(r"\b[0-9a-f]{8,}\b", "<id>", msg)
    msg = re.sub(r"\d+", "N", msg)
    msg = re.sub(r"\s+", " ", msg)[:200]
    raw = f"{case_id}|{msg}"
    return hashlib.sha256(raw.encode()).hexdigest()[:12]


def mine_failures(limit_runs: int = 50) -> dict[str, Any]:
    """Cluster failed evaluation results by error fingerprint."""
    with dbmod.connect() as conn:
        store.ensure_schema(conn)
        rows = conn.execute(
            """SELECT r.*, er.suite_id, er.status AS run_status
               FROM evaluation_results r
               JOIN evaluation_runs er ON er.id = r.evaluation_run_id
               WHERE r.success = 0
               ORDER BY r.created_at DESC
               LIMIT ?""",
            (limit_runs * 10,),
        ).fetchall()

    clusters: dict[str, dict[str, Any]] = {}
    for row in rows:
        d = dict(row)
        fp = _fingerprint(d.get("error"), d.get("case_id") or "")
        if fp not in clusters:
            clusters[fp] = {
                "signature": fp,
                "error_sample": (d.get("error") or "")[:300],
                "case_id": d.get("case_id"),
                "count": 0,
                "suite_ids": set(),
                "run_ids": set(),
            }
        c = clusters[fp]
        c["count"] += 1
        c["suite_ids"].add(d.get("suite_id"))
        c["run_ids"].add(d.get("evaluation_run_id"))

    ranked = sorted(clusters.values(), key=lambda x: -x["count"])
    for c in ranked:
        c["suite_ids"] = sorted(s for s in c["suite_ids"] if s)
        c["run_ids"] = sorted(s for s in c["run_ids"] if s)[:10]
        c["affected_runs"] = len(c["run_ids"])

    return {"clusters": ranked, "total_failures": len(rows), "cluster_count": len(ranked)}


def propose_from_failures(min_count: int = 1) -> list[dict[str, Any]]:
    """Generate improvement proposals from failure clusters (draft / awaiting_approval)."""
    from evaluation.proposals import create_proposal

    mined = mine_failures()
    created = []
    for c in mined["clusters"]:
        if c["count"] < min_count:
            continue
        prop = create_proposal(
            target_type="case",
            target_id=c.get("case_id") or "unknown",
            proposal={
                "title": f"Address failure cluster {c['signature']}",
                "change": "Investigate and harden validator / fix root cause for recurring failure",
                "expected_gain": "lower failure rate on golden/regression suite",
                "benchmark_plan": "re-run golden suite after fix",
            },
            evidence={
                "signature": c["signature"],
                "count": c["count"],
                "error_sample": c["error_sample"],
                "suite_ids": c["suite_ids"],
            },
            risk_level="LOW",
            status="awaiting_approval",
        )
        created.append(prop)
    return created
