#!/usr/bin/env python3
"""Versioned migrations framework — does not break existing schema."""
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path
from typing import Any, Callable, Optional

_HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(_HERE.parent))

from ops import SCHEMA_VERSION  # noqa: E402
from ops.paths import acquire_lock, load_ini, release_lock  # noqa: E402
from storage import db as dbmod  # noqa: E402

MigrationFn = Callable[[Any], None]


def ensure_migrations_table(conn) -> None:
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


def ensure_runtime_processes(conn) -> None:
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


def _checksum(name: str, version: int) -> str:
    return hashlib.sha256(f"{version}:{name}".encode()).hexdigest()[:16]


# ---- migration definitions (idempotent) ----

def mig_0005_stable_hardening(conn) -> None:
    """Stable: migrations table already created; runtime_processes; interrupted statuses via raw updates ok."""
    ensure_runtime_processes(conn)
    # optional columns on artifacts for integrity
    cols = {r[1] for r in conn.execute("PRAGMA table_info(artifacts)").fetchall()}
    for col, decl in [
        ("sha256", "TEXT"),
        ("size", "INTEGER"),
        ("mime", "TEXT"),
        ("pinned", "INTEGER NOT NULL DEFAULT 0"),
    ]:
        if col not in cols:
            conn.execute(f"ALTER TABLE artifacts ADD COLUMN {col} {decl}")



