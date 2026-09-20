"""Worker registry — CRUD + status transitions."""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any, Optional

_HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(_HERE.parent))

from storage import db as dbmod  # noqa: E402

VALID_STATUSES = frozenset({
    "new", "enrolling", "online", "busy", "degraded", "draining",
    "offline", "quarantined", "maintenance",
})
OFFLINE_THRESHOLD_SECS = 20


def _row(r) -> dict[str, Any]:
    if r is None:
        return {}
    d = dict(r)
    for k in ("capabilities_json", "labels_json"):
        if k in d and isinstance(d[k], str):
            try:
                d[k.replace("_json", "")] = json.loads(d[k] or ("{}" if "cap" in k else "[]"))
            except Exception:
                d[k.replace("_json", "")] = {} if "cap" in k else []
    if "capabilities" not in d:
        d["capabilities"] = {}
    if "labels" not in d:
        d["labels"] = []
    return d


def list_workers(status: Optional[str] = None) -> list[dict[str, Any]]:
    with dbmod.connect() as conn:
        if status:
            rows = conn.execute(
                "SELECT * FROM workers WHERE status=? ORDER BY name", (status,)
            ).fetchall()
        else:
            rows = conn.execute("SELECT * FROM workers ORDER BY name").fetchall()
        return [_row(r) for r in rows]


def get_worker(worker_id: str) -> Optional[dict[str, Any]]:
    with dbmod.connect() as conn:
        r = conn.execute(
            "SELECT * FROM workers WHERE id=? OR name=?", (worker_id, worker_id)
        ).fetchone()
        return _row(r) if r else None


def upsert_worker(
    *,
    worker_id: str,
    name: str,
    hostname: str = "",
    tailscale_ip: str = "",
    platform: str = "",
    architecture: str = "",
    version: str = "5.1.0",
    capabilities: Optional[dict] = None,
    labels: Optional[list] = None,
    max_parallel_tasks: int = 1,
    status: str = "online",
) -> dict[str, Any]:
    caps = json.dumps(capabilities or {})
    labs = json.dumps(labels or [])
    now = dbmod.utc_now()
    with dbmod.connect() as conn:
        existing = conn.execute("SELECT id FROM workers WHERE id=?", (worker_id,)).fetchone()
        if existing:
            conn.execute(
                """UPDATE workers SET name=?, hostname=?, tailscale_ip=?, platform=?,
                   architecture=?, version=?, capabilities_json=?, labels_json=?,
                   max_parallel_tasks=?, status=?, last_heartbeat=?, quarantined=0,
                   quarantine_reason=NULL WHERE id=?""",
                (
                    name, hostname, tailscale_ip, platform, architecture, version,
                    caps, labs, max_parallel_tasks, status, now, worker_id,
                ),
            )
        else:
            conn.execute(
                """INSERT INTO workers
                   (id, name, hostname, tailscale_ip, platform, architecture, version,
                    status, capabilities_json, labels_json, max_parallel_tasks,
                    current_load, last_heartbeat, enrolled_at, quarantined)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,0,?,?,0)""",
                (
                    worker_id, name, hostname, tailscale_ip, platform, architecture,
                    version, status, caps, labs, max_parallel_tasks, now, now,
                ),
            )
        conn.commit()
    return get_worker(worker_id) or {}


def set_status(worker_id: str, status: str, reason: str = "") -> dict[str, Any]:
    if status not in VALID_STATUSES:
        raise ValueError(f"invalid status: {status}")
    with dbmod.connect() as conn:
        if status == "quarantined":
            conn.execute(
                "UPDATE workers SET status=?, quarantined=1, quarantine_reason=? WHERE id=?",
                (status, reason or "quarantined", worker_id),
            )
        elif status != "quarantined":
            # unquarantine path when leaving quarantined
            conn.execute(
                "UPDATE workers SET status=?, quarantined=0, quarantine_reason=NULL WHERE id=?",
                (status, worker_id),
            )
        conn.commit()
        _emit(conn, worker_id, f"worker.{status}", {"reason": reason})
        conn.commit()
    return get_worker(worker_id) or {}


