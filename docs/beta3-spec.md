# AgentBox v5.0-beta3 — Policy, Budget & Risk Engine

**Środowisko docelowe:** AgentBox  
**SSH:** `100.123.66.15:22`  
**Użytkownik:** `box`  
**Hostname:** `cursor`  
**Root projektu:** `/workspace/agentbox-v5`  
**Poprzednia wersja:** `v5.0-beta2` — Observability + Multi-Agent Handoffs  
**Nowa wersja:** `v5.0-beta3`

> Ta wersja ma być wdrażana wyłącznie na serwerze AgentBox. Każdy skrypt wdrożeniowy musi uruchomić `agentbox-deploy-guard` przed dokonaniem zmian.

## 1. Cel beta3

Beta3 dodaje warstwę kontroli autonomii AgentBox:

```text
Task / Handoff / Agent Run
          │
          ▼
      Risk Engine
          │
     ┌────┼────┐
     ▼    ▼    ▼
 Policy Budget Approval
     │    │    │
     └────┼────┘
          ▼
      ALLOW / DENY
      REQUIRE APPROVAL
      PAUSE / BLOCK
```

Główne komponenty:

- Policy Engine
- Budget Engine
- Risk Engine
- Approval Routing
- Permission Profiles
- Policy Audit Trail
- Budget Accounting
- Risk Scoring
- Runtime Enforcement
- CLI do zarządzania politykami i budżetami
- integracja z beta2: handoffs, telemetry, events, artifacts, agent registry

## 2. Nowe statusy

```text
awaiting_policy
policy_denied
awaiting_approval
approved
budget_paused
budget_exceeded
risk_blocked
security_blocked
ready
running
completed
failed
cancelled
```

Dla handoffów:

```text
pending
policy_check
approved
denied
running
completed
failed
blocked
```

## 3. Risk Engine

Skala:

```text
0–19   LOW
20–39  MODERATE
40–59  ELEVATED
60–79  HIGH
80–100 CRITICAL
```

Przykładowe ryzyko:

| Operacja | Punkty |
|---|---:|
| read file | 0 |
| modify workspace file | 5 |
| create file | 5 |
| delete file | 15 |
| install dependency | 20 |
| network request | 15 |
| modify lockfile | 10 |
| database migration | 35 |
| docker build | 20 |
| docker run | 25 |
| privileged container | 80 |
| modify `/etc` | 80 |
| access secret-like file | 70 |
| `git commit` | 10 |
| `git merge` | 30 |
| `git push` | 50 |
| force push | 100 |
| production deploy | 90 |

Decyzje:

```text
LOW        -> auto allow
MODERATE   -> allow + audit
ELEVATED   -> policy dependent
HIGH       -> human approval
CRITICAL   -> deny by default
```

## 4. Policy Engine

Plik:

```text
~/.config/agentbox-v5/policies.ini
```

Przykład:

```ini
[filesystem]
workspace_only = true
allow_delete = approval
allow_system_write = false
secret_files = deny

[git]
commit = allow
merge = approval
push = approval
force_push = deny
delete_branch = approval

[network]
outbound = allow
unknown_domains = approval

[packages]
install = approval
remove = approval

[docker]
enabled = true
privileged = deny
host_network = deny
bind_system_paths = deny

[database]
migration = approval
destructive_migration = deny

[deployment]
production = approval
staging = allow

[approvals]
risk_threshold = 60
critical_threshold = 80
```

Akcje polityki:

```text
allow
deny
approval
audit
```

## 5. Budget Engine

Poziomy:

```text
Global
Project
Task
Agent
```

Limity:

```text
max_runtime_seconds
max_agent_runs
max_parallel_agents
max_retries
max_tokens
max_cost_usd
max_files_changed
max_lines_added
max_lines_removed
max_handoffs
max_network_requests
```

Przykład:

```ini
[global]
max_parallel_agents = 4
daily_cost_usd = 20
monthly_cost_usd = 200

[task_defaults]
max_runtime_seconds = 3600
max_agent_runs = 12
max_retries = 2
max_tokens = 150000
max_cost_usd = 5
max_files_changed = 50
max_handoffs = 10
```

Po przekroczeniu:

```text
running
↓
budget_exceeded
↓
paused
↓
human decision
```

## 6. Migracja SQLite

```sql
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

CREATE TABLE IF NOT EXISTS approvals (
    id TEXT PRIMARY KEY,
    task_id TEXT,
    run_id TEXT,
    handoff_id TEXT,
    approval_type TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending',
    requested_by TEXT,
    reason TEXT,
    risk_score INTEGER,
    payload_json TEXT,
    requested_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    decided_at TEXT,
    decided_by TEXT
);

CREATE INDEX IF NOT EXISTS idx_policy_scope
ON policies(scope_type, scope_id);

CREATE INDEX IF NOT EXISTS idx_budget_scope
ON budgets(scope_type, scope_id);

CREATE INDEX IF NOT EXISTS idx_budget_usage_scope
ON budget_usage(scope_type, scope_id, metric);

CREATE INDEX IF NOT EXISTS idx_risk_task
ON risk_assessments(task_id);

CREATE INDEX IF NOT EXISTS idx_approval_status
ON approvals(status);
```

