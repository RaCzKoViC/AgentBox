# AgentBox v5.0-rc1 — REST API + WebSocket + Web Dashboard

**Środowisko docelowe:** AgentBox  
**SSH:** `100.123.66.15:22`  
**Użytkownik:** `box`  
**Hostname:** `cursor`  
**Root projektu:** `/workspace/agentbox-v5`  
**Poprzednia wersja:** `v5.0-beta3` — Policy, Budget & Risk Engine  
**Nowa wersja:** `v5.0-rc1`

> rc1 nie powinno być wdrażane, dopóki beta3 nie przejdzie pełnej walidacji. Ta specyfikacja opisuje kolejny etap i ma być wdrażana wyłącznie na serwerze AgentBox po przejściu deployment guard, backupu, migracji i testów.

---

# 1. Cel rc1

rc1 zamienia AgentBox z platformy głównie terminalowej w pełny **Control Plane** dostępny przez:

- CLI
- REST API
- WebSocket
- Web Dashboard
- Tailscale

Docelowa architektura:

```text
                      AgentBox v5 rc1
                           │
             ┌─────────────┼─────────────┐
             │             │             │
            CLI          REST          Web UI
             │             │             │
             └───────┬─────┴─────┬───────┘
                     │           │
                     ▼           ▼
               FastAPI API   WebSocket Hub
                     │           │
                     └─────┬─────┘
                           ▼
                    Control Plane
                           │
         ┌─────────────────┼─────────────────┐
         ▼                 ▼                 ▼
     Task Engine       Policy/Risk       Observability
         │                 │                 │
         ▼                 ▼                 ▼
     Scheduler         Approvals          Metrics
         │                                   │
         ▼                                   ▼
       Agents                              Timeline
         │
         ▼
      Handoffs
         │
         ▼
 Sandbox / Worktree / Providers / Artifacts / Memory
```

---

# 2. Główne komponenty rc1

```text
agentbox/
├── api/
│   ├── app.py
│   ├── deps.py
│   ├── auth.py
│   ├── errors.py
│   ├── schemas.py
│   ├── routes/
│   │   ├── health.py
│   │   ├── status.py
│   │   ├── tasks.py
│   │   ├── runs.py
│   │   ├── agents.py
│   │   ├── handoffs.py
│   │   ├── approvals.py
│   │   ├── policies.py
│   │   ├── budgets.py
│   │   ├── risk.py
│   │   ├── artifacts.py
│   │   ├── memory.py
│   │   ├── metrics.py
│   │   ├── logs.py
│   │   ├── providers.py
│   │   ├── projects.py
│   │   └── settings.py
│   └── websocket.py
│
├── web/
│   ├── static/
│   ├── templates/
│   └── manifest.json
│
├── control_plane.py
├── web_runtime.py
└── web_security.py
```

---

# 3. Technologia

Backend:

```text
Python 3
FastAPI
Uvicorn
Pydantic
SQLite
existing AgentBox stores/services
```

WebSocket:

```text
FastAPI WebSocket
event fan-out
task subscriptions
system subscriptions
```

Frontend:

Preferowany rc1:

```text
HTML
CSS
Vanilla JS lub lekki frontend
```

Nie budować od razu ciężkiego frameworka, jeśli nie jest potrzebny.

Cel rc1 to:
- stabilność,
- mały narzut,
- szybki dashboard,
- brak konieczności skomplikowanego build pipeline.

---

# 4. Dostęp sieciowy

Dashboard ma być wystawiany wyłącznie na warstwie Tailscale / kontrolowanej sieci.

Docelowo:

```text
http://100.123.66.15:8787
```

Rekomendowany bind:

```text
100.123.66.15:8787
```

Nie używać domyślnie:

```text
0.0.0.0:8787
```

chyba że policy/config jawnie na to pozwoli.

---

# 5. Konfiguracja Web Control Plane

Nowy plik:

```text
~/.config/agentbox-v5/web.ini
```

Przykład:

```ini
[server]
host = 100.123.66.15
port = 8787
workers = 1
reload = false

[security]
tailscale_only = true
require_auth = true
allow_remote_admin = true
session_timeout_minutes = 120

[websocket]
enabled = true
heartbeat_seconds = 20
max_connections = 32

[ui]
enabled = true
title = AgentBox
refresh_interval_seconds = 3
```

---

# 6. Authentication

rc1 musi mieć własną warstwę auth.

Minimalne opcje:

```text
local bearer token
session cookie
Tailscale source validation
```

Nie przechowywać haseł w plaintext.

Rekomendowany rc1:

```text
Tailscale restriction
+
random admin token
+
session cookie
```

Token:

```text
~/.config/agentbox-v5/secrets/admin.token
```

Uprawnienia pliku:

```bash
chmod 600 ~/.config/agentbox-v5/secrets/admin.token
```

Generowanie:

```bash
python3 - <<'PY'
import secrets
print(secrets.token_urlsafe(48))
PY
```

---

# 7. Role API

Minimum:

```text
viewer
operator
admin
```

### viewer

Może:
- status
- task list
- timeline
- logs
- metrics
- artifacts read

Nie może:
- approve
- reject
- merge
- change policy
- change budget

### operator

Może:
- tworzyć taski
- queue
- pause
- resume
- approve zwykłe approval requests
- zarządzać handoffami

### admin

Pełne:
- policy
- budget
- risk override
- settings
- provider config
- approvals wysokiego ryzyka

---

# 8. REST API — Health

## `GET /api/v1/health`

Przykład:

```json
{
  "status": "ok",
  "version": "5.0.0-rc1",
  "daemon": "running",
  "database": "ok",
  "scheduler": "running",
  "websocket": "running"
}
```

## `GET /api/v1/status`

```json
{
  "tasks": {
    "running": 3,
    "queued": 5,
    "blocked": 1
  },
  "agents": {
    "active": 4
  },
  "handoffs": {
    "pending": 2
  },
  "approvals": {
    "pending": 2
  },
  "system": {
    "cpu_percent": 31.4,
    "memory_percent": 46.2,
    "disk_percent": 29.1
  }
}
```

---

# 9. REST API — Tasks

## `GET /api/v1/tasks`

Filtry:

```text
status
project_id
provider
agent
priority
limit
offset
```

## `POST /api/v1/tasks`

```json
{
  "title": "RacOS kernel review",
  "description": "Review kernel memory subsystem",
  "project_id": "prj_123",
  "provider": "claude",
  "priority": 50
}
```

## `GET /api/v1/tasks/{task_id}`

## `POST /api/v1/tasks/{task_id}/queue`

## `POST /api/v1/tasks/{task_id}/pause`

## `POST /api/v1/tasks/{task_id}/resume`

## `POST /api/v1/tasks/{task_id}/cancel`

## `GET /api/v1/tasks/{task_id}/timeline`

## `GET /api/v1/tasks/{task_id}/artifacts`

---

# 10. REST API — Runs

```text
GET /api/v1/runs
GET /api/v1/runs/{run_id}
GET /api/v1/runs/{run_id}/logs
POST /api/v1/runs/{run_id}/cancel
```

---

# 11. REST API — Agents

```text
GET /api/v1/agents
GET /api/v1/agents/{agent_name}
GET /api/v1/agents/{agent_name}/status
GET /api/v1/agents/{agent_name}/runs
```

Opcjonalnie rc1:

```text
POST /api/v1/agents/{agent_name}/enable
POST /api/v1/agents/{agent_name}/disable
```

---

# 12. REST API — Handoffs

```text
GET /api/v1/handoffs
GET /api/v1/handoffs/{handoff_id}
POST /api/v1/handoffs
POST /api/v1/handoffs/{handoff_id}/approve
POST /api/v1/handoffs/{handoff_id}/reject
POST /api/v1/handoffs/{handoff_id}/retry
```

Payload:

```json
{
  "task_id": "tsk_123",
  "source_agent": "planner",
  "target_agent": "researcher",
  "reason": "Research dependency compatibility",
  "required": true
}
```

---

# 13. REST API — Approvals