def mig_0006_distributed_workers(conn) -> None:
    """v5.1: workers registry, sessions, assignments, metrics, events, enrollment_tokens."""
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS workers (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            hostname TEXT,
            tailscale_ip TEXT,
            platform TEXT,
            architecture TEXT,
            version TEXT,
            status TEXT NOT NULL DEFAULT 'offline',
            capabilities_json TEXT,
            labels_json TEXT,
            max_parallel_tasks INTEGER NOT NULL DEFAULT 1,
            current_load INTEGER NOT NULL DEFAULT 0,
            last_heartbeat TEXT,
            enrolled_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            quarantined INTEGER NOT NULL DEFAULT 0,
            quarantine_reason TEXT
        );
        CREATE TABLE IF NOT EXISTS worker_sessions (
            id TEXT PRIMARY KEY,
            worker_id TEXT NOT NULL,
            token_hash TEXT NOT NULL,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            expires_at TEXT,
            revoked_at TEXT,
            FOREIGN KEY(worker_id) REFERENCES workers(id) ON DELETE CASCADE
        );
        CREATE TABLE IF NOT EXISTS worker_assignments (
            id TEXT PRIMARY KEY,
            worker_id TEXT NOT NULL,
            task_id TEXT NOT NULL,
            run_id TEXT,
            status TEXT NOT NULL DEFAULT 'assigned',
            assigned_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            started_at TEXT,
            finished_at TEXT,
            lease_seconds INTEGER NOT NULL DEFAULT 60,
            payload_json TEXT DEFAULT '{}',
            result_json TEXT,
            error TEXT,
            FOREIGN KEY(worker_id) REFERENCES workers(id)
        );
        CREATE TABLE IF NOT EXISTS worker_metrics (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            worker_id TEXT NOT NULL,
            cpu_percent REAL,
            memory_percent REAL,
            disk_percent REAL,
            load1 REAL,
            active_tasks INTEGER,
            metadata_json TEXT,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(worker_id) REFERENCES workers(id) ON DELETE CASCADE
        );
        CREATE TABLE IF NOT EXISTS worker_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            worker_id TEXT NOT NULL,
            event_type TEXT NOT NULL,
            payload_json TEXT,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(worker_id) REFERENCES workers(id) ON DELETE CASCADE
        );
        CREATE TABLE IF NOT EXISTS enrollment_tokens (
            id TEXT PRIMARY KEY,
            token_hash TEXT NOT NULL,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            expires_at TEXT NOT NULL,
            used_at TEXT,
            used_by_worker_id TEXT
        );
        CREATE INDEX IF NOT EXISTS idx_workers_status ON workers(status);
        CREATE INDEX IF NOT EXISTS idx_worker_assignments_worker ON worker_assignments(worker_id);
        CREATE INDEX IF NOT EXISTS idx_worker_metrics_worker ON worker_metrics(worker_id);
        CREATE INDEX IF NOT EXISTS idx_worker_events_worker ON worker_events(worker_id);
        CREATE INDEX IF NOT EXISTS idx_enrollment_tokens_hash ON enrollment_tokens(token_hash);
        """
    )
    # additive columns if older partial table exists
    cols = {r[1] for r in conn.execute("PRAGMA table_info(worker_assignments)").fetchall()}
    for col, decl in [
        ("lease_seconds", "INTEGER NOT NULL DEFAULT 60"),
        ("payload_json", "TEXT DEFAULT '{}'"),
        ("result_json", "TEXT"),
        ("error", "TEXT"),
    ]:
        if cols and col not in cols:
            conn.execute(f"ALTER TABLE worker_assignments ADD COLUMN {col} {decl}")




def mig_0007_intelligence(conn) -> None:
    """v5.2: semantic index, vector embeddings/memories, model registry, experience, quality."""
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS semantic_indexes (
            id TEXT PRIMARY KEY,
            project_id TEXT NOT NULL,
            embedding_model TEXT NOT NULL,
            embedding_version TEXT,
            index_version INTEGER NOT NULL DEFAULT 1,
            status TEXT NOT NULL DEFAULT 'new',
            last_commit TEXT,
            files_count INTEGER NOT NULL DEFAULT 0,
            chunks_count INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS semantic_chunks (
            id TEXT PRIMARY KEY,
            project_id TEXT NOT NULL,
            file_path TEXT NOT NULL,
            symbol TEXT,
            symbol_type TEXT,
            language TEXT,
            start_line INTEGER,
            end_line INTEGER,
            content_hash TEXT NOT NULL,
            content TEXT,
            vector_id TEXT,
            metadata_json TEXT,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS vector_embeddings (
            id TEXT PRIMARY KEY,
            namespace TEXT NOT NULL DEFAULT 'default',
            ref_type TEXT NOT NULL,
            ref_id TEXT NOT NULL,
            project_id TEXT,
            embedding_model TEXT NOT NULL,
            embedding_version TEXT,
            dim INTEGER NOT NULL,
            vector_blob BLOB NOT NULL,
            text_preview TEXT,
            meta_json TEXT NOT NULL DEFAULT '{}',
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS vector_memories (
            id TEXT PRIMARY KEY,
            scope_type TEXT NOT NULL,
            scope_id TEXT,
            memory_type TEXT NOT NULL,
            content TEXT NOT NULL,
            summary TEXT,
            vector_id TEXT,
            importance REAL NOT NULL DEFAULT 0.5,
            confidence REAL NOT NULL DEFAULT 0.5,
            provenance_json TEXT,
            usage_count INTEGER NOT NULL DEFAULT 0,
            last_used_at TEXT,
            pinned INTEGER NOT NULL DEFAULT 0,
            shareable INTEGER NOT NULL DEFAULT 0,
            project_id TEXT,
            content_hash TEXT,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS experience (
            id TEXT PRIMARY KEY,
            task_id TEXT,
            task_type TEXT,
            provider TEXT,
            model TEXT,
            agent TEXT,
            outcome TEXT,
            runtime_seconds REAL,
            cost REAL,
            retries INTEGER DEFAULT 0,
            review_pass INTEGER,
            notes TEXT,
            meta_json TEXT DEFAULT '{}',
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS model_registry (
            id TEXT PRIMARY KEY,
            provider TEXT NOT NULL,
            model TEXT NOT NULL,
            capabilities_json TEXT,
            context_window INTEGER,
            local INTEGER NOT NULL DEFAULT 0,
            enabled INTEGER NOT NULL DEFAULT 1,
            metadata_json TEXT,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS model_quality (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            provider TEXT NOT NULL,
            model TEXT NOT NULL,
            agent_name TEXT,
            task_type TEXT,
            success INTEGER,
            review_pass INTEGER,
            runtime_seconds REAL,
            cost REAL,
            retries INTEGER,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS routing_decisions (
            id TEXT PRIMARY KEY,
            task_id TEXT,
            agent_name TEXT,
            provider TEXT NOT NULL,
            model TEXT NOT NULL,
            score REAL,
            reason_json TEXT,
            fallback_json TEXT,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        CREATE INDEX IF NOT EXISTS idx_sem_chunks_project ON semantic_chunks(project_id);
        CREATE INDEX IF NOT EXISTS idx_vec_ns ON vector_embeddings(namespace);
        CREATE INDEX IF NOT EXISTS idx_vmem_scope ON vector_memories(scope_type, scope_id);
        CREATE INDEX IF NOT EXISTS idx_experience_type ON experience(task_type);
        """
    )