## 7. Nowe moduły Python

```text
agentbox/
├── policy.py
├── budget.py
├── risk.py
├── approvals.py
├── permissions.py
└── enforcement.py
```

## 8. Policy API

```python
evaluate_policy(
    action: str,
    resource: str | None,
    task_id: str | None,
    agent_name: str | None,
    context: dict,
) -> PolicyDecision
```

Wynik:

```python
{
    "decision": "allow|deny|approval",
    "reason": "...",
    "policy_id": "...",
    "risk_score": 0,
}
```

## 9. Risk API

```python
assess_risk(
    action,
    resource=None,
    context=None,
) -> RiskAssessment
```

## 10. Budget API

```python
check_budget(scope_type, scope_id, metric, requested_value)
record_usage(...)
remaining_budget(...)
budget_summary(...)
```

Budżet sprawdzaj **przed** kosztowną operacją.

## 11. Enforcement Engine

```text
Agent Action
    │
    ▼
Risk Assessment
    │
    ▼
Policy Evaluation
    │
    ▼
Budget Check
    │
    ├── DENY -> stop
    ├── APPROVAL -> approval queue
    └── ALLOW
          │
          ▼
       execute
          │
          ▼
    record usage
          │
          ▼
       audit event
```

Nowy moduł ma udostępniać:

```python
enforce_action(...)
```

## 12. Integracja z Multi-Agent Handoffs

Każdy handoff:

```text
Planner
  ↓
handoff request
  ↓
Risk Engine
  ↓
Policy Engine
  ↓
Budget Engine
  ↓
Agent Registry permission check
  ↓
create handoff
```

## 13. Permission Profiles

Agent Registry rozszerz o:

```text
read_files
write_files
delete_files
network
git_commit
git_merge
git_push
package_install
docker
database
deploy
delegate_to
```

## 14. Approval Queue

CLI:

```bash
agent5 approval list
agent5 approval show APR_ID
agent5 approval approve APR_ID
agent5 approval reject APR_ID --reason "..."
```

## 15. CLI beta3

```bash
agent5 policy list
agent5 policy show POLICY_ID
agent5 policy check ACTION
```

```bash
agent5 budget show
agent5 budget task TASK_ID
agent5 budget usage
```

```bash
agent5 risk check ACTION
agent5 risk history
```

```bash
agent5 approval list
agent5 approval approve APR_ID
agent5 approval reject APR_ID
```

Rozszerz:

```bash
agent5 status
```

## 16. Eventy

```text
policy.evaluated
policy.allowed
policy.denied
policy.approval_required

risk.assessed
risk.high
risk.critical

budget.checked
budget.consumed
budget.warning
budget.exceeded

approval.requested
approval.approved
approval.rejected

permission.allowed
permission.denied
```

## 17. Observability

Dodaj:

```text
agentbox_policy_checks_total
agentbox_policy_denies_total
agentbox_approvals_pending
agentbox_approvals_total
agentbox_risk_assessments_total
agentbox_risk_high_total
agentbox_budget_usage_tokens
agentbox_budget_usage_cost
agentbox_budget_exceeded_total
```

## 18. Zasady bezpieczeństwa

1. `git push --force` → DENY
2. zapis poza workspace → DENY
3. modyfikacja `/etc`, `/usr`, `/boot` → DENY
4. privileged Docker → DENY
5. dostęp do secret-like files → DENY lub approval
6. production deploy → approval
7. git push → approval
8. merge do `main/master` → approval
9. instalacja pakietu → approval
10. destructive DB migration → deny domyślnie

Nie zapisuj haseł, tokenów ani kluczy API w logach.

## 19. Deployment Guard

Każdy installer beta3:

```bash
#!/usr/bin/env bash
set -Eeuo pipefail

command -v agentbox-deploy-guard >/dev/null 2>&1 || {
    echo "[ERR] Deployment guard missing."
    exit 1
}

agentbox-deploy-guard

ROOT="/workspace/agentbox-v5"

[[ -d "$ROOT" ]] || {
    echo "[ERR] AgentBox v5 root missing: $ROOT"
    exit 1
}

cd "$ROOT"
```

## 20. Backup

