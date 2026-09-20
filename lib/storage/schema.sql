-- AgentBox v5 SQLite schema (beta3 — Policy, Budget & Risk Engine)
-- Statuses: created, planned, awaiting_approval, queued, scheduled, running,
--   paused, blocked, failed, completed, reviewing, awaiting_merge, merged,
--   rejected, cancelled, rolled_back, paused_budget

PRAGMA foreign_keys = ON;
PRAGMA journal_mode = WAL;

CREATE TABLE IF NOT EXISTS tasks (
    id              TEXT PRIMARY KEY,
    project_id      TEXT NOT NULL,
    title           TEXT NOT NULL,
    description     TEXT DEFAULT '',
    priority        INTEGER NOT NULL DEFAULT 0,
    status          TEXT NOT NULL DEFAULT 'created',
    created_at      TEXT NOT NULL,
    updated_at      TEXT NOT NULL,
    provider        TEXT DEFAULT '',
    model           TEXT DEFAULT '',
    budget_tokens   INTEGER DEFAULT 0,
    budget_cost     REAL DEFAULT 0.0,
    timeout_secs    INTEGER DEFAULT 0,
    approval_policy TEXT DEFAULT 'auto',
    sandbox_mode    TEXT DEFAULT 'worktree',
    current_stage   TEXT DEFAULT '',
    parent_task     TEXT DEFAULT '',
    depends_on_json TEXT NOT NULL DEFAULT '[]',
    meta_json       TEXT NOT NULL DEFAULT '{}',
    usage_tokens    INTEGER NOT NULL DEFAULT 0,
    usage_cost      REAL NOT NULL DEFAULT 0.0,
    usage_runtime_secs INTEGER NOT NULL DEFAULT 0,
    usage_retries   INTEGER NOT NULL DEFAULT 0,
    usage_files_changed INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS runs (
    id          TEXT PRIMARY KEY,
    task_id     TEXT NOT NULL,
    status      TEXT NOT NULL DEFAULT 'running',
    started_at  TEXT NOT NULL,
    finished_at TEXT,
    exit_code   INTEGER,
    worker_id   TEXT DEFAULT '',
    error       TEXT DEFAULT '',
    stats_json  TEXT DEFAULT '{}',
    FOREIGN KEY (task_id) REFERENCES tasks(id)
);

CREATE TABLE IF NOT EXISTS events (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    ts           TEXT NOT NULL,
    task_id      TEXT,
    run_id       TEXT,
    kind         TEXT NOT NULL,
    message      TEXT DEFAULT '',
    payload_json TEXT DEFAULT '{}'
);

-- beta1: agent registry (role / capabilities / provider / model)
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
);

CREATE TABLE IF NOT EXISTS approvals (
    id          TEXT PRIMARY KEY,
    task_id     TEXT NOT NULL,
    gate        TEXT NOT NULL,
    status      TEXT NOT NULL DEFAULT 'pending',
    reason      TEXT DEFAULT '',
    created_at  TEXT NOT NULL,
    resolved_at TEXT,
    FOREIGN KEY (task_id) REFERENCES tasks(id)
);

-- beta1: layered memory (user / project / agent / task)
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
);

CREATE INDEX IF NOT EXISTS idx_tasks_status ON tasks(status);
CREATE INDEX IF NOT EXISTS idx_tasks_created ON tasks(created_at);
CREATE INDEX IF NOT EXISTS idx_tasks_priority ON tasks(priority DESC, created_at ASC);
CREATE INDEX IF NOT EXISTS idx_runs_task ON runs(task_id);
CREATE INDEX IF NOT EXISTS idx_runs_status ON runs(status);
CREATE INDEX IF NOT EXISTS idx_events_task ON events(task_id);
CREATE INDEX IF NOT EXISTS idx_events_run ON events(run_id);
CREATE INDEX IF NOT EXISTS idx_events_ts ON events(ts);
CREATE INDEX IF NOT EXISTS idx_approvals_task ON approvals(task_id);
CREATE INDEX IF NOT EXISTS idx_approvals_status ON approvals(status);
CREATE INDEX IF NOT EXISTS idx_memories_scope ON memories(scope, scope_key);
CREATE INDEX IF NOT EXISTS idx_memories_updated ON memories(updated_at);
CREATE INDEX IF NOT EXISTS idx_memories_expires ON memories(expires_at);
CREATE INDEX IF NOT EXISTS idx_agents_status ON agents(status);

-- beta2: multi-agent handoffs
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
);

-- beta2: observability metrics
CREATE TABLE IF NOT EXISTS metrics (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    metric_name     TEXT NOT NULL,
    metric_value    REAL NOT NULL,
    labels_json     TEXT DEFAULT '{}',
    created_at      TEXT NOT NULL
);

-- beta2: per-agent run tracking
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
);

-- beta2: artifacts registry
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
);

CREATE INDEX IF NOT EXISTS idx_handoff_task ON agent_handoffs(task_id);
CREATE INDEX IF NOT EXISTS idx_metrics_name ON metrics(metric_name);
CREATE INDEX IF NOT EXISTS idx_agent_runs_task ON agent_runs(task_id);
CREATE INDEX IF NOT EXISTS idx_artifacts_task ON artifacts(task_id);
CREATE INDEX IF NOT EXISTS idx_handoff_status ON agent_handoffs(status);

-- beta3: Policy / Budget / Risk Engine
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
);

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
);

CREATE TABLE IF NOT EXISTS budget_usage (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    scope_type TEXT NOT NULL,
    scope_id TEXT,
    metric TEXT NOT NULL,
    value REAL NOT NULL,
    task_id TEXT,
    run_id TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

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
);

CREATE INDEX IF NOT EXISTS idx_policy_scope ON policies(scope_type, scope_id);
CREATE INDEX IF NOT EXISTS idx_budget_scope ON budgets(scope_type, scope_id);
CREATE INDEX IF NOT EXISTS idx_budget_usage_scope ON budget_usage(scope_type, scope_id, metric);
CREATE INDEX IF NOT EXISTS idx_risk_task ON risk_assessments(task_id);

-- rc1: Web Control Plane
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

CREATE INDEX IF NOT EXISTS idx_web_sessions_expiry
ON web_sessions(expires_at);

CREATE INDEX IF NOT EXISTS idx_api_audit_created
ON api_audit(created_at);

-- v5.1: Distributed workers
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


-- v5.3: Autonomous Planning & Workflow Intelligence
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


-- v5.5: Self-Improvement, Evaluation & Benchmarking
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