def mig_0008_planning(conn) -> None:
    """v5.3: goals, plans, plan_nodes, plan_revisions, reflections, workflow_runs."""
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS goals (
            id TEXT PRIMARY KEY,
            project_id TEXT,
            title TEXT NOT NULL,
            description TEXT DEFAULT '',
            status TEXT NOT NULL DEFAULT 'created',
            priority INTEGER NOT NULL DEFAULT 100,
            success_criteria_json TEXT DEFAULT '[]',
            constraints_json TEXT DEFAULT '{}',
            budget_id TEXT,
            risk_profile TEXT DEFAULT 'MEDIUM',
            approval_policy TEXT DEFAULT 'plan',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            completed_at TEXT
        );
        CREATE TABLE IF NOT EXISTS plans (
            id TEXT PRIMARY KEY,
            goal_id TEXT NOT NULL,
            version INTEGER NOT NULL DEFAULT 1,
            status TEXT NOT NULL DEFAULT 'draft',
            summary TEXT DEFAULT '',
            graph_json TEXT NOT NULL DEFAULT '{}',
            estimated_cost REAL DEFAULT 0,
            estimated_runtime_seconds REAL DEFAULT 0,
            risk_summary_json TEXT DEFAULT '{}',
            approval_points_json TEXT DEFAULT '[]',
            quality_score REAL DEFAULT 0,
            supersedes_plan_id TEXT,
            workflow_template TEXT DEFAULT '',
            intelligence_notes_json TEXT DEFAULT '{}',
            created_at TEXT NOT NULL,
            FOREIGN KEY (goal_id) REFERENCES goals(id)
        );
        CREATE TABLE IF NOT EXISTS plan_nodes (
            id TEXT PRIMARY KEY,
            plan_id TEXT NOT NULL,
            goal_id TEXT,
            title TEXT NOT NULL,
            description TEXT DEFAULT '',
            node_type TEXT DEFAULT 'stage',
            status TEXT DEFAULT 'pending',
            assigned_agent TEXT DEFAULT '',
            dependencies_json TEXT DEFAULT '[]',
            required_capabilities_json TEXT DEFAULT '[]',
            estimated_runtime REAL DEFAULT 60,
            estimated_cost REAL DEFAULT 0.05,
            risk TEXT DEFAULT 'MEDIUM',
            parallel_safe INTEGER DEFAULT 0,
            critical INTEGER DEFAULT 1,
            order_index INTEGER DEFAULT 0,
            meta_json TEXT DEFAULT '{}',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            FOREIGN KEY (plan_id) REFERENCES plans(id)
        );
        CREATE TABLE IF NOT EXISTS plan_revisions (
            id TEXT PRIMARY KEY,
            plan_id TEXT NOT NULL,
            goal_id TEXT,
            new_plan_id TEXT,
            reason TEXT DEFAULT '',
            changes_json TEXT DEFAULT '{}',
            created_at TEXT NOT NULL,
            FOREIGN KEY (plan_id) REFERENCES plans(id)
        );
        CREATE TABLE IF NOT EXISTS reflections (
            id TEXT PRIMARY KEY,
            goal_id TEXT NOT NULL,
            task_id TEXT,
            run_id TEXT,
            plan_id TEXT,
            decision TEXT NOT NULL,
            confidence REAL DEFAULT 0.7,
            reason TEXT DEFAULT '',
            proposed_actions_json TEXT DEFAULT '[]',
            created_at TEXT NOT NULL,
            FOREIGN KEY (goal_id) REFERENCES goals(id)
        );
        CREATE TABLE IF NOT EXISTS workflow_runs (
            id TEXT PRIMARY KEY,
            template_name TEXT NOT NULL,
            goal_id TEXT,
            plan_id TEXT,
            status TEXT DEFAULT 'running',
            meta_json TEXT DEFAULT '{}',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_goals_status ON goals(status);
        CREATE INDEX IF NOT EXISTS idx_plans_goal ON plans(goal_id);
        CREATE INDEX IF NOT EXISTS idx_plan_nodes_plan ON plan_nodes(plan_id);
        CREATE INDEX IF NOT EXISTS idx_reflections_goal ON reflections(goal_id);
        CREATE INDEX IF NOT EXISTS idx_workflow_runs_goal ON workflow_runs(goal_id);
        """
    )



def mig_0009_tools(conn) -> None:
    """v5.4: tools registry, versions, calls, outcomes, permissions, mcp, reliability."""
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS tools (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            display_name TEXT,
            category TEXT NOT NULL,
            provider TEXT DEFAULT 'builtin',
            version TEXT DEFAULT '1.0.0',
            enabled INTEGER NOT NULL DEFAULT 1,
            execution_mode TEXT NOT NULL DEFAULT 'local',
            capabilities_json TEXT NOT NULL DEFAULT '[]',
            permissions_json TEXT DEFAULT '[]',
            risk_level TEXT DEFAULT 'LOW',
            cost_profile_json TEXT DEFAULT '{}',
            timeout_seconds INTEGER DEFAULT 60,
            retry_policy_json TEXT DEFAULT '{}',
            health_status TEXT DEFAULT 'unknown',
            worker_requirements_json TEXT DEFAULT '{}',
            input_schema_json TEXT DEFAULT '{}',
            output_schema_json TEXT DEFAULT '{}',
            manifest_json TEXT DEFAULT '{}',
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS tool_versions (
            id TEXT PRIMARY KEY,
            tool_id TEXT NOT NULL,
            version TEXT NOT NULL,
            changelog TEXT DEFAULT '',
            input_schema_json TEXT DEFAULT '{}',
            output_schema_json TEXT DEFAULT '{}',
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(tool_id) REFERENCES tools(id)
        );
        CREATE TABLE IF NOT EXISTS tool_calls (
            id TEXT PRIMARY KEY,
            tool_id TEXT NOT NULL,
            task_id TEXT,
            run_id TEXT,
            agent_name TEXT,
            worker_id TEXT,
            status TEXT NOT NULL DEFAULT 'pending',
            input_json TEXT DEFAULT '{}',
            output_json TEXT DEFAULT '{}',
            input_hash TEXT,
            output_hash TEXT,
            exit_code INTEGER,
            duration_ms INTEGER,
            risk_score INTEGER,
            risk_level TEXT,
            cost REAL DEFAULT 0,
            decision TEXT,
            approval_id TEXT,
            error TEXT,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            finished_at TEXT,
            FOREIGN KEY(tool_id) REFERENCES tools(id)
        );
        CREATE TABLE IF NOT EXISTS tool_outcomes (
            id TEXT PRIMARY KEY,
            tool_id TEXT NOT NULL,
            call_id TEXT,
            capability TEXT,
            task_type TEXT DEFAULT '',
            input_class TEXT DEFAULT '',
            success INTEGER NOT NULL DEFAULT 0,
            failure_type TEXT,
            latency_ms INTEGER,
            worker_id TEXT,
            provider TEXT,
            meta_json TEXT DEFAULT '{}',
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(tool_id) REFERENCES tools(id)
        );
        CREATE TABLE IF NOT EXISTS tool_permissions (
            id TEXT PRIMARY KEY,
            agent_name TEXT NOT NULL,
            tool_id TEXT,
            capability TEXT,
            allowed INTEGER NOT NULL DEFAULT 1,
            requires_approval INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS mcp_servers (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            transport TEXT NOT NULL DEFAULT 'stdio',
            endpoint TEXT,
            command TEXT,
            enabled INTEGER NOT NULL DEFAULT 1,
            auth_mode TEXT DEFAULT 'none',
            trust_level TEXT DEFAULT 'standard',
            health_status TEXT DEFAULT 'unknown',
            capabilities_json TEXT DEFAULT '[]',
            metadata_json TEXT DEFAULT '{}',
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS tool_reliability (
            tool_id TEXT PRIMARY KEY,
            success_count INTEGER NOT NULL DEFAULT 0,
            failure_count INTEGER NOT NULL DEFAULT 0,
            timeout_count INTEGER NOT NULL DEFAULT 0,
            validation_failure_count INTEGER NOT NULL DEFAULT 0,
            retry_count INTEGER NOT NULL DEFAULT 0,
            reliability_score REAL NOT NULL DEFAULT 50,
            avg_latency_ms REAL,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(tool_id) REFERENCES tools(id)
        );
        CREATE INDEX IF NOT EXISTS idx_tools_category ON tools(category);
        CREATE INDEX IF NOT EXISTS idx_tool_calls_tool ON tool_calls(tool_id);
        CREATE INDEX IF NOT EXISTS idx_tool_outcomes_tool ON tool_outcomes(tool_id);
        """
    )