```text
GET /api/v1/approvals
GET /api/v1/approvals/{approval_id}
POST /api/v1/approvals/{approval_id}/approve
POST /api/v1/approvals/{approval_id}/reject
```

Approve:

```json
{
  "comment": "Approved after diff review"
}
```

Reject:

```json
{
  "reason": "Risk too high"
}
```

---

# 14. REST API — Policies

```text
GET /api/v1/policies
GET /api/v1/policies/{policy_id}
POST /api/v1/policies
PATCH /api/v1/policies/{policy_id}
POST /api/v1/policies/{policy_id}/enable
POST /api/v1/policies/{policy_id}/disable
```

Policy mutations wymagają `admin`.

---

# 15. REST API — Budgets

```text
GET /api/v1/budgets
GET /api/v1/budgets/usage
GET /api/v1/budgets/task/{task_id}
POST /api/v1/budgets
PATCH /api/v1/budgets/{budget_id}
```

---

# 16. REST API — Risk

```text
GET /api/v1/risk
GET /api/v1/risk/history
GET /api/v1/risk/task/{task_id}
POST /api/v1/risk/check
```

Przykład:

```json
{
  "action": "git_push",
  "resource": "main",
  "task_id": "tsk_123"
}
```

Wynik:

```json
{
  "score": 72,
  "level": "HIGH",
  "decision": "approval",
  "reasons": [
    "push operation",
    "protected branch"
  ]
}
```

---

# 17. REST API — Artifacts

```text
GET /api/v1/artifacts
GET /api/v1/artifacts/{artifact_id}
GET /api/v1/artifacts/{artifact_id}/download
```

Dla bezpieczeństwa:
- blokować path traversal,
- nie wystawiać dowolnych ścieżek systemowych,
- artifact path musi należeć do AgentBox artifact root.

---

# 18. REST API — Memory

```text
GET /api/v1/memory
GET /api/v1/memory/search?q=...
GET /api/v1/memory/project/{project_id}
GET /api/v1/memory/task/{task_id}
```

Mutacje pamięci:
- tylko kontrolowane,
- zgodne z istniejącym Memory Engine,
- audytowane.

---

# 19. REST API — Metrics

```text
GET /api/v1/metrics
GET /api/v1/metrics/system
GET /api/v1/metrics/tasks
GET /api/v1/metrics/agents
GET /api/v1/metrics/providers
```

Opcjonalnie:

```text
GET /metrics
```

format Prometheus, jeśli rc1 ma exporter.

---

# 20. REST API — Logs

```text
GET /api/v1/logs
GET /api/v1/logs/daemon
GET /api/v1/logs/task/{task_id}
GET /api/v1/logs/run/{run_id}
```

Ograniczenia:
- limit linii,
- pagination,
- bez sekretów,
- sanitizacja ANSI.

---

# 21. REST API — Providers

```text
GET /api/v1/providers
GET /api/v1/providers/{provider}
GET /api/v1/providers/{provider}/health
```

Przykład:

```json
{
  "name": "claude",
  "available": true,
  "active_runs": 2,
  "errors_last_hour": 0
}
```

---

# 22. REST API — Projects

```text
GET /api/v1/projects
GET /api/v1/projects/{project_id}
POST /api/v1/projects
POST /api/v1/projects/refresh
```

Nie pozwalać API na dowolne skanowanie systemu poza dozwolonym rootem.

---

# 23. REST API — Settings

```text
GET /api/v1/settings
PATCH /api/v1/settings
```

Tylko `admin`.

Zmiany settings:
- audytowane,
- walidowane,
- bez sekretów w response.

---

# 24. WebSocket

Endpoint:

```text
/ws/events
```

Połączenie:
- auth required,
- heartbeat,
- timeout,
- limit klientów.

Subskrypcje:

```json
{
  "subscribe": [
    "system",
    "tasks",
    "agents",
    "handoffs",
    "approvals",
    "metrics"
  ]
}
```

---

# 25. WebSocket event format

```json
{
  "type": "task.status",
  "timestamp": "2026-09-19T22:30:00+02:00",
  "task_id": "tsk_123",
  "payload": {
    "status": "running",
    "stage": "coder"
  }
}
```

