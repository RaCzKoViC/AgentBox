#!/usr/bin/env python3
"""AgentBox v5 SQLite storage module (5.0.0 Stable — + recovery statuses / migrations)."""
from __future__ import annotations

import json
import os
import sqlite3
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

ALLOWED_STATUSES = frozenset({
    "created", "planned", "awaiting_approval", "queued", "scheduled",
    "running", "paused", "blocked", "failed", "completed", "reviewing",
    "awaiting_merge", "merged", "rejected", "cancelled", "rolled_back",
    "paused_budget",
    # beta3
    "awaiting_policy", "policy_denied", "approved", "budget_paused",
    "budget_exceeded", "risk_blocked", "security_blocked", "ready",
    # stable recovery
    "interrupted", "recovering", "recovered", "recovery_failed", "orphaned", "stale",
})

# Dependencies considered satisfied when in these statuses
DONE_STATUSES = frozenset({"completed", "merged"})

DEFAULT_DATA_ROOT = Path.home() / ".local" / "share" / "agentbox" / "v5"
DEFAULT_DB_PATH = DEFAULT_DATA_ROOT / "data" / "agentbox.db"


def utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def new_id(prefix: str = "") -> str:
    u = uuid.uuid4().hex[:12]
    return f"{prefix}{u}" if prefix else u


def resolve_db_path(db_path: Optional[str] = None) -> Path:
    if db_path:
        return Path(db_path)
    env = os.environ.get("AGENTBOX_V5_DB")
    if env:
        return Path(env)
    return DEFAULT_DB_PATH


def schema_path() -> Path:
    here = Path(__file__).resolve().parent
    candidates = [
        here / "schema.sql",
        Path(__file__).resolve().parent.parent.parent / "lib" / "storage" / "schema.sql",
    ]
    for c in candidates:
        if c.is_file():
            return c
    raise FileNotFoundError("schema.sql not found")


def connect(db_path: Optional[str] = None) -> sqlite3.Connection:
    path = resolve_db_path(db_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path), timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    return conn


