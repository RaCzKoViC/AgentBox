"""Failover stubs — wired for dry-run + basic reassignment."""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any, Optional

_HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(_HERE.parent))

from storage import db as dbmod  # noqa: E402
from distributed import registry  # noqa: E402
from distributed import routing  # noqa: E402

MAX_FAILOVERS = 2


def dry_run(failed_worker_id: str, task_id: str = "") -> dict[str, Any]:
    """Plan failover without mutating assignments (selftest-safe)."""
    failed = registry.get_worker(failed_worker_id)
    decision = routing.select_worker(
        task_id=task_id,
        requirements={"preferred_provider": "stub"},
    )
    replacement = None
    if decision.worker_id and decision.worker_id != failed_worker_id:
        replacement = decision.worker_id
    else:
        for c in decision.candidates:
            if c["worker_id"] != failed_worker_id:
                replacement = c["worker_id"]
                break
    plan = {
        "ok": True,
        "dry_run": True,
        "failed_worker": failed_worker_id,
        "failed_worker_status": (failed or {}).get("status"),
        "task_id": task_id or None,
        "replacement_worker": replacement,
        "score": decision.score if replacement else 0,
        "reasons": decision.reasons,
        "action": "reassign" if replacement else "restart_on_control_plane",
        "max_failovers": MAX_FAILOVERS,
    }
    with dbmod.connect() as conn:
        conn.execute(
            "INSERT INTO worker_events (worker_id, event_type, payload_json) VALUES (?,?,?)",
            (failed_worker_id, "failover.started", json.dumps({**plan, "phase": "dry_run"})),
        )
        conn.commit()
    return plan


def execute(failed_worker_id: str, assignment_id: str) -> dict[str, Any]:
    """Mark assignment expired and pick another worker if available."""
    asgn = routing.get_assignment(assignment_id)
    if not asgn:
        raise KeyError(assignment_id)
    task_id = asgn["task_id"]
    with dbmod.connect() as conn:
        conn.execute(
            "UPDATE worker_assignments SET status='expired', finished_at=? WHERE id=?",
            (dbmod.utc_now(), assignment_id),
        )
        conn.execute(
            "UPDATE workers SET current_load = CASE WHEN current_load > 0 THEN current_load - 1 ELSE 0 END, status='offline' WHERE id=?",
            (failed_worker_id,),
        )
        conn.execute(
            "INSERT INTO worker_events (worker_id, event_type, payload_json) VALUES (?,?,?)",
            (failed_worker_id, "failover.started", json.dumps({"assignment_id": assignment_id})),
        )
        conn.commit()
    decision = routing.select_worker(task_id=task_id)
    if not decision.worker_id or decision.worker_id == failed_worker_id:
        return {
            "ok": False,
            "error": "no replacement worker",
            "failed_worker": failed_worker_id,
            "assignment_id": assignment_id,
        }
    new_asgn = routing.create_assignment(decision.worker_id, task_id, payload={"failover_from": assignment_id})
    with dbmod.connect() as conn:
        conn.execute(
            "INSERT INTO worker_events (worker_id, event_type, payload_json) VALUES (?,?,?)",
            (decision.worker_id, "failover.completed",
             json.dumps({"from": failed_worker_id, "new_assignment": new_asgn.get("id")})),
        )
        conn.commit()
    return {
        "ok": True,
        "failed_worker": failed_worker_id,
        "replacement_worker": decision.worker_id,
        "new_assignment": new_asgn,
    }