Inne:

```text
agent.started
agent.completed
handoff.created
handoff.completed
approval.requested
approval.approved
policy.denied
budget.exceeded
risk.high
artifact.created
daemon.health
system.metrics
```

---

# 26. WebSocket architecture

```text
SQLite/Event Store
      │
      ▼
Event Publisher
      │
      ▼
WebSocket Hub
  ┌───┼────┐
  ▼   ▼    ▼
 UI1 UI2  UI3
```

rc1 może używać polling bridge nad istniejącym Event Store.

Później stable może przejść na bardziej zaawansowany event bus.

---

# 27. Dashboard — ekran główny

Dashboard powinien pokazywać:

```text
AgentBox v5 rc1

Daemon       RUNNING
Scheduler    RUNNING
Agents       4 active
Tasks        3 running / 5 queued
Handoffs     2 pending
Approvals    2 pending

CPU          31%
RAM          7.2 / 15.6 GB
Disk         29%

Budget today $7.82 / $20
Policy denies 3
Risk HIGH     1
```

---

# 28. Dashboard — Tasks

Widok tabeli:

```text
ID
Title
Project
Status
Stage
Priority
Provider
Agent
Runtime
Budget
Risk
```

Funkcje:

```text
Open
Pause
Resume
Cancel
Queue
Inspect
Timeline
Artifacts
Logs
Approvals
```

---

# 29. Dashboard — Task Detail

Sekcje:

```text
Overview
Timeline
Agents
Handoffs
Approvals
Artifacts
Memory
Logs
Metrics
Risk
Budget
Diff
```

Przykład pipeline:

```text
Planner       DONE
Researcher    DONE
Architect     DONE
Coder         RUNNING
Tester        WAITING
Reviewer      WAITING
```

---

# 30. Dashboard — Agents

Karty:

```text
Planner
Architect
Coder
Tester
Reviewer
Debugger
Researcher
Security
Performance
Documentation
Release
```

Każda pokazuje:

```text
status
provider
model
active task
runtime
handoffs
errors
last activity
```

---

# 31. Dashboard — Handoffs

Tabela:

```text
From
To
Task
Reason
Required
Status
Created
Duration
```

Widok szczegółowy:
- source context,
- target context,
- artifacts,
- memory refs,
- result,
- events.

---

# 32. Dashboard — Approvals

To jeden z kluczowych ekranów.

Karta approval:

```text
Action:
git push main

Task:
RacOS networking refactor

Agent:
release

Risk:
HIGH 72/100

Policy:
approval required

Reason:
protected branch
```

Przyciski:

```text
Approve
Reject
Inspect task
Inspect diff
Inspect logs
```

---

# 33. Dashboard — Budgets

Wykresy / statystyki:

```text
daily cost
monthly cost
tokens
runtime
agent runs
handoffs
network requests
files changed
```

Poziomy:
- global
- project
- task
- agent.

---

# 34. Dashboard — Policies

Lista polityk:

```text
Category
Action
Effect
Scope
Enabled
```

Przykład:

```text
git | force_push | deny | global
git | push | approval | global
filesystem | system_write | deny | global
docker | privileged | deny | global
```

---

# 35. Dashboard — Risk

Widoki:

```text
Current HIGH/CRITICAL
Recent assessments
Risk by task
Risk by agent
Risk by action
```

---

# 36. Dashboard — Artifacts

Browser:

```text
Task
Agent
Type
File
Size
Created
```

Podgląd:
- Markdown
- JSON
- text logs
- patch/diff
- images później.

---

# 37. Dashboard — Memory

Widoki:

```text
Project Memory
Task Memory
Agent Memory
Run Memory
Search
```

W beta/rc nie edytować swobodnie pamięci bez audytu.

---

# 38. Dashboard — Logs

Live view przez WebSocket.

Filtry:

```text
daemon
task
run
agent
provider
level
```

Poziomy:

```text
DEBUG
INFO
WARN
ERROR
CRITICAL
```

---

