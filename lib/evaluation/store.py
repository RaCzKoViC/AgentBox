"""SQLite helpers for evaluation tables."""
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


def ensure_schema(conn=None) -> None:
    """Idempotent create of v5.5 evaluation tables."""
    own = conn is None
    if own:
        conn = dbmod.connect()
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS benchmark_suites (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            version INTEGER NOT NULL DEFAULT 1,
            description TEXT DEFAULT '',
            enabled INTEGER NOT NULL DEFAULT 1,
            path TEXT DEFAULT '',
            meta_json TEXT DEFAULT '{}',
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS benchmark_cases (
            id TEXT PRIMARY KEY,
            suite_id TEXT NOT NULL,
            name TEXT NOT NULL,
            definition_json TEXT NOT NULL DEFAULT '{}',
            version INTEGER NOT NULL DEFAULT 1,
            enabled INTEGER NOT NULL DEFAULT 1,
            critical INTEGER NOT NULL DEFAULT 1,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(suite_id) REFERENCES benchmark_suites(id)
        );
        CREATE TABLE IF NOT EXISTS evaluation_runs (
            id TEXT PRIMARY KEY,
            suite_id TEXT NOT NULL,
            subject_type TEXT NOT NULL DEFAULT 'platform',
            subject_id TEXT NOT NULL DEFAULT 'agentbox',
            variant TEXT DEFAULT '',
            status TEXT NOT NULL DEFAULT 'created',
            score REAL,
            gate_status TEXT DEFAULT '',
            started_at TEXT,
            finished_at TEXT,
            metadata_json TEXT DEFAULT '{}',
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS evaluation_results (
            id TEXT PRIMARY KEY,
            evaluation_run_id TEXT NOT NULL,
            case_id TEXT NOT NULL,
            success INTEGER,
            scores_json TEXT DEFAULT '{}',
            metrics_json TEXT DEFAULT '{}',
            artifacts_json TEXT DEFAULT '{}',
            error TEXT,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(evaluation_run_id) REFERENCES evaluation_runs(id),
            FOREIGN KEY(case_id) REFERENCES benchmark_cases(id)
        );
        CREATE TABLE IF NOT EXISTS baselines (
            id TEXT PRIMARY KEY,
            suite_id TEXT NOT NULL,
            subject_type TEXT NOT NULL DEFAULT 'platform',
            subject_id TEXT NOT NULL DEFAULT 'agentbox',
            version TEXT DEFAULT '1',
            summary_json TEXT NOT NULL DEFAULT '{}',
            evaluation_run_id TEXT,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS improvement_proposals (
            id TEXT PRIMARY KEY,
            target_type TEXT NOT NULL,
            target_id TEXT NOT NULL,
            current_version TEXT DEFAULT '',
            proposed_version TEXT DEFAULT '',
            proposal_json TEXT NOT NULL DEFAULT '{}',
            evidence_json TEXT DEFAULT '{}',
            risk_level TEXT DEFAULT 'LOW',
            status TEXT NOT NULL DEFAULT 'draft',
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS prompt_versions (
            id TEXT PRIMARY KEY,
            prompt_name TEXT NOT NULL,
            version INTEGER NOT NULL,
            content TEXT NOT NULL,
            content_hash TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'draft',
            parent_id TEXT,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(prompt_name, version)
        );
        CREATE TABLE IF NOT EXISTS workflow_versions (
            id TEXT PRIMARY KEY,
            workflow_name TEXT NOT NULL,
            version INTEGER NOT NULL,
            definition_json TEXT NOT NULL DEFAULT '{}',
            content_hash TEXT NOT NULL DEFAULT '',
            status TEXT NOT NULL DEFAULT 'draft',
            parent_id TEXT,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(workflow_name, version)
        );
        CREATE TABLE IF NOT EXISTS regression_events (
            id TEXT PRIMARY KEY,
            evaluation_run_id TEXT,
            suite_id TEXT,
            kind TEXT NOT NULL,
            detail_json TEXT DEFAULT '{}',
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        CREATE INDEX IF NOT EXISTS idx_eval_runs_suite ON evaluation_runs(suite_id);
        CREATE INDEX IF NOT EXISTS idx_eval_results_run ON evaluation_results(evaluation_run_id);
        CREATE INDEX IF NOT EXISTS idx_baselines_suite ON baselines(suite_id);
        CREATE INDEX IF NOT EXISTS idx_proposals_status ON improvement_proposals(status);
        CREATE INDEX IF NOT EXISTS idx_prompt_versions_name ON prompt_versions(prompt_name);
        CREATE INDEX IF NOT EXISTS idx_workflow_versions_name ON workflow_versions(workflow_name);
        """
    )
    if own:
        conn.commit()
        conn.close()


def insert_run(conn, row: dict[str, Any]) -> None:
    conn.execute(
        """INSERT INTO evaluation_runs
           (id, suite_id, subject_type, subject_id, variant, status, score, gate_status,
            started_at, finished_at, metadata_json, created_at)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
        (
            row["id"], row["suite_id"], row.get("subject_type", "platform"),
            row.get("subject_id", "agentbox"), row.get("variant", ""),
            row["status"], row.get("score"), row.get("gate_status", ""),
            row.get("started_at"), row.get("finished_at"),
            _j(row.get("metadata") or {}), row.get("created_at") or dbmod.utc_now(),
        ),
    )


def update_run(conn, run_id: str, **fields: Any) -> None:
    allowed = {"status", "score", "gate_status", "started_at", "finished_at", "metadata_json", "variant"}
    sets, vals = [], []
    for k, v in fields.items():
        if k == "metadata":
            k = "metadata_json"
            v = _j(v)
        if k not in allowed:
            continue
        sets.append(f"{k}=?")
        vals.append(v)
    if not sets:
        return
    vals.append(run_id)
    conn.execute(f"UPDATE evaluation_runs SET {', '.join(sets)} WHERE id=?", vals)


def insert_result(conn, row: dict[str, Any]) -> None:
    conn.execute(
        """INSERT INTO evaluation_results
           (id, evaluation_run_id, case_id, success, scores_json, metrics_json,
            artifacts_json, error, created_at)
           VALUES (?,?,?,?,?,?,?,?,?)""",
        (
            row["id"], row["evaluation_run_id"], row["case_id"],
            1 if row.get("success") else 0,
            _j(row.get("scores") or {}), _j(row.get("metrics") or {}),
            _j(row.get("artifacts") or {}), row.get("error"),
            row.get("created_at") or dbmod.utc_now(),
        ),
    )


def get_run(run_id: str) -> Optional[dict[str, Any]]:
    with dbmod.connect() as conn:
        ensure_schema(conn)
        r = conn.execute("SELECT * FROM evaluation_runs WHERE id=?", (run_id,)).fetchone()
        if not r:
            return None
        d = dict(r)
        d["metadata"] = _loads(d.pop("metadata_json", None), {})
        results = [
            {
                **dict(x),
                "scores": _loads(x["scores_json"], {}),
                "metrics": _loads(x["metrics_json"], {}),
                "artifacts": _loads(x["artifacts_json"], {}),
                "success": bool(x["success"]),
            }
            for x in conn.execute(
                "SELECT * FROM evaluation_results WHERE evaluation_run_id=? ORDER BY created_at",
                (run_id,),
            ).fetchall()
        ]
        for x in results:
            for k in ("scores_json", "metrics_json", "artifacts_json"):
                x.pop(k, None)
        d["results"] = results
        return d


def list_runs(suite_id: Optional[str] = None, limit: int = 50) -> list[dict[str, Any]]:
    with dbmod.connect() as conn:
        ensure_schema(conn)
        if suite_id:
            rows = conn.execute(
                "SELECT * FROM evaluation_runs WHERE suite_id=? ORDER BY created_at DESC LIMIT ?",
                (suite_id, limit),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM evaluation_runs ORDER BY created_at DESC LIMIT ?",
                (limit,),
            ).fetchall()
        out = []
        for r in rows:
            d = dict(r)
            d["metadata"] = _loads(d.pop("metadata_json", None), {})
            out.append(d)
        return out