def mig_0010_evaluation(conn) -> None:
    """v5.5: evaluation harness, baselines, proposals, prompt/workflow versions."""
    from evaluation import store
    store.ensure_schema(conn)




def mig_0011_ops_autopilot(conn) -> None:
    """v5.6: ops autopilot playbooks, remediation, drift, maintenance plans."""
    from ops_autopilot import store
    store.ensure_schema(conn)



def mig_0012_pending_decisions(conn) -> None:
    """v5.6.3: pending user decisions list (dashboard "Czeka na Macieja")."""
    from ops import pending
    pending.ensure_schema(conn)


MIGRATIONS: list[tuple[int, str, MigrationFn]] = [
    (5, "stable_hardening", mig_0005_stable_hardening),
    (6, "distributed_workers", mig_0006_distributed_workers),
    (7, "intelligence", mig_0007_intelligence),
    (8, "planning", mig_0008_planning),
    (9, "tools", mig_0009_tools),
    (10, "evaluation", mig_0010_evaluation),
    (11, "ops_autopilot", mig_0011_ops_autopilot),
    (12, "pending_decisions", mig_0012_pending_decisions),
]


def applied_versions(conn) -> set[int]:
    ensure_migrations_table(conn)
    return {r[0] for r in conn.execute("SELECT version FROM migrations").fetchall()}