# 39. Dashboard — Providers

Karty:

```text
Claude
Codex
Gemini
OpenCode
Ollama
```

Pola:

```text
available
health
active runs
last error
request count
error count
avg duration
```

Nie wyświetlać sekretów/API keys.

---

# 40. Dashboard — Projects

Widoki:

```text
Project list
Path
Type
Git branch
Dirty state
Tasks
Memory
Recent runs
```

---

# 41. Dashboard — Settings

Sekcje:

```text
Core
Scheduler
Web
Auth
Providers
Policies
Budgets
Memory
Observability
Sandbox
```

Mutacje tylko admin.

---

# 42. Frontend layout

Rekomendowany układ:

```text
┌─────────────────────────────────────────────┐
│ AgentBox        daemon ●      user: admin   │
├────────────┬────────────────────────────────┤
│ Dashboard  │                                │
│ Tasks      │                                │
│ Agents     │          Main View             │
│ Handoffs   │                                │
│ Approvals  │                                │
│ Budgets    │                                │
│ Policies   │                                │
│ Risk       │                                │
│ Artifacts  │                                │
│ Memory     │                                │
│ Metrics    │                                │
│ Logs       │                                │
│ Providers  │                                │
│ Projects   │                                │
│ Settings   │                                │
└────────────┴────────────────────────────────┘
```

---

# 43. Frontend wymagania

- responsywny
- desktop-first, ale działa na iPhone
- dark mode
- szybkie odświeżanie
- brak ciężkich animacji
- WebSocket live updates
- fallback polling
- bezpieczne renderowanie logów
- nie renderować niesanitizowanego HTML z agent outputs

---

# 44. API error model

Standard:

```json
{
  "error": {
    "code": "TASK_NOT_FOUND",
    "message": "Task does not exist",
    "details": {}
  }
}
```

HTTP:

```text
400 bad request
401 unauthenticated
403 denied
404 not found
409 conflict
422 validation
429 rate limit
500 internal
503 unavailable
```

---

# 45. Rate limiting

rc1 powinno ograniczać:

```text
login attempts
task creation
approval mutations
policy mutations
settings mutations
WebSocket reconnect spam
```

Przykład:

```text
GET read API: 120/min
POST task: 20/min
approval: 30/min
admin mutations: 30/min
login: 10/5min
```

---

# 46. CSRF / Session Security

Jeśli dashboard używa cookies:
- HttpOnly
- SameSite=Strict/Lax
- CSRF token dla mutacji
- secure flag jeśli HTTPS.

Jeśli bearer token:
- nie trzymać tokenu w localStorage jeśli można tego uniknąć,
- preferować pamięć sesji / bezpieczny cookie flow.

---

# 47. Tailscale-only validation

Request middleware powinien:
1. sprawdzić source address,
2. opcjonalnie sprawdzić Tailscale peer identity,
3. odrzucić publiczne źródła.

Jeśli walidacja peer identity nie jest dostępna, co najmniej bind tylko do Tailscale IP.

---

# 48. CORS

Domyślnie:

```text
same-origin only
```

Nie używać:

```text
Access-Control-Allow-Origin: *
```

dla panelu admina.

---

# 49. SQLite concurrency

Ponieważ dashboard i daemon będą współdzielić DB:

```text
PRAGMA journal_mode=WAL
PRAGMA foreign_keys=ON
busy_timeout
short transactions
```

Nie utrzymywać długich transakcji HTTP.

---

# 50. Migracja SQLite rc1

Dodaj tabele:

```sql
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
```

Nie zapisywać bearer tokenu plaintext — tylko hash.

---

# 51. Audit

Mutacje API muszą generować eventy:

```text
api.request
api.task_created
api.task_cancelled
api.approval_approved
api.approval_rejected
api.policy_changed
api.budget_changed
api.settings_changed
api.auth_failed
```

---

# 52. Integracja z Policy Engine

API nie może omijać beta3.

Przykład:

```text
POST /tasks/{id}/resume
       │
       ▼
auth
       │
       ▼
permission check
       │
       ▼
policy / risk / budget
       │
       ▼
control plane action
```

