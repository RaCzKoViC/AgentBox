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