def mark_offline_stale(threshold_secs: int = OFFLINE_THRESHOLD_SECS) -> list[str]:
    """Mark workers offline if heartbeat older than threshold. Returns ids marked."""
    marked: list[str] = []
    with dbmod.connect() as conn:
        rows = conn.execute(
            "SELECT id, last_heartbeat, status FROM workers WHERE status IN ('online','busy','degraded') AND quarantined=0"
        ).fetchall()
        now = dbmod.utc_now()
        for r in rows:
            hb = r["last_heartbeat"] or ""
            try:
                from datetime import datetime, timezone
                ts = datetime.strptime(hb[:26].rstrip("Z"), "%Y-%m-%dT%H:%M:%S.%f").replace(tzinfo=timezone.utc)
                age = (datetime.now(timezone.utc) - ts).total_seconds()
            except Exception:
                try:
                    from datetime import datetime, timezone
                    ts = datetime.strptime(hb[:19], "%Y-%m-%dT%H:%M:%S").replace(tzinfo=timezone.utc)
                    age = (datetime.now(timezone.utc) - ts).total_seconds()
                except Exception:
                    age = threshold_secs + 1
            if age > threshold_secs:
                conn.execute(
                    "UPDATE workers SET status='offline' WHERE id=?", (r["id"],)
                )
                _emit(conn, r["id"], "worker.offline", {"age_secs": age})
                marked.append(r["id"])
        conn.commit()
    return marked


def add_label(worker_id: str, label: str) -> dict[str, Any]:
    w = get_worker(worker_id)
    if not w:
        raise KeyError(worker_id)
    labels = list(w.get("labels") or [])
    if label not in labels:
        labels.append(label)
    with dbmod.connect() as conn:
        conn.execute(
            "UPDATE workers SET labels_json=? WHERE id=?",
            (json.dumps(labels), w["id"]),
        )
        conn.commit()
    return get_worker(w["id"]) or {}


def remove_label(worker_id: str, label: str) -> dict[str, Any]:
    w = get_worker(worker_id)
    if not w:
        raise KeyError(worker_id)
    labels = [x for x in (w.get("labels") or []) if x != label]
    with dbmod.connect() as conn:
        conn.execute(
            "UPDATE workers SET labels_json=? WHERE id=?",
            (json.dumps(labels), w["id"]),
        )
        conn.commit()
    return get_worker(w["id"]) or {}


def remove_worker(worker_id: str) -> bool:
    w = get_worker(worker_id)
    if not w:
        return False
    if w.get("status") in ("online", "busy") and int(w.get("current_load") or 0) > 0:
        raise RuntimeError("worker has active load; drain first")
    with dbmod.connect() as conn:
        conn.execute("DELETE FROM worker_sessions WHERE worker_id=?", (w["id"],))
        conn.execute("DELETE FROM workers WHERE id=?", (w["id"],))
        conn.commit()
    return True


def _emit(conn, worker_id: str, event_type: str, payload: Optional[dict] = None) -> None:
    conn.execute(
        "INSERT INTO worker_events (worker_id, event_type, payload_json) VALUES (?,?,?)",
        (worker_id, event_type, json.dumps(payload or {})),
    )
    try:
        conn.execute(
            "INSERT INTO events (ts, task_id, run_id, kind, message, payload_json) VALUES (?,?,?,?,?,?)",
            (dbmod.utc_now(), None, None, event_type, event_type, json.dumps({"worker_id": worker_id, **(payload or {})})),
        )
    except Exception:
        pass


def counts() -> dict[str, int]:
    with dbmod.connect() as conn:
        total = conn.execute("SELECT COUNT(*) FROM workers").fetchone()[0]
        online = conn.execute(
            "SELECT COUNT(*) FROM workers WHERE status IN ('online','busy','degraded')"
        ).fetchone()[0]
        offline = conn.execute(
            "SELECT COUNT(*) FROM workers WHERE status='offline'"
        ).fetchone()[0]
        quarantined = conn.execute(
            "SELECT COUNT(*) FROM workers WHERE quarantined=1 OR status='quarantined'"
        ).fetchone()[0]
    return {
        "total": total,
        "online": online,
        "offline": offline,
        "quarantined": quarantined,
    }
