"""Task → worker routing by capabilities / load / labels."""
from __future__ import annotations

import json
import sys
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any, Optional

_HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(_HERE.parent))

from distributed import registry  # noqa: E402
from distributed.capabilities import matches, parse_caps  # noqa: E402
from storage import db as dbmod  # noqa: E402


@dataclass
class WorkerDecision:
    worker_id: Optional[str]
    score: float = 0.0
    reasons: list[str] = field(default_factory=list)
    candidates: list[dict] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def score_worker(w: dict[str, Any], requirements: Optional[dict] = None) -> tuple[float, list[str]]:
    if w.get("quarantined") or w.get("status") == "quarantined":
        return -1.0, ["quarantined"]
    if w.get("status") in ("offline", "draining", "maintenance", "new", "enrolling"):
        return -1.0, [f"status={w.get('status')}"]
    caps = w.get("capabilities") or parse_caps(w.get("capabilities_json"))
    ok, reasons = matches(caps, requirements)
    if not ok:
        return -1.0, reasons
    score = 40.0  # capability match base
    # load (20%)
    max_p = max(int(w.get("max_parallel_tasks") or 1), 1)
    load = int(w.get("current_load") or 0)
    load_score = max(0.0, 20.0 * (1.0 - load / max_p))
    score += load_score
    reasons.append(f"load {load}/{max_p}")
    # health (10%)
    if w.get("status") == "online":
        score += 10.0
        reasons.append("healthy")
    elif w.get("status") == "busy":
        score += 5.0
    elif w.get("status") == "degraded":
        score += 2.0
    # labels (project affinity stub — 10%)
    req_labels = (requirements or {}).get("required_labels") or []
    wlabels = set(w.get("labels") or [])
    if req_labels:
        hit = sum(1 for lb in req_labels if lb in wlabels)
        if hit < len(req_labels):
            return -1.0, ["missing required labels"]
        score += 10.0 * (hit / len(req_labels))
        reasons.append("labels match")
    else:
        score += 5.0
    # provider locality (15%)
    pref = (requirements or {}).get("preferred_provider")
    providers = caps.get("providers") or []
    if pref and pref in providers:
        score += 15.0
        reasons.append(f"provider {pref}")
    else:
        score += 5.0
    # network latency stub (5%)
    score += 5.0
    return score, reasons


def select_worker(
    task_id: str = "",
    requirements: Optional[dict] = None,
    policy_context: Optional[dict] = None,
) -> WorkerDecision:
    """Select best online worker. Policy/budget/risk still gate at assignment time."""
    _ = policy_context  # reserved
    workers = registry.list_workers()
    scored: list[tuple[float, dict, list[str]]] = []
    for w in workers:
        sc, reasons = score_worker(w, requirements)
        if sc >= 0:
            scored.append((sc, w, reasons))
    scored.sort(key=lambda x: (-x[0], x[1].get("current_load", 0)))
    candidates = [
        {"worker_id": w["id"], "name": w.get("name"), "score": sc, "reasons": rs}
        for sc, w, rs in scored[:5]
    ]
    if not scored:
        return WorkerDecision(None, 0.0, ["no eligible workers"], candidates)
    best_sc, best_w, best_rs = scored[0]
    return WorkerDecision(best_w["id"], best_sc, best_rs, candidates)


def create_assignment(
    worker_id: str,
    task_id: str,
    run_id: str = "",
    lease_seconds: int = 60,
    payload: Optional[dict] = None,
) -> dict[str, Any]:
    aid = dbmod.new_id("asgn_")
    with dbmod.connect() as conn:
        # gate: quarantined workers get nothing
        w = conn.execute("SELECT * FROM workers WHERE id=?", (worker_id,)).fetchone()
        if not w:
            raise KeyError(worker_id)
        if int(w["quarantined"] or 0) or w["status"] == "quarantined":
            raise PermissionError("worker quarantined")
        if w["status"] in ("offline", "draining", "maintenance"):
            raise PermissionError(f"worker status={w['status']}")
        conn.execute(
            """INSERT INTO worker_assignments
               (id, worker_id, task_id, run_id, status, assigned_at, lease_seconds, payload_json)
               VALUES (?,?,?,?, 'assigned', ?, ?, ?)""",
            (aid, worker_id, task_id, run_id or None, dbmod.utc_now(), lease_seconds,
             json.dumps(payload or {})),
        )
        conn.execute(
            "UPDATE workers SET current_load = current_load + 1 WHERE id=?", (worker_id,)
        )
        conn.execute(
            "INSERT INTO worker_events (worker_id, event_type, payload_json) VALUES (?,?,?)",
            (worker_id, "assignment.created", json.dumps({"assignment_id": aid, "task_id": task_id})),
        )
        conn.commit()
    return get_assignment(aid) or {"id": aid}