Dashboard to tylko kolejny klient Control Plane.

---

# 53. Web Runtime

Nowa komenda:

```bash
agent5 web start
agent5 web stop
agent5 web status
agent5 web restart
```

Bez systemd.

PID:

```text
~/.local/share/agentbox-v5/runtime/pids/agentbox-web.pid
```

Log:

```text
~/.local/share/agentbox-v5/logs/web.log
```

---

# 54. Proces bez systemd

`agent5 web start`:

```text
check existing PID
bind validation
config validation
auth secret validation
spawn uvicorn detached
write PID
health probe
```

`stop`:
- SIGTERM,
- timeout,
- cleanup PID.

---

# 55. CLI rc1

Dodaj:

```bash
agent5 web start
agent5 web stop
agent5 web restart
agent5 web status
agent5 web url
```

```bash
agent5 auth token rotate
agent5 auth sessions
agent5 auth revoke SESSION_ID
```

```bash
agent5 api health
```

Opcjonalnie:

```bash
agent5 dashboard
```

zwraca URL:

```text
http://100.123.66.15:8787
```

---

# 56. API OpenAPI

FastAPI automatycznie generuje:

```text
/openapi.json
/docs
/redoc
```

W rc1:
- `/docs` wyłączyć lub chronić auth,
- najlepiej tylko admin,
- produkcyjnie można całkowicie wyłączyć.

---

# 57. Testy backend

Dodaj:

```text
tests/
├── test_api_health.py
├── test_api_auth.py
├── test_api_tasks.py
├── test_api_handoffs.py
├── test_api_approvals.py
├── test_api_policy.py
├── test_api_budget.py
├── test_api_risk.py
├── test_api_artifacts.py
├── test_api_memory.py
├── test_websocket.py
├── test_web_security.py
└── test_web_runtime.py
```

---

# 58. Testy frontend

Minimum:
- dashboard loads,
- login,
- task list,
- task detail,
- approvals,
- live WebSocket update,
- reconnect fallback,
- mobile layout.

---

# 59. Smoke Test A — health

```text
start web
↓
GET /health
↓
200 OK
↓
daemon visible
↓
database ok
```

---

# 60. Smoke Test B — task lifecycle

```text
POST task
↓
task appears in SQLite
↓
task appears dashboard
↓
queue task
↓
WebSocket task.status
↓
dashboard updates live
```

---

# 61. Smoke Test C — approval

```text
high-risk action
↓
approval requested
↓
dashboard notification
↓
admin opens approval
↓
approve
↓
approval event
↓
task resumes
```

---

# 62. Smoke Test D — policy deny

```text
force push request
↓
risk critical
↓
policy deny
↓
API 403 / blocked
↓
dashboard shows deny
↓
audit event exists
```

---

# 63. Smoke Test E — WebSocket reconnect

```text
dashboard connected
↓
web process restart
↓
socket disconnect
↓
client reconnect
↓
resubscribe
↓
live updates continue
```

---

# 64. Acceptance Criteria

rc1 jest gotowe tylko jeśli:

- [ ] beta3 data preserved
- [ ] database migration succeeds
- [ ] web runtime starts without systemd
- [ ] web binds only to approved interface
- [ ] auth works
- [ ] unauthorized API rejected
- [ ] role permissions work
- [ ] task REST API works
- [ ] agent REST API works
- [ ] handoff REST API works
- [ ] approval flow works
- [ ] policy/budget/risk routes work
- [ ] artifacts route is path-safe
- [ ] memory route works
- [ ] logs sanitize secrets
- [ ] WebSocket live events work
- [ ] reconnect works
- [ ] dashboard works on desktop
- [ ] dashboard works on iPhone
- [ ] dashboard reflects daemon state
- [ ] beta3 enforcement cannot be bypassed
- [ ] API mutations are audited
- [ ] web self-test PASS
- [ ] global self-test PASS
- [ ] rollback path documented

---

# 65. Deployment Guard

Każdy rc1 deploy:

```bash
#!/usr/bin/env bash
set -Eeuo pipefail

command -v agentbox-deploy-guard >/dev/null 2>&1 || {
    echo "[ERR] deployment guard unavailable"
    exit 1
}

agentbox-deploy-guard

ROOT="/workspace/agentbox-v5"

[[ -d "$ROOT" ]] || {
    echo "[ERR] missing $ROOT"
    exit 1
}

cd "$ROOT"
```

---

# 66. Pre-deploy checks

```bash
agentbox-deploy-guard
cd /workspace/agentbox-v5

agent5 daemon status
agent5 selftest
agent5 status
```

Wymagane:
- beta3 PASS,
- brak pending migration,
- brak DB corruption,
- brak krytycznych runów podczas migracji.

---

# 67. Backup

Przed rc1:

```bash
STAMP="$(date +%Y%m%d-%H%M%S)"
BACKUP="$HOME/.local/share/agentbox-v5/backups/rc1-$STAMP"

mkdir -p "$BACKUP"

cp -a /workspace/agentbox-v5 \
  "$BACKUP/project"

cp -a "$HOME/.local/share/agentbox-v5/agentbox.db" \
  "$BACKUP/agentbox.db" 2>/dev/null || true

cp -a "$HOME/.config/agentbox-v5" \
  "$BACKUP/config" 2>/dev/null || true
```

Zapisać wersję:

```bash
python3 -m agentbox --version > "$BACKUP/version.txt" 2>&1 || true
```

---

# 68. Deployment Sequence

```bash
ssh box@100.123.66.15 -p 22
```

```bash
agentbox-deploy-guard
cd /workspace/agentbox-v5
```

Sprawdź:

```bash
agent5 selftest
```

Zatrzymaj:

```bash
agent5 web stop 2>/dev/null || true
agent5 daemon stop
```

Wdróż:
- kod,
- migracje,
- config,
- dependencies.

Następnie:

```bash
agent5 daemon start
agent5 daemon status
```

Potem:

```bash
agent5 web start
agent5 web status
agent5 web url
```

Na końcu:

```bash
agent5 selftest
agent5 status
```

---

# 69. Health probe

Po starcie:

```bash
curl -fsS http://100.123.66.15:8787/api/v1/health
```

Jeśli auth jest wymagany nawet dla health, użyć odpowiedniego mechanizmu token/session.

---

# 70. Rollback

W razie niepowodzenia:

```text
stop web
stop daemon
restore project backup
restore DB
restore config
start daemon
run selftest
```

Nie wykonywać downgrade migracji na żywej DB bez przygotowanej procedury.

Najbezpieczniej:
- backup pełnej DB przed migracją,
- restore całego pliku DB.

---

# 71. Web Dashboard security checklist

- [ ] Tailscale-only bind
- [ ] auth enabled
- [ ] admin token hashed
- [ ] sessions expire
- [ ] CSRF on cookie mutations
- [ ] same-origin CORS
- [ ] rate limiting
- [ ] no secret output
- [ ] no arbitrary file read
- [ ] no path traversal
- [ ] policy engine enforced
- [ ] audit trail enabled
- [ ] protected admin endpoints
- [ ] secure defaults

---

# 72. Dashboard navigation