def status() -> dict[str, Any]:
    with dbmod.connect() as conn:
        ensure_migrations_table(conn)
        applied = sorted(applied_versions(conn))
        pending = [v for v, _, _ in MIGRATIONS if v not in set(applied)]
    return {
        "schema_version_target": SCHEMA_VERSION,
        "applied": applied,
        "pending": pending,
        "migrations": [{"version": v, "name": n} for v, n, _ in MIGRATIONS],
    }


def run(backup_first: bool = True) -> dict[str, Any]:
    cfg = load_ini("backup.ini")
    if backup_first and cfg.getboolean("backup", "before_migration", fallback=True):
        from ops.backups import create as backup_create
        b = backup_create(note="pre-migration", label="pre_migrate")
        pre = b["backup_id"]
    else:
        pre = None

    acquire_lock("migration", operation_id="migrate")
    applied_now = []
    try:
        with dbmod.connect() as conn:
            # keep legacy _migrate path intact
            dbmod._migrate(conn)
            ensure_migrations_table(conn)
            ensure_runtime_processes(conn)
            have = applied_versions(conn)
            for version, name, fn in MIGRATIONS:
                if version in have:
                    continue
                fn(conn)
                cs = _checksum(name, version)
                conn.execute(
                    "INSERT INTO migrations (version, name, applied_at, checksum) VALUES (?,?,?,?)",
                    (version, name, dbmod.utc_now(), cs),
                )
                applied_now.append({"version": version, "name": name, "checksum": cs})
            conn.commit()
            # verify
            rows = conn.execute("PRAGMA quick_check").fetchall()
            qc = rows[0][0] if rows else "fail"
        return {
            "ok": qc == "ok",
            "applied": applied_now,
            "pre_backup": pre,
            "quick_check": qc,
            "status": status(),
        }
    finally:
        release_lock("migration")


def main(argv: Optional[list[str]] = None) -> int:
    argv = list(argv or sys.argv[1:])
    cmd = argv[0] if argv else "status"
    if cmd == "status":
        print(json.dumps(status(), indent=2))
    elif cmd == "run":
        print(json.dumps(run(backup_first="--no-backup" not in argv), indent=2))
    else:
        print("usage: migrations.py status|run [--no-backup]", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