def get_assignment(assignment_id: str) -> Optional[dict[str, Any]]:
    with dbmod.connect() as conn:
        r = conn.execute(
            "SELECT * FROM worker_assignments WHERE id=?", (assignment_id,)
        ).fetchone()
        if not r:
            return None
        d = dict(r)
        try:
            d["payload"] = json.loads(d.get("payload_json") or "{}")
        except Exception:
            d["payload"] = {}
        return d


def list_assignments(worker_id: Optional[str] = None, status: Optional[str] = None) -> list[dict]:
    with dbmod.connect() as conn:
        q = "SELECT * FROM worker_assignments WHERE 1=1"
        args: list[Any] = []
        if worker_id:
            q += " AND worker_id=?"
            args.append(worker_id)
        if status:
            q += " AND status=?"
            args.append(status)
        q += " ORDER BY assigned_at DESC LIMIT 100"
        return [dict(r) for r in conn.execute(q, args).fetchall()]


def poll_assignment(worker_id: str) -> Optional[dict[str, Any]]:
    with dbmod.connect() as conn:
        r = conn.execute(
            """SELECT * FROM worker_assignments
               WHERE worker_id=? AND status='assigned'
               ORDER BY assigned_at ASC LIMIT 1""",
            (worker_id,),
        ).fetchone()
        if not r:
            return None
        d = dict(r)
        try:
            d["payload"] = json.loads(d.get("payload_json") or "{}")
        except Exception:
            d["payload"] = {}
        return d


def accept_assignment(worker_id: str, assignment_id: str) -> dict[str, Any]:
    with dbmod.connect() as conn:
        r = conn.execute(
            "SELECT * FROM worker_assignments WHERE id=? AND worker_id=?",
            (assignment_id, worker_id),
        ).fetchone()
        if not r:
            raise KeyError("assignment not found")
        if r["status"] not in ("assigned",):
            raise RuntimeError(f"cannot accept status={r['status']}")
        conn.execute(
            "UPDATE worker_assignments SET status='accepted', started_at=? WHERE id=?",
            (dbmod.utc_now(), assignment_id),
        )
        conn.execute(
            "UPDATE workers SET status='busy' WHERE id=?", (worker_id,)
        )
        conn.execute(
            "INSERT INTO worker_events (worker_id, event_type, payload_json) VALUES (?,?,?)",
            (worker_id, "assignment.accepted", json.dumps({"assignment_id": assignment_id})),
        )
        conn.commit()
    return get_assignment(assignment_id) or {}


def complete_assignment(
    worker_id: str,
    assignment_id: str,
    *,
    ok: bool = True,
    result: Optional[dict] = None,
    error: str = "",
) -> dict[str, Any]:
    status = "completed" if ok else "failed"
    with dbmod.connect() as conn:
        r = conn.execute(
            "SELECT * FROM worker_assignments WHERE id=? AND worker_id=?",
            (assignment_id, worker_id),
        ).fetchone()
        if not r:
            raise KeyError("assignment not found")
        conn.execute(
            """UPDATE worker_assignments SET status=?, finished_at=?,
               result_json=?, error=? WHERE id=?""",
            (status, dbmod.utc_now(), json.dumps(result or {}), error, assignment_id),
        )
        conn.execute(
            "UPDATE workers SET current_load = CASE WHEN current_load > 0 THEN current_load - 1 ELSE 0 END, status='online' WHERE id=?",
            (worker_id,),
        )
        conn.execute(
            "INSERT INTO worker_events (worker_id, event_type, payload_json) VALUES (?,?,?)",
            (worker_id, f"assignment.{status}", json.dumps({"assignment_id": assignment_id})),
        )
        conn.commit()
    return get_assignment(assignment_id) or {}