```text
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

---

# 73. Live notification center

Dashboard powinien mieć notifications:

```text
Task failed
Approval requested
Budget exceeded
Risk HIGH
Policy denied
Provider unavailable
Handoff failed
Daemon degraded
```

Kliknięcie otwiera właściwy detail view.

---

# 74. Global search

rc1 może dodać:

```text
Search tasks
Search agents
Search projects
Search artifacts
Search memory
Search logs
```

Endpoint:

```text
GET /api/v1/search?q=...
```

Jeśli czas implementacji rc1 będzie zbyt duży, global search można przesunąć do stable.

---

# 75. Mobile / iPhone

Dashboard powinien działać na iPhone 15 Pro Max:

- responsywna nawigacja,
- boczne menu jako drawer,
- karty zamiast szerokich tabel,
- approvals łatwe do obsługi dotykiem,
- log viewer z poziomym przewijaniem,
- brak hover-only interactions.

---

# 76. PWA — opcjonalnie rc1

Dashboard może dostać:

```text
manifest.webmanifest
service worker
icon set
standalone display
```

Ale PWA nie może cachować:
- approval state,
- live task data,
- auth-sensitive API responses.

Offline tylko:
- shell UI,
- statyczne assety.

---

# 77. FastAPI dependency list

Przykładowo:

```text
fastapi
uvicorn
pydantic
python-multipart
itsdangerous
```

Opcjonalnie:
- `psutil`,
- `jinja2`.

Nie instalować zbędnych pakietów.

---

# 78. Web performance

Cel:
- dashboard shell < 1 MB,
- pierwsze renderowanie szybkie,
- API pagination,
- log tail zamiast pełnych logów,
- metrics aggregation.

---

# 79. Observability rc1

Dodać:

```text
agentbox_http_requests_total
agentbox_http_errors_total
agentbox_http_request_duration_seconds
agentbox_websocket_connections
agentbox_websocket_messages_total
agentbox_auth_failures_total
agentbox_active_sessions
```

---

# 80. API request tracing

Każdy request dostaje:

```text
request_id
```

Przykład:

```text
req_7fa3...
```

Powinien występować:
- log,
- API audit,
- error response.

---

# 81. Log format

Preferowany JSONL dla backendu:

```json
{
  "ts": "...",
  "level": "INFO",
  "component": "api",
  "request_id": "req_123",
  "message": "task created",
  "task_id": "tsk_123"
}
```

---

# 82. Error boundary

API nie może wysyłać tracebacków klientowi.

Do klienta:

```json
{
  "error": {
    "code": "INTERNAL_ERROR",
    "message": "Internal server error"
  }
}
```

Traceback tylko do logów serwera.

---

# 83. API versioning

Całość:

```text
/api/v1/...
```

Nie wystawiać nieversionowanych endpointów kontrolnych.

---

# 84. Stable compatibility

rc1 musi zachować:

```text
agent5 task ...
agent5 daemon ...
agent5 approval ...
agent5 policy ...
agent5 budget ...
agent5 risk ...
```

Web API jest nowym frontendem, nie zamiennikiem core.

---

# 85. Self-test rc1

Docelowo:

```bash
agent5 selftest
```

powinien zawierać:

```text
AgentBox v5.0-rc1

[OK] database
[OK] migrations
[OK] daemon
[OK] scheduler
[OK] agent registry
[OK] memory
[OK] context builder
[OK] handoffs
[OK] observability
[OK] policy
[OK] budget
[OK] risk
[OK] approvals
[OK] enforcement
[OK] API
[OK] authentication
[OK] WebSocket
[OK] dashboard assets
[OK] web runtime
[OK] artifact security
[OK] Tailscale bind

RESULT: PASS
```

---

# 86. rc1 completion report

Po wdrożeniu wygenerować raport:

```text
Version
DB schema
Backup path
Daemon PID
Web PID
Dashboard URL
API URL
WebSocket URL
Auth mode
Active providers
Test results
Failed tests
Open issues
Rollback path
```

---

# 87. Następny etap

Po udanym rc1:

## `AgentBox v5.0 stable — Production Hardening & Recovery`

Zakres:

```text
Migration hardening
Backup manager
Restore manager
Crash recovery
Task recovery
Orphan worktree cleanup
Orphan PID cleanup
DB integrity checks
Event compaction
Log rotation
Artifact retention
Memory maintenance
Security review
API hardening
Web hardening
Upgrade framework
Rollback framework
Release packaging
Documentation
End-to-end tests
```

Stable powinno być pierwszą wersją, którą można uznać za spójną platformę AgentBox v5.

---

# 88. Reguła wdrożeniowa

rc1 ma być uznane za gotowe dopiero gdy:

```text
beta3 PASS
→ backup
→ migration
→ API tests
→ WebSocket tests
→ security tests
→ dashboard tests
→ Tailscale test
→ restart test
→ recovery test
→ full selftest PASS
```

Dopiero wtedy:

```text
v5.0-rc1 ACTIVE
```
