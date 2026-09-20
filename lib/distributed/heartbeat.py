"""Worker heartbeat processing + offline detection."""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any, Optional

_HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(_HERE.parent))

from storage import db as dbmod  # noqa: E402
from distributed import registry  # noqa: E402

HEARTBEAT_INTERVAL = 5
OFFLINE_THRESHOLD = 20


def process_heartbeat(
    worker_id: str,
    *,
    cpu_percent: float = 0.0,
    memory_percent: float = 0.0,
    disk_percent: float = 0.0,
    load1: float = 0.0,
    active_tasks: int = 0,
    version: str = "",
    health: str = "healthy",
    metadata: Optional[dict] = None,
) -> dict[str, Any]:
    now = dbmod.utc_now()
    with dbmod.connect() as conn:
        w = conn.execute("SELECT * FROM workers WHERE id=?", (worker_id,)).fetchone()
        if not w:
            raise KeyError(f"worker not found: {worker_id}")
        if int(w["quarantined"] or 0) == 1 or w["status"] == "quarantined":
            status = "quarantined"
        elif w["status"] == "draining":
            status = "draining"
        elif active_tasks > 0:
            status = "busy"
        elif health == "degraded":
            status = "degraded"
        else:
            status = "online"
        conn.execute(
            """UPDATE workers SET last_heartbeat=?, current_load=?, status=?,
               version=COALESCE(NULLIF(?,''), version) WHERE id=?""",
            (now, active_tasks, status, version, worker_id),
        )
        conn.execute(
            """INSERT INTO worker_metrics
               (worker_id, cpu_percent, memory_percent, disk_percent, load1, active_tasks, metadata_json)
               VALUES (?,?,?,?,?,?,?)""",
            (
                worker_id, cpu_percent, memory_percent, disk_percent, load1,
                active_tasks, json.dumps(metadata or {}),
            ),
        )
        conn.commit()
    # opportunistic stale sweep
    registry.mark_offline_stale(OFFLINE_THRESHOLD)
    w2 = registry.get_worker(worker_id) or {}
    return {
        "ok": True,
        "worker_id": worker_id,
        "status": w2.get("status", status),
        "server_time": now,
        "next_heartbeat_seconds": HEARTBEAT_INTERVAL,
    }