```bash
STAMP="$(date +%Y%m%d-%H%M%S)"
BACKUP="$HOME/.local/share/agentbox-v5/backups/beta3-$STAMP"

mkdir -p "$BACKUP"

cp -a /workspace/agentbox-v5 "$BACKUP/project"

cp -a "$HOME/.local/share/agentbox-v5/agentbox.db"   "$BACKUP/agentbox.db" 2>/dev/null || true

cp -a "$HOME/.config/agentbox-v5"   "$BACKUP/config" 2>/dev/null || true
```

## 21. Testy beta3

```text
tests/
├── test_policy.py
├── test_budget.py
├── test_risk.py
├── test_approvals.py
├── test_permissions.py
├── test_enforcement.py
├── test_handoff_policy.py
└── test_budget_observability.py
```

## 22. Smoke test

### A

```text
Coder requests normal workspace write
→ risk LOW
→ policy ALLOW
→ action executes
→ event recorded
```

### B

```text
Coder requests git push
→ risk HIGH
→ policy APPROVAL
→ approval created
→ task pauses
→ human approves
→ action resumes
```

### C

```text
Agent requests force push
→ risk CRITICAL
→ policy DENY
→ no action
→ policy.denied event
```

### D

```text
Task exceeds max_handoffs
→ budget.exceeded
→ task budget_paused
```

### E

```text
Agent tries system write outside workspace
→ permission denied
→ security event
```

## 23. Acceptance Criteria

- [ ] migracja SQLite przechodzi bez utraty danych beta2
- [ ] istnieją wszystkie nowe tabele
- [ ] `agent5 policy list` działa
- [ ] `agent5 budget show` działa
- [ ] `agent5 risk check` działa
- [ ] `agent5 approval list` działa
- [ ] handoff przechodzi przez policy/budget/risk
- [ ] denied operation nie jest wykonywana
- [ ] approval operation jest zatrzymywana
- [ ] approved operation może zostać wznowiona
- [ ] budget exceeded zatrzymuje task
- [ ] risk score zapisuje się w SQLite
- [ ] decyzje trafiają do event store
- [ ] telemetry beta2 zawiera metryki beta3
- [ ] daemon działa po migracji
- [ ] self-test kończy się PASS
- [ ] istnieje rollback path

## 24. Self-test

```bash
agent5 selftest
```

Docelowo:

```text
AgentBox v5.0-beta3

[OK] database
[OK] migrations
[OK] daemon
[OK] scheduler
[OK] agent registry
[OK] memory
[OK] context builder
[OK] handoffs
[OK] observability
[OK] policy engine
[OK] budget engine
[OK] risk engine
[OK] permissions
[OK] approval queue
[OK] enforcement engine
[OK] artifacts
[OK] event store

RESULT: PASS
```

## 25. Deployment sequence

```bash
ssh box@100.123.66.15 -p 22
```

```bash
agentbox-deploy-guard
cd /workspace/agentbox-v5
agent5 daemon status
agent5 daemon stop
```

Wdróż beta3, uruchom testy, a potem:

```bash
agent5 daemon start
agent5 daemon status
agent5 selftest
agent5 status
```

Dopiero po pełnym PASS uznaj beta3 za aktywną.

## 26. Architektura po beta3

```text
                          AgentBox v5
                              │
                    ┌─────────┴─────────┐
                    │                   │
               Control Plane       Observability
                    │                   │
               Task Manager             ├── Events
                    │                   ├── Metrics
                    ▼                   ├── Timeline
                 Scheduler              └── Health
                    │
             ┌──────┼──────┐
             │      │      │
             ▼      ▼      ▼
          Agents  Handoffs Queue
             │
             ▼
        Enforcement Layer
             │
     ┌───────┼────────┐
     ▼       ▼        ▼
  Policy   Budget    Risk
     │       │        │
     └───────┼────────┘
             ▼
       Approval Engine
             │
      ┌──────┴──────┐
      ▼             ▼
    ALLOW          DENY
      │
      ▼
 Sandbox / Worktree
      │
      ▼
 Provider / Tools
```

## 27. Następny etap

Po beta3:

### `v5.0-rc1 — REST API + WebSocket + Web Dashboard`

Zakres:

```text
FastAPI control plane
REST API
WebSocket event stream
Dashboard
Tasks
Agents
Handoffs
Approvals
Budgets
Policies
Risk
Artifacts
Memory
Metrics
Logs
Providers
Projects
Settings
```

Planowany adres przez Tailscale:

```text
http://100.123.66.15:8787
```

Dostęp powinien być ograniczony do Tailscale / autoryzowanej warstwy kontrolnej.

---

## Standard kolejnych wydań

Każda kolejna wersja AgentBox ma być przekazywana jako `.md` i zawierać:

1. wersję i zakres,
2. architekturę,
3. migrację,
4. moduły,
5. API,
6. CLI,
7. deployment guard,
8. backup,
9. testy,
10. smoke test,
11. acceptance criteria,
12. rollback,
13. kolejny etap roadmapy.