def _migrate(conn: sqlite3.Connection) -> None:
    """Add alpha3/beta1 columns/tables to older DBs."""
    cols = {r[1] for r in conn.execute("PRAGMA table_info(tasks)").fetchall()}
    alters = []
    for col, decl in [
        ("usage_tokens", "INTEGER NOT NULL DEFAULT 0"),
        ("usage_cost", "REAL NOT NULL DEFAULT 0.0"),
        ("usage_runtime_secs", "INTEGER NOT NULL DEFAULT 0"),
        ("usage_retries", "INTEGER NOT NULL DEFAULT 0"),
        ("usage_files_changed", "INTEGER NOT NULL DEFAULT 0"),
    ]:
        if col not in cols:
            alters.append(f"ALTER TABLE tasks ADD COLUMN {col} {decl}")
    for a in alters:
        conn.execute(a)
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS approvals (
            id          TEXT PRIMARY KEY,
            task_id     TEXT NOT NULL,
            gate        TEXT NOT NULL,
            status      TEXT NOT NULL DEFAULT 'pending',
            reason      TEXT DEFAULT '',
            created_at  TEXT NOT NULL,
            resolved_at TEXT,
            FOREIGN KEY (task_id) REFERENCES tasks(id)
        )
        """
    )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_approvals_task ON approvals(task_id)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_approvals_status ON approvals(status)")

    # beta1: memories
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS memories (
            id          TEXT PRIMARY KEY,
            scope       TEXT NOT NULL,
            scope_key   TEXT NOT NULL DEFAULT '',
            kind        TEXT NOT NULL DEFAULT 'note',
            content     TEXT NOT NULL,
            meta_json   TEXT NOT NULL DEFAULT '{}',
            created_at  TEXT NOT NULL,
            updated_at  TEXT NOT NULL,
            expires_at  TEXT
        )
        """
    )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_memories_scope ON memories(scope, scope_key)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_memories_updated ON memories(updated_at)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_memories_expires ON memories(expires_at)")

    # beta1: extend agents table (role / capabilities / provider / model)
    agent_cols = {r[1] for r in conn.execute("PRAGMA table_info(agents)").fetchall()}
    if agent_cols:
        for col, decl in [
            ("role", "TEXT DEFAULT ''"),
            ("capabilities_json", "TEXT DEFAULT '[]'"),
            ("provider", "TEXT DEFAULT ''"),
            ("model", "TEXT DEFAULT ''"),
        ]:
            if col not in agent_cols:
                conn.execute(f"ALTER TABLE agents ADD COLUMN {col} {decl}")
        # Backfill role from kind if present and role empty
        if "kind" in agent_cols:
            conn.execute(
                "UPDATE agents SET role = kind WHERE (role IS NULL OR role = '') AND kind IS NOT NULL AND kind != ''"
            )
    else:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS agents (
                id                 TEXT PRIMARY KEY,
                name               TEXT NOT NULL,
                role               TEXT DEFAULT '',
                capabilities_json  TEXT DEFAULT '[]',
                provider           TEXT DEFAULT '',
                model              TEXT DEFAULT '',
                status             TEXT DEFAULT 'active',
                meta_json          TEXT DEFAULT '{}',
                created_at         TEXT NOT NULL,
                updated_at         TEXT NOT NULL
            )
            """
        )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_agents_status ON agents(status)")

    # beta2: agent_handoffs / metrics / agent_runs / artifacts
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS agent_handoffs (
            id              TEXT PRIMARY KEY,
            task_id         TEXT NOT NULL,
            run_id          TEXT,
            source_agent    TEXT NOT NULL,
            target_agent    TEXT NOT NULL,
            status          TEXT NOT NULL DEFAULT 'pending',
            reason          TEXT DEFAULT '',
            context_json    TEXT DEFAULT '{}',
            required        INTEGER NOT NULL DEFAULT 1,
            retries         INTEGER NOT NULL DEFAULT 0,
            max_retries     INTEGER NOT NULL DEFAULT 2,
            error           TEXT DEFAULT '',
            result_json     TEXT DEFAULT '{}',
            created_at      TEXT NOT NULL,
            accepted_at     TEXT,
            completed_at    TEXT,
            FOREIGN KEY (task_id) REFERENCES tasks(id)
        )
        """
    )
    # Migrate extra columns if older handoffs table existed without them
    hcols = {r[1] for r in conn.execute("PRAGMA table_info(agent_handoffs)").fetchall()}
    for col, decl in [
        ("required", "INTEGER NOT NULL DEFAULT 1"),
        ("retries", "INTEGER NOT NULL DEFAULT 0"),
        ("max_retries", "INTEGER NOT NULL DEFAULT 2"),
        ("error", "TEXT DEFAULT ''"),
        ("result_json", "TEXT DEFAULT '{}'"),
    ]:
        if col not in hcols:
            conn.execute(f"ALTER TABLE agent_handoffs ADD COLUMN {col} {decl}")

    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS metrics (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            metric_name     TEXT NOT NULL,
            metric_value    REAL NOT NULL,
            labels_json     TEXT DEFAULT '{}',
            created_at      TEXT NOT NULL
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS agent_runs (
            id              TEXT PRIMARY KEY,
            task_id         TEXT NOT NULL,
            run_id          TEXT,
            agent_name      TEXT NOT NULL,
            provider        TEXT DEFAULT '',
            model           TEXT DEFAULT '',
            status          TEXT NOT NULL DEFAULT 'running',
            started_at      TEXT NOT NULL,
            finished_at     TEXT,
            duration_ms     INTEGER,
            exit_code       INTEGER,
            error           TEXT DEFAULT '',
            FOREIGN KEY (task_id) REFERENCES tasks(id)
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS artifacts (
            id              TEXT PRIMARY KEY,
            task_id         TEXT NOT NULL,
            run_id          TEXT,
            agent_name      TEXT DEFAULT '',
            kind            TEXT DEFAULT 'file',
            path            TEXT NOT NULL,
            metadata_json   TEXT DEFAULT '{}',
            created_at      TEXT NOT NULL,
            FOREIGN KEY (task_id) REFERENCES tasks(id)
        )
        """
    )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_handoff_task ON agent_handoffs(task_id)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_metrics_name ON metrics(metric_name)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_agent_runs_task ON agent_runs(task_id)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_artifacts_task ON artifacts(task_id)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_handoff_status ON agent_handoffs(status)")

    # beta3: policies / budgets / budget_usage / risk_assessments + approvals columns
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS policies (
            id TEXT PRIMARY KEY,
            scope_type TEXT NOT NULL,
            scope_id TEXT,
            category TEXT NOT NULL,
            action TEXT NOT NULL,
            effect TEXT NOT NULL,
            config_json TEXT,
            enabled INTEGER NOT NULL DEFAULT 1,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS budgets (
            id TEXT PRIMARY KEY,
            scope_type TEXT NOT NULL,
            scope_id TEXT,
            metric TEXT NOT NULL,
            limit_value REAL NOT NULL,
            period TEXT,
            enabled INTEGER NOT NULL DEFAULT 1,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS budget_usage (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            scope_type TEXT NOT NULL,
            scope_id TEXT,
            metric TEXT NOT NULL,
            value REAL NOT NULL,
            task_id TEXT,
            run_id TEXT,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS risk_assessments (
            id TEXT PRIMARY KEY,
            task_id TEXT,
            run_id TEXT,
            agent_name TEXT,
            action TEXT NOT NULL,
            resource TEXT,
            risk_score INTEGER NOT NULL,
            risk_level TEXT NOT NULL,
            decision TEXT NOT NULL,
            reasons_json TEXT,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_policy_scope ON policies(scope_type, scope_id)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_budget_scope ON budgets(scope_type, scope_id)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_budget_usage_scope ON budget_usage(scope_type, scope_id, metric)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_risk_task ON risk_assessments(task_id)")

    # Carefully extend approvals (alpha3 → beta3) — no data loss
    appr_cols = {r[1] for r in conn.execute("PRAGMA table_info(approvals)").fetchall()}
    if appr_cols:
        for col, decl in [
            ("run_id", "TEXT"),
            ("handoff_id", "TEXT"),
            ("approval_type", "TEXT"),
            ("requested_by", "TEXT"),
            ("risk_score", "INTEGER"),
            ("payload_json", "TEXT"),
            ("requested_at", "TEXT"),
            ("decided_at", "TEXT"),
            ("decided_by", "TEXT"),
        ]:
            if col not in appr_cols:
                conn.execute(f"ALTER TABLE approvals ADD COLUMN {col} {decl}")
        # Backfill approval_type from gate, requested_at from created_at
        appr_cols2 = {r[1] for r in conn.execute("PRAGMA table_info(approvals)").fetchall()}
        if "gate" in appr_cols2 and "approval_type" in appr_cols2:
            conn.execute(
                "UPDATE approvals SET approval_type = gate WHERE approval_type IS NULL OR approval_type = ''"
            )
        if "created_at" in appr_cols2 and "requested_at" in appr_cols2:
            conn.execute(
                "UPDATE approvals SET requested_at = created_at WHERE requested_at IS NULL OR requested_at = ''"
            )
        if "resolved_at" in appr_cols2 and "decided_at" in appr_cols2:
            conn.execute(
                "UPDATE approvals SET decided_at = resolved_at WHERE decided_at IS NULL AND resolved_at IS NOT NULL"
            )

    # rc1: web control plane
    conn.executescript("""
CREATE TABLE IF NOT EXISTS web_sessions (
    id TEXT PRIMARY KEY,
    user_role TEXT NOT NULL,
    token_hash TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    expires_at TEXT NOT NULL,
    revoked_at TEXT
);
CREATE TABLE IF NOT EXISTS api_audit (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    method TEXT NOT NULL,
    path TEXT NOT NULL,
    actor TEXT,
    role TEXT,
    status_code INTEGER,
    task_id TEXT,
    remote_addr TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS web_preferences (
    key TEXT PRIMARY KEY,
    value_json TEXT,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_web_sessions_expiry ON web_sessions(expires_at);
CREATE INDEX IF NOT EXISTS idx_api_audit_created ON api_audit(created_at);
""")

    # stable: migrations + runtime_processes
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS migrations (
            version INTEGER PRIMARY KEY,
            name TEXT NOT NULL,
            applied_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            checksum TEXT NOT NULL
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS runtime_processes (
            id TEXT PRIMARY KEY,
            component TEXT NOT NULL,
            pid INTEGER,
            state TEXT NOT NULL,
            started_at TEXT,
            heartbeat_at TEXT,
            metadata_json TEXT
        )
        """
    )

def init_db(db_path: Optional[str] = None) -> Path:
    path = resolve_db_path(db_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    sql = schema_path().read_text(encoding="utf-8")
    with connect(str(path)) as conn:
        conn.executescript(sql)
        _migrate(conn)
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_tasks_priority ON tasks(priority DESC, created_at ASC)"
        )
        conn.execute("CREATE INDEX IF NOT EXISTS idx_runs_status ON runs(status)")
        conn.commit()
    return path


def parse_depends_on(raw: Any) -> list[str]:
    if raw is None:
        return []
    if isinstance(raw, list):
        return [str(x) for x in raw]
    if isinstance(raw, str):
        s = raw.strip()
        if not s:
            return []
        try:
            data = json.loads(s)
            if isinstance(data, list):
                return [str(x) for x in data]
        except json.JSONDecodeError:
            return []
    return []


def create_task(
    project_id: str,
    title: str,
    description: str = "",
    provider: str = "",
    model: str = "",
    priority: int = 0,
    meta: Optional[dict] = None,
    depends_on: Optional[list] = None,
    budget_tokens: int = 0,
    budget_cost: float = 0.0,
    approval_policy: str = "auto",
    sandbox_mode: str = "worktree",
    timeout_secs: int = 0,
    db_path: Optional[str] = None,
) -> dict:
    tid = new_id("t_")
    now = utc_now()
    meta_json = json.dumps(meta or {})
    deps_json = json.dumps(list(depends_on or []))
    with connect(db_path) as conn:
        conn.execute(
            """
            INSERT INTO tasks (
                id, project_id, title, description, priority, status,
                created_at, updated_at, provider, model, depends_on_json, meta_json,
                budget_tokens, budget_cost, approval_policy, sandbox_mode, timeout_secs
            ) VALUES (?, ?, ?, ?, ?, 'created', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                tid, project_id, title, description, priority, now, now, provider, model,
                deps_json, meta_json, int(budget_tokens), float(budget_cost),
                approval_policy or "auto", sandbox_mode or "worktree", int(timeout_secs or 0),
            ),
        )
        conn.execute(
            """
            INSERT INTO events (ts, task_id, run_id, kind, message, payload_json)
            VALUES (?, ?, NULL, 'task.created', ?, ?)
            """,
            (now, tid, f"Created task: {title}", json.dumps({"project_id": project_id})),
        )
        conn.commit()
    return get_task(tid, db_path)


def get_task(task_id: str, db_path: Optional[str] = None) -> Optional[dict]:
    with connect(db_path) as conn:
        row = conn.execute("SELECT * FROM tasks WHERE id = ?", (task_id,)).fetchone()
        return dict(row) if row else None


def list_tasks(status: Optional[str] = None, db_path: Optional[str] = None) -> list[dict]:
    with connect(db_path) as conn:
        if status:
            rows = conn.execute(
                "SELECT * FROM tasks WHERE status = ? ORDER BY created_at ASC",
                (status,),
            ).fetchall()
        else:
            rows = conn.execute("SELECT * FROM tasks ORDER BY created_at ASC").fetchall()
        return [dict(r) for r in rows]


def set_task_status(task_id: str, status: str, db_path: Optional[str] = None) -> dict:
    if status not in ALLOWED_STATUSES:
        raise ValueError(f"invalid status: {status}; allowed: {sorted(ALLOWED_STATUSES)}")
    task = get_task(task_id, db_path)
    if not task:
        raise KeyError(f"task not found: {task_id}")
    now = utc_now()
    old = task["status"]
    with connect(db_path) as conn:
        conn.execute(
            "UPDATE tasks SET status = ?, updated_at = ? WHERE id = ?",
            (status, now, task_id),
        )
        conn.execute(
            """
            INSERT INTO events (ts, task_id, run_id, kind, message, payload_json)
            VALUES (?, ?, NULL, 'task.status', ?, ?)
            """,
            (
                now,
                task_id,
                f"Status {old} -> {status}",
                json.dumps({"from": old, "to": status}),
            ),
        )
        conn.commit()
    return get_task(task_id, db_path)


def set_depends_on(task_id: str, deps: list[str], db_path: Optional[str] = None) -> dict:
    """Set depends_on_json for a task. Raises on unknown ids or cycles."""
    task = get_task(task_id, db_path)
    if not task:
        raise KeyError(f"task not found: {task_id}")
    deps = [str(d) for d in deps]
    # Deduplicate preserving order
    seen: set[str] = set()
    uniq: list[str] = []
    for d in deps:
        if d not in seen:
            seen.add(d)
            uniq.append(d)
    deps = uniq
    if task_id in deps:
        raise ValueError(f"cycle: task {task_id} cannot depend on itself")
    with connect(db_path) as conn:
        for d in deps:
            row = conn.execute("SELECT id FROM tasks WHERE id = ?", (d,)).fetchone()
            if not row:
                raise KeyError(f"depends_on task not found: {d}")
        # Cycle detection: would task_id become reachable from any dep?
        if _would_create_cycle(conn, task_id, deps):
            raise ValueError(f"cycle detected: adding deps {deps} to {task_id}")
        now = utc_now()
        conn.execute(
            "UPDATE tasks SET depends_on_json = ?, updated_at = ? WHERE id = ?",
            (json.dumps(deps), now, task_id),
        )
        conn.execute(
            """
            INSERT INTO events (ts, task_id, run_id, kind, message, payload_json)
            VALUES (?, ?, NULL, 'task.depends_on', ?, ?)
            """,
            (now, task_id, f"depends_on set to {deps}", json.dumps({"depends_on": deps})),
        )
        conn.commit()
    return get_task(task_id, db_path)


def add_depends_on(task_id: str, on_ids: list[str], db_path: Optional[str] = None) -> dict:
    task = get_task(task_id, db_path)
    if not task:
        raise KeyError(f"task not found: {task_id}")
    current = parse_depends_on(task.get("depends_on_json"))
    merged = current[:]
    for oid in on_ids:
        if oid not in merged:
            merged.append(oid)
    return set_depends_on(task_id, merged, db_path=db_path)


def _load_dep_map(conn: sqlite3.Connection) -> dict[str, list[str]]:
    rows = conn.execute("SELECT id, depends_on_json FROM tasks").fetchall()
    out: dict[str, list[str]] = {}
    for r in rows:
        out[r["id"]] = parse_depends_on(r["depends_on_json"])
    return out


def _would_create_cycle(conn: sqlite3.Connection, task_id: str, new_deps: list[str]) -> bool:
    """True if setting task_id's deps to new_deps would introduce a cycle."""
    dep_map = _load_dep_map(conn)
    dep_map[task_id] = list(new_deps)

    def reaches(start: str, target: str, visiting: set[str]) -> bool:
        if start == target:
            return True
        if start in visiting:
            return False
        visiting.add(start)
        for nxt in dep_map.get(start, []):
            if reaches(nxt, target, visiting):
                return True
        visiting.discard(start)
        return False

    # Cycle if from any new dep we can reach task_id (meaning task_id -> dep -> ... -> task_id)
    for d in new_deps:
        if reaches(d, task_id, set()):
            return True
    return False


def deps_satisfied(task: dict, db_path: Optional[str] = None) -> bool:
    deps = parse_depends_on(task.get("depends_on_json"))
    if not deps:
        return True
    with connect(db_path) as conn:
        for d in deps:
            row = conn.execute("SELECT status FROM tasks WHERE id = ?", (d,)).fetchone()
            if not row or row["status"] not in DONE_STATUSES:
                return False
    return True


def list_ready_queued(limit: int = 50, db_path: Optional[str] = None) -> list[dict]:
    """Queued tasks whose depends_on are all completed/merged.
    Ordered by priority DESC, created_at ASC.
    """
    with connect(db_path) as conn:
        rows = conn.execute(
            """
            SELECT * FROM tasks
            WHERE status = 'queued'
            ORDER BY priority DESC, created_at ASC
            """
        ).fetchall()
        ready: list[dict] = []
        for r in rows:
            task = dict(r)
            deps = parse_depends_on(task.get("depends_on_json"))
            ok = True
            for d in deps:
                dep_row = conn.execute(
                    "SELECT status FROM tasks WHERE id = ?", (d,)
                ).fetchone()
                if not dep_row or dep_row["status"] not in DONE_STATUSES:
                    ok = False
                    break
            if ok:
                ready.append(task)
                if len(ready) >= limit:
                    break
        return ready


def count_running(db_path: Optional[str] = None) -> int:
    with connect(db_path) as conn:
        row = conn.execute(
            "SELECT COUNT(*) AS n FROM tasks WHERE status IN ('running', 'scheduled')"
        ).fetchone()
        return int(row["n"])


def count_by_status(db_path: Optional[str] = None) -> dict[str, int]:
    with connect(db_path) as conn:
        rows = conn.execute(
            "SELECT status, COUNT(*) AS n FROM tasks GROUP BY status"
        ).fetchall()
        return {r["status"]: int(r["n"]) for r in rows}


def queue_stats(db_path: Optional[str] = None) -> dict:
    counts = count_by_status(db_path)
    ready = list_ready_queued(limit=1000, db_path=db_path)
    return {
        "queued": counts.get("queued", 0),
        "ready": len(ready),
        "running": counts.get("running", 0) + counts.get("scheduled", 0),
        "scheduled": counts.get("scheduled", 0),
        "completed": counts.get("completed", 0),
        "failed": counts.get("failed", 0),
        "by_status": counts,
    }


def pick_queued_task(db_path: Optional[str] = None) -> Optional[dict]:
    """Backward-compatible: pick one ready queued task (deps satisfied)."""
    ready = list_ready_queued(limit=1, db_path=db_path)
    return ready[0] if ready else None


def claim_ready_task(task_id: str, db_path: Optional[str] = None) -> Optional[dict]:
    """Atomically move queued→scheduled if still queued. Returns task or None."""
    now = utc_now()
    with connect(db_path) as conn:
        cur = conn.execute(
            """
            UPDATE tasks SET status = 'scheduled', updated_at = ?
            WHERE id = ? AND status = 'queued'
            """,
            (now, task_id),
        )
        if cur.rowcount != 1:
            conn.commit()
            return None
        conn.execute(
            """
            INSERT INTO events (ts, task_id, run_id, kind, message, payload_json)
            VALUES (?, ?, NULL, 'task.status', ?, ?)
            """,
            (
                now,
                task_id,
                "Status queued -> scheduled",
                json.dumps({"from": "queued", "to": "scheduled"}),
            ),
        )
        conn.commit()
    return get_task(task_id, db_path)


def create_run(task_id: str, worker_id: str = "", db_path: Optional[str] = None) -> dict:
    rid = new_id("r_")
    now = utc_now()
    with connect(db_path) as conn:
        conn.execute(
            """
            INSERT INTO runs (id, task_id, status, started_at, worker_id, stats_json)
            VALUES (?, ?, 'running', ?, ?, '{}')
            """,
            (rid, task_id, now, worker_id),
        )
        conn.execute(
            "UPDATE tasks SET status = 'running', updated_at = ?, current_stage = 'stub' WHERE id = ?",
            (now, task_id),
        )
        conn.execute(
            """
            INSERT INTO events (ts, task_id, run_id, kind, message, payload_json)
            VALUES (?, ?, ?, 'run.started', ?, ?)
            """,
            (now, task_id, rid, f"Run started by {worker_id or 'daemon'}", json.dumps({})),
        )
        conn.commit()
    return get_run(rid, db_path)


def get_run(run_id: str, db_path: Optional[str] = None) -> Optional[dict]:
    with connect(db_path) as conn:
        row = conn.execute("SELECT * FROM runs WHERE id = ?", (run_id,)).fetchone()
        return dict(row) if row else None


def list_runs(task_id: Optional[str] = None, db_path: Optional[str] = None) -> list[dict]:
    with connect(db_path) as conn:
        if task_id:
            rows = conn.execute(
                "SELECT * FROM runs WHERE task_id = ? ORDER BY started_at DESC",
                (task_id,),
            ).fetchall()
        else:
            rows = conn.execute("SELECT * FROM runs ORDER BY started_at DESC").fetchall()
        return [dict(r) for r in rows]


def finish_run(
    run_id: str,
    status: str = "completed",
    exit_code: int = 0,
    error: str = "",
    stats: Optional[dict] = None,
    db_path: Optional[str] = None,
) -> dict:
    run = get_run(run_id, db_path)
    if not run:
        raise KeyError(f"run not found: {run_id}")
    now = utc_now()
    task_status = "completed" if status == "completed" else "failed"
    with connect(db_path) as conn:
        conn.execute(
            """
            UPDATE runs SET status = ?, finished_at = ?, exit_code = ?, error = ?, stats_json = ?
            WHERE id = ?
            """,
            (status, now, exit_code, error, json.dumps(stats or {}), run_id),
        )
        conn.execute(
            "UPDATE tasks SET status = ?, updated_at = ?, current_stage = 'done' WHERE id = ?",
            (task_status, now, run["task_id"]),
        )
        conn.execute(
            """
            INSERT INTO events (ts, task_id, run_id, kind, message, payload_json)
            VALUES (?, ?, ?, 'run.finished', ?, ?)
            """,
            (
                now,
                run["task_id"],
                run_id,
                f"Run finished: {status}",
                json.dumps({"exit_code": exit_code, "error": error}),
            ),
        )
        conn.commit()
    return get_run(run_id, db_path)


def emit_event(
    kind: str,
    message: str = "",
    task_id: Optional[str] = None,
    run_id: Optional[str] = None,
    payload: Optional[dict] = None,
    db_path: Optional[str] = None,
) -> int:
    now = utc_now()
    with connect(db_path) as conn:
        cur = conn.execute(
            """
            INSERT INTO events (ts, task_id, run_id, kind, message, payload_json)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (now, task_id, run_id, kind, message, json.dumps(payload or {})),
        )
        conn.commit()
        return int(cur.lastrowid)


def list_events(
    task_id: Optional[str] = None,
    limit: int = 50,
    db_path: Optional[str] = None,
) -> list[dict]:
    with connect(db_path) as conn:
        if task_id:
            rows = conn.execute(
                """
                SELECT * FROM events WHERE task_id = ?
                ORDER BY id DESC LIMIT ?
                """,
                (task_id, limit),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM events ORDER BY id DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [dict(r) for r in rows]


def graph_show(task_id: str, db_path: Optional[str] = None) -> dict:
    task = get_task(task_id, db_path)
    if not task:
        raise KeyError(f"task not found: {task_id}")
    deps = parse_depends_on(task.get("depends_on_json"))
    dep_info = []
    with connect(db_path) as conn:
        for d in deps:
            row = conn.execute(
                "SELECT id, title, status FROM tasks WHERE id = ?", (d,)
            ).fetchone()
            if row:
                dep_info.append(dict(row))
            else:
                dep_info.append({"id": d, "title": None, "status": "missing"})
        # dependents: tasks that list this id in depends_on_json
        dependents = []
        for r in conn.execute("SELECT id, title, status, depends_on_json FROM tasks").fetchall():
            dlist = parse_depends_on(r["depends_on_json"])
            if task_id in dlist:
                dependents.append({"id": r["id"], "title": r["title"], "status": r["status"]})
    return {
        "task": {
            "id": task["id"],
            "title": task["title"],
            "status": task["status"],
            "priority": task["priority"],
            "depends_on": deps,
        },
        "dependencies": dep_info,
        "dependents": dependents,
        "ready": deps_satisfied(task, db_path=db_path) if task["status"] == "queued" else None,
    }


def _print_json(obj: Any) -> None:
    print(json.dumps(obj, indent=2, ensure_ascii=False, default=str))


def main(argv: Optional[list[str]] = None) -> int:
    """Minimal CLI for db.py (used by shell wrappers)."""
    argv = list(argv if argv is not None else sys.argv[1:])
    if not argv:
        print(
            "usage: db.py <init|create-task|list-tasks|get-task|set-status|pick-queued|"
            "list-ready|set-depends|add-depends|count-running|queue-stats|claim|"
            "create-run|finish-run|list-runs|emit|list-events|graph-show> ...",
            file=sys.stderr,
        )
        return 2

    cmd = argv[0]
    db_path = os.environ.get("AGENTBOX_V5_DB")

    try:
        if cmd == "init":
            path = init_db(db_path)
            print(str(path))
            return 0

        if cmd == "create-task":
            import argparse
            p = argparse.ArgumentParser()
            p.add_argument("--project", required=True)
            p.add_argument("--title", required=True)
            p.add_argument("--desc", default="")
            p.add_argument("--provider", default="")
            p.add_argument("--model", default="")
            p.add_argument("--priority", type=int, default=0)
            p.add_argument("--budget-tokens", type=int, default=0)
            p.add_argument("--budget-cost", type=float, default=0.0)
            p.add_argument("--approval-policy", default="auto")
            p.add_argument("--sandbox-mode", default="worktree")
            p.add_argument("--timeout", type=int, default=0)
            args = p.parse_args(argv[1:])
            task = create_task(
                project_id=args.project,
                title=args.title,
                description=args.desc,
                provider=args.provider,
                model=args.model,
                priority=args.priority,
                budget_tokens=args.budget_tokens,
                budget_cost=args.budget_cost,
                approval_policy=args.approval_policy,
                sandbox_mode=args.sandbox_mode,
                timeout_secs=args.timeout,
                db_path=db_path,
            )
            _print_json(task)
            return 0

        if cmd == "list-tasks":
            status = None
            if len(argv) > 1 and argv[1] == "--status" and len(argv) > 2:
                status = argv[2]
            _print_json(list_tasks(status=status, db_path=db_path))
            return 0

        if cmd == "get-task":
            if len(argv) < 2:
                print("get-task ID required", file=sys.stderr)
                return 2
            task = get_task(argv[1], db_path)
            if not task:
                print(f"not found: {argv[1]}", file=sys.stderr)
                return 1
            _print_json(task)
            return 0

        if cmd == "set-status":
            if len(argv) < 3:
                print("set-status ID STATUS", file=sys.stderr)
                return 2
            task = set_task_status(argv[1], argv[2], db_path)
            _print_json(task)
            return 0

        if cmd == "pick-queued":
            task = pick_queued_task(db_path)
            if not task:
                print("{}")
                return 0
            _print_json(task)
            return 0

        if cmd == "list-ready":
            limit = 50
            if "--limit" in argv:
                i = argv.index("--limit")
                limit = int(argv[i + 1]) if i + 1 < len(argv) else 50
            _print_json(list_ready_queued(limit=limit, db_path=db_path))
            return 0

        if cmd == "set-depends":
            if len(argv) < 2:
                print("set-depends TASK_ID [--on ID ...]", file=sys.stderr)
                return 2
            tid = argv[1]
            ons: list[str] = []
            i = 2
            while i < len(argv):
                if argv[i] == "--on" and i + 1 < len(argv):
                    ons.append(argv[i + 1])
                    i += 2
                else:
                    i += 1
            task = set_depends_on(tid, ons, db_path=db_path)
            _print_json(task)
            return 0

        if cmd == "add-depends":
            if len(argv) < 2:
                print("add-depends TASK_ID --on ID [--on ID2]", file=sys.stderr)
                return 2
            tid = argv[1]
            ons = []
            i = 2
            while i < len(argv):
                if argv[i] == "--on" and i + 1 < len(argv):
                    ons.append(argv[i + 1])
                    i += 2
                else:
                    i += 1
            if not ons:
                print("at least one --on required", file=sys.stderr)
                return 2
            task = add_depends_on(tid, ons, db_path=db_path)
            _print_json(task)
            return 0

        if cmd == "count-running":
            print(count_running(db_path))
            return 0

        if cmd == "queue-stats":
            _print_json(queue_stats(db_path))
            return 0

        if cmd == "claim":
            if len(argv) < 2:
                print("claim TASK_ID", file=sys.stderr)
                return 2
            task = claim_ready_task(argv[1], db_path=db_path)
            if not task:
                print("{}")
                return 0
            _print_json(task)
            return 0

        if cmd == "graph-show":
            if len(argv) < 2:
                print("graph-show TASK_ID", file=sys.stderr)
                return 2
            _print_json(graph_show(argv[1], db_path=db_path))
            return 0

        if cmd == "create-run":
            if len(argv) < 2:
                print("create-run TASK_ID [--worker W]", file=sys.stderr)
                return 2
            worker = ""
            if "--worker" in argv:
                i = argv.index("--worker")
                worker = argv[i + 1] if i + 1 < len(argv) else ""
            run = create_run(argv[1], worker_id=worker, db_path=db_path)
            _print_json(run)
            return 0

        if cmd == "finish-run":
            import argparse
            p = argparse.ArgumentParser()
            p.add_argument("run_id")
            p.add_argument("--status", default="completed")
            p.add_argument("--exit-code", type=int, default=0)
            p.add_argument("--error", default="")
            args = p.parse_args(argv[1:])
            run = finish_run(
                args.run_id,
                status=args.status,
                exit_code=args.exit_code,
                error=args.error,
                db_path=db_path,
            )
            _print_json(run)
            return 0

        if cmd == "list-runs":
            task_id = None
            if len(argv) > 1 and argv[1] == "--task" and len(argv) > 2:
                task_id = argv[2]
            _print_json(list_runs(task_id=task_id, db_path=db_path))
            return 0

        if cmd == "emit":
            import argparse
            p = argparse.ArgumentParser()
            p.add_argument("--kind", required=True)
            p.add_argument("--message", default="")
            p.add_argument("--task", default=None)
            p.add_argument("--run", default=None)
            args = p.parse_args(argv[1:])
            eid = emit_event(
                kind=args.kind,
                message=args.message,
                task_id=args.task,
                run_id=args.run,
                db_path=db_path,
            )
            print(eid)
            return 0

        if cmd == "list-events":
            import argparse
            p = argparse.ArgumentParser()
            p.add_argument("--task", default=None)
            p.add_argument("--limit", type=int, default=50)
            args = p.parse_args(argv[1:])
            _print_json(list_events(task_id=args.task, limit=args.limit, db_path=db_path))
            return 0

        print(f"unknown command: {cmd}", file=sys.stderr)
        return 2
    except Exception as e:
        print(f"error: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
