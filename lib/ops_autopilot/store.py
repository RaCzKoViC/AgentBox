"""SQLite helpers for ops autopilot tables."""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any, Optional

_HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(_HERE.parent))

from storage import db as dbmod  # noqa: E402


def _j(obj: Any) -> str:
    return json.dumps(obj, ensure_ascii=False, default=str)


def _loads(s: Optional[str], default: Any = None) -> Any:
    if s is None or s == "":
        return default if default is not None else {}
    try:
        return json.loads(s)
    except Exception:
        return default if default is not None else {}


SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS playbook_runs (
    id TEXT PRIMARY KEY,
    playbook_id TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'created',
    dry_run INTEGER NOT NULL DEFAULT 1,
    risk_level TEXT NOT NULL DEFAULT 'LOW',
    triggered_by TEXT DEFAULT 'manual',
    started_at TEXT,
    finished_at TEXT,
    result_json TEXT DEFAULT '{}',
    error TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_playbook_runs_pb ON playbook_runs(playbook_id);
CREATE INDEX IF NOT EXISTS idx_playbook_runs_status ON playbook_runs(status);

CREATE TABLE IF NOT EXISTS remediation_actions (
    id TEXT PRIMARY KEY,
    action_type TEXT NOT NULL,
    risk_level TEXT NOT NULL DEFAULT 'LOW',
    status TEXT NOT NULL DEFAULT 'proposed',
    dry_run INTEGER NOT NULL DEFAULT 1,
    target TEXT DEFAULT '',
    detail_json TEXT DEFAULT '{}',
    approval_id TEXT,
    playbook_run_id TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    applied_at TEXT,
    FOREIGN KEY(playbook_run_id) REFERENCES playbook_runs(id)
);
CREATE INDEX IF NOT EXISTS idx_remediation_status ON remediation_actions(status);
CREATE INDEX IF NOT EXISTS idx_remediation_risk ON remediation_actions(risk_level);

CREATE TABLE IF NOT EXISTS drift_snapshots (
    id TEXT PRIMARY KEY,
    scope TEXT NOT NULL DEFAULT 'config',
    baseline_hash TEXT DEFAULT '',
    current_hash TEXT DEFAULT '',
    drifted INTEGER NOT NULL DEFAULT 0,
    findings_json TEXT DEFAULT '[]',
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_drift_scope ON drift_snapshots(scope);

CREATE TABLE IF NOT EXISTS maintenance_plans (
    id TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'draft',
    priority TEXT NOT NULL DEFAULT 'medium',
    window_start TEXT,
    window_end TEXT,
    actions_json TEXT DEFAULT '[]',
    forecast_json TEXT DEFAULT '{}',
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_maint_plans_status ON maintenance_plans(status);

CREATE TABLE IF NOT EXISTS ops_incidents (
    id TEXT PRIMARY KEY,
    fingerprint TEXT NOT NULL,
    title TEXT NOT NULL,
    severity TEXT NOT NULL DEFAULT 'SEV3',
    status TEXT NOT NULL DEFAULT 'open',
    component TEXT DEFAULT '',
    source TEXT DEFAULT 'anomaly',
    symptoms_json TEXT DEFAULT '[]',
    evidence_json TEXT DEFAULT '{}',
    suspected_causes_json TEXT DEFAULT '[]',
    runbook_id TEXT,
    resolution_json TEXT DEFAULT '{}',
    detected_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    resolved_at TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_ops_incidents_status ON ops_incidents(status);
CREATE INDEX IF NOT EXISTS idx_ops_incidents_fp ON ops_incidents(fingerprint);
CREATE INDEX IF NOT EXISTS idx_ops_incidents_sev ON ops_incidents(severity);

CREATE TABLE IF NOT EXISTS ops_incident_events (
    id TEXT PRIMARY KEY,
    incident_id TEXT NOT NULL,
    event_type TEXT NOT NULL,
    message TEXT DEFAULT '',
    detail_json TEXT DEFAULT '{}',
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY(incident_id) REFERENCES ops_incidents(id)
);
CREATE INDEX IF NOT EXISTS idx_ops_inc_events ON ops_incident_events(incident_id);

CREATE TABLE IF NOT EXISTS ops_anomalies (
    id TEXT PRIMARY KEY,
    kind TEXT NOT NULL,
    severity TEXT NOT NULL DEFAULT 'SEV3',
    component TEXT DEFAULT '',
    metric TEXT DEFAULT '',
    value_json TEXT DEFAULT '{}',
    threshold_json TEXT DEFAULT '{}',
    incident_id TEXT,
    status TEXT NOT NULL DEFAULT 'open',
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_ops_anomalies_status ON ops_anomalies(status);

CREATE TABLE IF NOT EXISTS ops_restore_drills (
    id TEXT PRIMARY KEY,
    backup_id TEXT,
    result TEXT NOT NULL DEFAULT 'PASS',
    verify_json TEXT DEFAULT '{}',
    dry_restore_json TEXT DEFAULT '{}',
    notes TEXT DEFAULT '',
    destructive INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_ops_restore_drills ON ops_restore_drills(created_at);

CREATE TABLE IF NOT EXISTS ops_health_samples (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    score INTEGER NOT NULL,
    status TEXT NOT NULL,
    components_json TEXT DEFAULT '{}',
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
"""


def ensure_schema(conn=None) -> None:
    own = conn is None
    if own:
        conn = dbmod.connect()
    conn.executescript(SCHEMA_SQL)
    if own:
        conn.commit()
        conn.close()


def insert_playbook_run(conn, row: dict[str, Any]) -> None:
    conn.execute(
        """INSERT INTO playbook_runs
           (id, playbook_id, status, dry_run, risk_level, triggered_by,
            started_at, finished_at, result_json, error, created_at)
           VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
        (
            row["id"],
            row["playbook_id"],
            row.get("status", "created"),
            1 if row.get("dry_run", True) else 0,
            row.get("risk_level", "LOW"),
            row.get("triggered_by", "manual"),
            row.get("started_at"),
            row.get("finished_at"),
            _j(row.get("result") or {}),
            row.get("error"),
            row.get("created_at") or dbmod.utc_now(),
        ),
    )


def update_playbook_run(conn, run_id: str, **fields: Any) -> None:
    sets = []
    vals: list[Any] = []
    for k, v in fields.items():
        if k == "result":
            sets.append("result_json=?")
            vals.append(_j(v))
        elif k == "dry_run":
            sets.append("dry_run=?")
            vals.append(1 if v else 0)
        else:
            sets.append(f"{k}=?")
            vals.append(v)
    if not sets:
        return
    vals.append(run_id)
    conn.execute(f"UPDATE playbook_runs SET {', '.join(sets)} WHERE id=?", vals)


def list_playbook_runs(playbook_id: Optional[str] = None, limit: int = 50) -> list[dict[str, Any]]:
    with dbmod.connect() as conn:
        ensure_schema(conn)
        if playbook_id:
            rows = conn.execute(
                "SELECT * FROM playbook_runs WHERE playbook_id=? ORDER BY created_at DESC LIMIT ?",
                (playbook_id, limit),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM playbook_runs ORDER BY created_at DESC LIMIT ?",
                (limit,),
            ).fetchall()
    return [_row_playbook(r) for r in rows]


def get_playbook_run(run_id: str) -> Optional[dict[str, Any]]:
    with dbmod.connect() as conn:
        ensure_schema(conn)
        r = conn.execute("SELECT * FROM playbook_runs WHERE id=?", (run_id,)).fetchone()
    return _row_playbook(r) if r else None


def _row_playbook(r) -> dict[str, Any]:
    d = dict(r)
    d["dry_run"] = bool(d.get("dry_run"))
    d["result"] = _loads(d.pop("result_json", None), {})
    return d


def insert_remediation(conn, row: dict[str, Any]) -> None:
    conn.execute(
        """INSERT INTO remediation_actions
           (id, action_type, risk_level, status, dry_run, target, detail_json,
            approval_id, playbook_run_id, created_at, applied_at)
           VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
        (
            row["id"],
            row["action_type"],
            row.get("risk_level", "LOW"),
            row.get("status", "proposed"),
            1 if row.get("dry_run", True) else 0,
            row.get("target", ""),
            _j(row.get("detail") or {}),
            row.get("approval_id"),
            row.get("playbook_run_id"),
            row.get("created_at") or dbmod.utc_now(),
            row.get("applied_at"),
        ),
    )


def update_remediation(conn, action_id: str, **fields: Any) -> None:
    sets = []
    vals: list[Any] = []
    for k, v in fields.items():
        if k == "detail":
            sets.append("detail_json=?")
            vals.append(_j(v))
        elif k == "dry_run":
            sets.append("dry_run=?")
            vals.append(1 if v else 0)
        else:
            sets.append(f"{k}=?")
            vals.append(v)
    if not sets:
        return
    vals.append(action_id)
    conn.execute(f"UPDATE remediation_actions SET {', '.join(sets)} WHERE id=?", vals)


def list_remediations(status: Optional[str] = None, limit: int = 50) -> list[dict[str, Any]]:
    with dbmod.connect() as conn:
        ensure_schema(conn)
        if status:
            rows = conn.execute(
                "SELECT * FROM remediation_actions WHERE status=? ORDER BY created_at DESC LIMIT ?",
                (status, limit),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM remediation_actions ORDER BY created_at DESC LIMIT ?",
                (limit,),
            ).fetchall()
    return [_row_remediation(r) for r in rows]


def get_remediation(action_id: str) -> Optional[dict[str, Any]]:
    with dbmod.connect() as conn:
        ensure_schema(conn)
        r = conn.execute("SELECT * FROM remediation_actions WHERE id=?", (action_id,)).fetchone()
    return _row_remediation(r) if r else None


def _row_remediation(r) -> dict[str, Any]:
    d = dict(r)
    d["dry_run"] = bool(d.get("dry_run"))
    d["detail"] = _loads(d.pop("detail_json", None), {})
    return d


def insert_drift(conn, row: dict[str, Any]) -> None:
    conn.execute(
        """INSERT INTO drift_snapshots
           (id, scope, baseline_hash, current_hash, drifted, findings_json, created_at)
           VALUES (?,?,?,?,?,?,?)""",
        (
            row["id"],
            row.get("scope", "config"),
            row.get("baseline_hash", ""),
            row.get("current_hash", ""),
            1 if row.get("drifted") else 0,
            _j(row.get("findings") or []),
            row.get("created_at") or dbmod.utc_now(),
        ),
    )


def list_drift(scope: Optional[str] = None, limit: int = 20) -> list[dict[str, Any]]:
    with dbmod.connect() as conn:
        ensure_schema(conn)
        if scope:
            rows = conn.execute(
                "SELECT * FROM drift_snapshots WHERE scope=? ORDER BY created_at DESC LIMIT ?",
                (scope, limit),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM drift_snapshots ORDER BY created_at DESC LIMIT ?",
                (limit,),
            ).fetchall()
    out = []
    for r in rows:
        d = dict(r)
        d["drifted"] = bool(d.get("drifted"))
        d["findings"] = _loads(d.pop("findings_json", None), [])
        out.append(d)
    return out


def insert_maintenance_plan(conn, row: dict[str, Any]) -> None:
    conn.execute(
        """INSERT INTO maintenance_plans
           (id, title, status, priority, window_start, window_end,
            actions_json, forecast_json, created_at, updated_at)
           VALUES (?,?,?,?,?,?,?,?,?,?)""",
        (
            row["id"],
            row["title"],
            row.get("status", "draft"),
            row.get("priority", "medium"),
            row.get("window_start"),
            row.get("window_end"),
            _j(row.get("actions") or []),
            _j(row.get("forecast") or {}),
            row.get("created_at") or dbmod.utc_now(),
            row.get("updated_at") or dbmod.utc_now(),
        ),
    )


def list_maintenance_plans(status: Optional[str] = None, limit: int = 20) -> list[dict[str, Any]]:
    with dbmod.connect() as conn:
        ensure_schema(conn)
        if status:
            rows = conn.execute(
                "SELECT * FROM maintenance_plans WHERE status=? ORDER BY created_at DESC LIMIT ?",
                (status, limit),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM maintenance_plans ORDER BY created_at DESC LIMIT ?",
                (limit,),
            ).fetchall()
    out = []
    for r in rows:
        d = dict(r)
        d["actions"] = _loads(d.pop("actions_json", None), [])
        d["forecast"] = _loads(d.pop("forecast_json", None), {})
        out.append(d)
    return out


# --- v5.6.2 gap-fill: incidents / anomalies / restore drills / health ---

def insert_incident(conn, row: dict[str, Any]) -> None:
    conn.execute(
        """INSERT INTO ops_incidents
           (id, fingerprint, title, severity, status, component, source,
            symptoms_json, evidence_json, suspected_causes_json, runbook_id,
            resolution_json, detected_at, updated_at, resolved_at, created_at)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (
            row["id"],
            row["fingerprint"],
            row["title"],
            row.get("severity", "SEV3"),
            row.get("status", "open"),
            row.get("component", ""),
            row.get("source", "anomaly"),
            _j(row.get("symptoms") or []),
            _j(row.get("evidence") or {}),
            _j(row.get("suspected_causes") or []),
            row.get("runbook_id"),
            _j(row.get("resolution") or {}),
            row.get("detected_at") or dbmod.utc_now(),
            row.get("updated_at") or dbmod.utc_now(),
            row.get("resolved_at"),
            row.get("created_at") or dbmod.utc_now(),
        ),
    )


def update_incident(conn, incident_id: str, **fields: Any) -> None:
    sets, vals = [], []
    mapping = {
        "symptoms": "symptoms_json",
        "evidence": "evidence_json",
        "suspected_causes": "suspected_causes_json",
        "resolution": "resolution_json",
    }
    for k, v in fields.items():
        col = mapping.get(k, k)
        if k in mapping:
            sets.append(f"{col}=?")
            vals.append(_j(v))
        else:
            sets.append(f"{col}=?")
            vals.append(v)
    if not sets:
        return
    vals.append(incident_id)
    conn.execute(f"UPDATE ops_incidents SET {', '.join(sets)} WHERE id=?", vals)


def _row_incident(r) -> dict[str, Any]:
    d = dict(r)
    d["symptoms"] = _loads(d.pop("symptoms_json", None), [])
    d["evidence"] = _loads(d.pop("evidence_json", None), {})
    d["suspected_causes"] = _loads(d.pop("suspected_causes_json", None), [])
    d["resolution"] = _loads(d.pop("resolution_json", None), {})
    return d


def list_incidents(status: Optional[str] = None, limit: int = 50) -> list[dict[str, Any]]:
    with dbmod.connect() as conn:
        ensure_schema(conn)
        if status:
            rows = conn.execute(
                "SELECT * FROM ops_incidents WHERE status=? ORDER BY detected_at DESC LIMIT ?",
                (status, limit),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM ops_incidents ORDER BY detected_at DESC LIMIT ?",
                (limit,),
            ).fetchall()
    return [_row_incident(r) for r in rows]


def get_incident(incident_id: str) -> Optional[dict[str, Any]]:
    with dbmod.connect() as conn:
        ensure_schema(conn)
        r = conn.execute("SELECT * FROM ops_incidents WHERE id=?", (incident_id,)).fetchone()
    return _row_incident(r) if r else None


def find_open_incident_by_fingerprint(fingerprint: str) -> Optional[dict[str, Any]]:
    with dbmod.connect() as conn:
        ensure_schema(conn)
        r = conn.execute(
            "SELECT * FROM ops_incidents WHERE fingerprint=? AND status NOT IN ('resolved','closed') "
            "ORDER BY detected_at DESC LIMIT 1",
            (fingerprint,),
        ).fetchone()
    return _row_incident(r) if r else None


def insert_incident_event(conn, row: dict[str, Any]) -> None:
    conn.execute(
        """INSERT INTO ops_incident_events
           (id, incident_id, event_type, message, detail_json, created_at)
           VALUES (?,?,?,?,?,?)""",
        (
            row["id"],
            row["incident_id"],
            row["event_type"],
            row.get("message", ""),
            _j(row.get("detail") or {}),
            row.get("created_at") or dbmod.utc_now(),
        ),
    )


def list_incident_events(incident_id: str, limit: int = 100) -> list[dict[str, Any]]:
    with dbmod.connect() as conn:
        ensure_schema(conn)
        rows = conn.execute(
            "SELECT * FROM ops_incident_events WHERE incident_id=? ORDER BY created_at ASC LIMIT ?",
            (incident_id, limit),
        ).fetchall()
    out = []
    for r in rows:
        d = dict(r)
        d["detail"] = _loads(d.pop("detail_json", None), {})
        out.append(d)
    return out


def insert_anomaly(conn, row: dict[str, Any]) -> None:
    conn.execute(
        """INSERT INTO ops_anomalies
           (id, kind, severity, component, metric, value_json, threshold_json,
            incident_id, status, created_at)
           VALUES (?,?,?,?,?,?,?,?,?,?)""",
        (
            row["id"],
            row["kind"],
            row.get("severity", "SEV3"),
            row.get("component", ""),
            row.get("metric", ""),
            _j(row.get("value") or {}),
            _j(row.get("threshold") or {}),
            row.get("incident_id"),
            row.get("status", "open"),
            row.get("created_at") or dbmod.utc_now(),
        ),
    )


def list_anomalies(status: Optional[str] = None, limit: int = 50) -> list[dict[str, Any]]:
    with dbmod.connect() as conn:
        ensure_schema(conn)
        if status:
            rows = conn.execute(
                "SELECT * FROM ops_anomalies WHERE status=? ORDER BY created_at DESC LIMIT ?",
                (status, limit),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM ops_anomalies ORDER BY created_at DESC LIMIT ?",
                (limit,),
            ).fetchall()
    out = []
    for r in rows:
        d = dict(r)
        d["value"] = _loads(d.pop("value_json", None), {})
        d["threshold"] = _loads(d.pop("threshold_json", None), {})
        out.append(d)
    return out


def insert_restore_drill(conn, row: dict[str, Any]) -> None:
    conn.execute(
        """INSERT INTO ops_restore_drills
           (id, backup_id, result, verify_json, dry_restore_json, notes, destructive, created_at)
           VALUES (?,?,?,?,?,?,?,?)""",
        (
            row["id"],
            row.get("backup_id"),
            row.get("result", "PASS"),
            _j(row.get("verify") or {}),
            _j(row.get("dry_restore") or {}),
            row.get("notes", ""),
            1 if row.get("destructive") else 0,
            row.get("created_at") or dbmod.utc_now(),
        ),
    )


def list_restore_drills(limit: int = 20) -> list[dict[str, Any]]:
    with dbmod.connect() as conn:
        ensure_schema(conn)
        rows = conn.execute(
            "SELECT * FROM ops_restore_drills ORDER BY created_at DESC LIMIT ?",
            (limit,),
        ).fetchall()
    out = []
    for r in rows:
        d = dict(r)
        d["destructive"] = bool(d.get("destructive"))
        d["verify"] = _loads(d.pop("verify_json", None), {})
        d["dry_restore"] = _loads(d.pop("dry_restore_json", None), {})
        out.append(d)
    return out


def insert_health_sample(conn, row: dict[str, Any]) -> None:
    conn.execute(
        """INSERT INTO ops_health_samples (score, status, components_json, created_at)
           VALUES (?,?,?,?)""",
        (
            int(row.get("score", 0)),
            row.get("status", "unknown"),
            _j(row.get("components") or {}),
            row.get("created_at") or dbmod.utc_now(),
        ),
    )


def latest_health_sample() -> Optional[dict[str, Any]]:
    with dbmod.connect() as conn:
        ensure_schema(conn)
        r = conn.execute(
            "SELECT * FROM ops_health_samples ORDER BY id DESC LIMIT 1"
        ).fetchone()
    if not r:
        return None
    d = dict(r)
    d["components"] = _loads(d.pop("components_json", None), {})
    return d

