# AgentBox v5.1 — Distributed Agents & Remote Workers

**Środowisko główne:** AgentBox  
**Control Plane:** `100.123.66.15:22`  
**Użytkownik:** `box`  
**Hostname:** `cursor`  
**Root projektu:** `/workspace/agentbox-v5`  
**Poprzednia wersja:** `v5.0.0 Stable`  
**Nowa wersja:** `v5.1.0`

> v5.1 rozszerza AgentBox z jednego serwera do architektury wielowęzłowej. Główny serwer `cursor` pozostaje Control Plane, a dodatkowe hosty mogą działać jako Remote Workers. Wszystkie zmiany nadal muszą przechodzić przez istniejące Policy, Budget, Risk, Approval, Observability i Recovery Engines.

---

# 1. Cel v5.1

AgentBox v5.1 ma obsługiwać:

- wiele worker nodes,
- rejestrację zdalnych workerów,
- bezpieczny enrollment,
- capabilities per node,
- heartbeat i health,
- distributed scheduler,
- task routing,
- remote sandboxes,
- remote worktrees,
- cross-node handoffs,
- artifact transfer,
- memory/context transfer,
- node budgets,
- node policies,
- node quarantine,
- failover,
- recovery po utracie workera,
- distributed observability,
- dashboard wielowęzłowy.

Docelowa architektura:

```text
                        AgentBox Control Plane
                          cursor / 100.123.66.15
                                  │
                     ┌────────────┼────────────┐
                     │            │            │
                     ▼            ▼            ▼
                  Worker A      Worker B      Worker C
                   Linux         Linux         GPU Node
                     │            │            │
             ┌───────┼──────┐     │       ┌────┼────┐
             ▼       ▼      ▼     ▼       ▼    ▼    ▼
          Claude   Codex   Test  Build   Ollama GPU  Docs
```

---

# 2. Role w architekturze

## Control Plane

Odpowiada za:
- task registry,
- global scheduler,
- policies,
- budgets,
- risk,
- approvals,
- memory metadata,
- artifacts metadata,
- worker registry,
- worker routing,
- recovery,
- dashboard,
- REST API,
- WebSocket,
- audit.

## Worker Node

Odpowiada za:
- wykonywanie zadań,
- lokalny sandbox,
- provider execution,
- lokalny artifact staging,
- lokalny context cache,
- heartbeat,
- metrics,
- worker logs,
- task checkpoints,
- transport wyników do Control Plane.

---

# 3. Nowe komponenty

```text
agentbox/
├── distributed/
│   ├── registry.py
│   ├── enrollment.py
│   ├── transport.py
│   ├── scheduler.py
│   ├── routing.py
│   ├── heartbeat.py
│   ├── capabilities.py
│   ├── worker_client.py
│   ├── worker_server.py
│   ├── transfer.py
│   ├── quarantine.py
│   └── failover.py
│
├── worker/
│   ├── runtime.py
│   ├── executor.py
│   ├── sandbox.py
│   ├── health.py
│   └── local_store.py
```

---

# 4. Worker Registry

Każdy worker ma rekord:

```text
worker_id
name
hostname
tailscale_ip
platform
architecture
status
version
capabilities
labels
max_parallel_tasks
current_load
last_heartbeat
enrolled_at
quarantined
```

---

# 5. Migracja SQLite

Dodaj:

```sql
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
    FOREIGN KEY(worker_id) REFERENCES workers(id),
    FOREIGN KEY(task_id) REFERENCES tasks(id)
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

CREATE INDEX IF NOT EXISTS idx_workers_status
ON workers(status);

CREATE INDEX IF NOT EXISTS idx_worker_assignments_worker
ON worker_assignments(worker_id);

CREATE INDEX IF NOT EXISTS idx_worker_metrics_worker
ON worker_metrics(worker_id);
```

---

# 6. Worker Status

Stany:

```text
new
enrolling
online
busy
degraded
draining
offline
quarantined
maintenance
```

---

# 7. Secure Enrollment

Enrollment musi być jawny.

Control Plane:

```bash
agent5 worker token create
```

Generuje jednorazowy token.

Worker:

```bash
agent5-worker enroll \
  --control-plane 100.123.66.15:8787 \
  --token ENROLLMENT_TOKEN
```

Token:
- jednorazowy,
- TTL,
- hashed po stronie Control Plane.

---

# 8. Enrollment Flow

```text
worker requests enrollment
↓
token validation
↓
Tailscale source validation
↓
capability probe
↓
worker record created
↓
worker session issued
↓
heartbeat starts
```

---

# 9. Worker Authentication

Worker nie używa admin tokenu dashboardu.

Osobny mechanizm:

```text
worker session token
```

Zakres:
- heartbeat,
- assignment poll,
- task result,
- artifact upload,
- metrics,
- worker logs.

---

# 10. Tailscale Requirement

Domyślnie remote workers tylko przez Tailscale.

Nie dopuszczać publicznego enrollmentu.

Worker record powinien zapisywać:

```text
tailscale_ip
hostname
worker_id
```

---

# 11. Capability Discovery

Worker raportuje:

```text
cpu_count
memory_total
disk_free
architecture
docker
git
python
node
rust
go
gpu
cuda
providers
```

Przykład:

```json
{
  "cpu": 8,
  "memory_gb": 16,
  "docker": true,
  "rust": true,
  "node": true,
  "gpu": false,
  "providers": [
    "claude",
    "codex"
  ]
}
```

---

# 12. Worker Labels

Manualne labels:

```text
rust
gpu
docs
frontend
linux
trusted
high-memory
```

CLI:

```bash
agent5 worker label add WORKER_ID rust
agent5 worker label remove WORKER_ID rust
```

---

# 13. Distributed Scheduler

Scheduler wybiera worker na podstawie:

```text
required capabilities
labels
provider availability
CPU
RAM
current load
budget
policy
risk
sandbox requirements
project affinity
```

---

# 14. Routing Score

Przykład:

```text
capability match      40%
load                   20%
provider locality      15%
project cache          10%
health                 10%
network latency         5%
```

---

# 15. Task Constraints

Task może deklarować:

```text
requires_gpu
requires_docker
requires_rust
preferred_provider
required_labels
min_memory_gb
max_worker_risk
```

---

# 16. Worker Selection API

```python
select_worker(
    task_id,
    requirements,
    policy_context,
) -> WorkerDecision
```

Wynik:

```json
{
  "worker_id": "wrk_abcd",
  "score": 87,
  "reasons": [
    "rust capability",
    "provider claude available",
    "low load"
  ]
}
```

---

# 17. Distributed Queue

Queue pozostaje logicznie centralna.

Control Plane decyduje:
- co,
- gdzie,
- kiedy.

Worker nie samodzielnie pobiera dowolnych tasków bez assignmentu.

---

# 18. Worker Pull Model

Bezpieczniejszy rc:

```text
worker polls assignment endpoint
```

zamiast Control Plane inicjującego połączenie do workera.

Zalety:
- NAT friendly,
- Tailscale friendly,
- mniej otwartych portów.

---

# 19. Worker Assignment Flow

```text
task ready
↓
scheduler selects worker
↓
assignment created
↓
worker polls
↓
worker accepts
↓
status busy
↓
execution
↓
result upload
↓
status online
```

---

# 20. Assignment Lease

Każdy assignment ma lease:

```text
lease_seconds = 60
```

Worker odnawia lease heartbeatem.

Jeśli lease wygasa:
- assignment stale,
- task interrupted,
- failover.

---

# 21. Worker Heartbeat

Domyślnie:

```text
heartbeat interval = 5s
offline threshold = 20s
```

Heartbeat zawiera:
- CPU,
- RAM,
- disk,
- active tasks,
- version,
- health.

---

# 22. Node Health

Status:

```text
healthy
degraded
unhealthy
offline
```

---

# 23. Remote Sandbox

Worker tworzy lokalny sandbox:

```text
worktree
docker
direct-readonly
```

Control Plane przekazuje tylko wymagany context.

---

# 24. Project Distribution

Nie kopiować całego repo zawsze.

Tryby:

```text
git clone
git fetch
worktree
artifact bundle
context-only
```

Preferowany:
- Git remote dostępny -> clone/fetch,
- bez remote -> signed bundle/artifact transfer.

---

# 25. Git Revision Pinning

Assignment musi zawierać:

```text
repo
commit_sha
branch
task_branch
```

Worker wykonuje pracę na dokładnym SHA.

---

# 26. Remote Worktree

Worker:

```text
project cache
↓
fetch SHA
↓
create worktree
↓
create task branch
↓
execute
```

---

# 27. Artifact Transfer

Transport artifactów:

```text
worker
↓
chunked upload
↓
Control Plane artifact store
```

Każdy artifact:
- sha256,
- size,
- task,
- run,
- worker,
- agent.

---

# 28. Artifact Verification

Control Plane po upload:
1. size check,
2. sha256 check,
3. metadata validation,
4. register artifact.

---

# 29. Cross-Node Handoffs

Przykład:

```text
Planner @ Worker-A
↓
handoff
↓
Researcher @ Worker-B
↓
result
↓
Architect @ Worker-A
```

Context nie jest przekazywany peer-to-peer.

Preferowany model:

```text
Worker A
↓
Control Plane
↓
Worker B
```

---

# 30. Handoff Routing

Scheduler może przenieść handoff na inny worker na podstawie capabilities.

Przykład:

```text
Security Agent
requires label=security
```

---

# 31. Context Transfer

Paczka:

```text
task summary
handoff summary
memory refs
relevant files
artifacts
constraints
policy context
```

Nie wysyłać całej historii bez potrzeby.

---

# 32. Memory Transfer

Preferowany:
- memory refs,
- resolved snippets,
- no unrestricted DB copy.

Worker nie dostaje całej centralnej pamięci.

---

# 33. Remote Memory Cache

Worker może cache'ować read-only context.

Cache:
- TTL,
- task-scoped,
- encrypted/permission restricted jeśli zawiera wrażliwy kontekst.

---

# 34. Policy Across Nodes

Global policy zawsze egzekwuje Control Plane.

Worker dodatkowo egzekwuje lokalną kopię policy snapshot.

Przed task:
- Control Plane policy check,
- signed policy snapshot,
- Worker enforcement.

---

# 35. Policy Version

Assignment zawiera:

```text
policy_version
```

Worker odrzuca assignment, jeśli wymagany policy version jest nowszy niż lokalnie wspierany.

---

# 36. Budget Across Nodes

Budżet centralny.

Worker raportuje usage:

```text
runtime
tokens
cost
network requests
files changed
handoffs
```

Control Plane aktualizuje global budget.

---

# 37. Worker Budget

Możliwe limity:

```text
max_concurrent_tasks
daily_runtime
daily_cost
daily_tokens
```

---

# 38. Risk by Worker

Worker może mieć trust score:

```text
trusted
standard
restricted
quarantined
```

High-risk tasks tylko na trusted nodes.

---

# 39. Node Quarantine

Przy:
- policy violation,
- suspicious response,
- bad checksum,
- repeated failures,
- version mismatch,
- auth anomaly.

Status:

```text
quarantined
```

Worker nie dostaje nowych zadań.

---

# 40. Quarantine CLI

```bash
agent5 worker quarantine WORKER_ID --reason "..."
agent5 worker unquarantine WORKER_ID
```

Unquarantine wymaga admina.

---

# 41. Worker Drain

Przed maintenance:

```bash
agent5 worker drain WORKER_ID
```

Nowe taski nie trafiają na node.

Aktywne kończą się.

---

# 42. Worker Remove

```bash
agent5 worker remove WORKER_ID
```

Tylko jeśli:
- brak active tasks,
- brak leases,
- worker drained/offline.

---

# 43. Failover

Jeśli worker znika:

```text
heartbeat lost
↓
lease expires
↓
run interrupted
↓
checkpoint available?
├── yes -> recover
└── no -> restart task
↓
scheduler picks another worker
```

---

# 44. Failover Policy

```ini
[distributed]
auto_failover = true
max_failovers = 2
failover_delay_seconds = 10
require_checkpoint_for_high_risk = true
```

---

# 45. Checkpoints Across Nodes

Worker uploaduje:
- git SHA,
- patch,
- stage state,
- artifacts,
- run metadata.

---

# 46. Distributed Recovery

Control Plane recovery engine rozszerz o:
- stale assignment,
- offline worker,
- orphaned remote run,
- partial artifact upload.

---

# 47. Partial Upload Recovery

Upload chunks mają:
- upload_id,
- chunk index,
- checksum.

Możliwe resume.

---

# 48. Transport

REST over Tailscale wystarczy dla v5.1.

Opcjonalnie później:
- gRPC.

Nie komplikować przed stabilnym distributed runtime.

---

# 49. Worker API

Control Plane:

```text
POST /api/v1/workers/enroll
POST /api/v1/workers/heartbeat
GET  /api/v1/workers/{id}/assignment
POST /api/v1/workers/{id}/assignment/{assignment_id}/accept
POST /api/v1/workers/{id}/assignment/{assignment_id}/result
POST /api/v1/workers/{id}/artifacts
```

---

# 50. Admin Worker API

```text
GET /api/v1/workers
GET /api/v1/workers/{id}
POST /api/v1/workers/{id}/drain
POST /api/v1/workers/{id}/quarantine
POST /api/v1/workers/{id}/unquarantine
DELETE /api/v1/workers/{id}
```

---

# 51. Worker Runtime CLI

Nowe:

```bash
agent5-worker enroll
agent5-worker start
agent5-worker stop
agent5-worker status
agent5-worker health
agent5-worker capabilities
```

---

# 52. Control Plane CLI

```bash
agent5 worker list
agent5 worker show WORKER_ID
agent5 worker token create
agent5 worker drain WORKER_ID
agent5 worker quarantine WORKER_ID
agent5 worker unquarantine WORKER_ID
agent5 worker remove WORKER_ID
```

---

# 53. Scheduler CLI

```bash
agent5 scheduler explain TASK_ID
```

Pokazuje dlaczego wybrano konkretny worker.

---

# 54. Assignment CLI

```bash
agent5 assignment list
agent5 assignment show ID
```

---

# 55. Dashboard — Workers

Nowa sekcja:

```text
Workers
```

Tabela:

```text
Name
Host
IP
Status
CPU
RAM
Tasks
Capabilities
Version
Last heartbeat
```

---

# 56. Worker Detail

Sekcje:

```text
Overview
Capabilities
Tasks
Runs
Metrics
Logs
Artifacts
Policies
Budgets
Events
```

---

# 57. Distributed Map

Dashboard może pokazywać:

```text
Control Plane
 ├── Worker A online
 ├── Worker B busy
 └── Worker C degraded
```

---

# 58. Dashboard Routing View

Task detail:

```text
Task
↓
Planner @ worker-a
↓
Researcher @ worker-b
↓
Coder @ worker-a
↓
Tester @ worker-c
```

---

# 59. Distributed Metrics

Dodaj:

```text
agentbox_workers_total
agentbox_workers_online
agentbox_workers_offline
agentbox_worker_cpu_percent
agentbox_worker_memory_percent
agentbox_assignments_total
agentbox_assignments_failed
agentbox_failovers_total
agentbox_remote_artifact_bytes
```

---

# 60. Event Taxonomy

Dodaj:

```text
worker.enrolled
worker.online
worker.offline
worker.degraded
worker.draining
worker.quarantined

assignment.created
assignment.accepted
assignment.started
assignment.completed
assignment.failed
assignment.expired

failover.started
failover.completed
failover.failed

artifact.remote_upload
artifact.remote_verified
```

---

# 61. Worker Version Compatibility

Control Plane sprawdza:

```text
major version
protocol version
schema compatibility
```

Worker ze starszym protokołem może dostać:

```text
upgrade_required
```

---

# 62. Protocol Version

Dodaj:

```text
AGENTBOX_DISTRIBUTED_PROTOCOL=1
```

Handshake worker -> control plane.

---

# 63. Security

Worker token:
- unique,
- scoped,
- revocable,
- hashed centrally.

Nie używać:
- dashboard admin token,
- SSH password,
- provider secrets z Control Plane bez potrzeby.

---

# 64. Provider Credentials

Preferowane:
- provider credential lokalnie na workerze,
- Control Plane wie tylko provider capability.

Alternatywa:
- scoped secret injection,
- tylko jeśli konieczne.

---

# 65. Secret Distribution

Jeśli konieczne:
- encrypted transport,
- ephemeral,
- task-scoped,
- never persisted in logs.

---

# 66. File Security

Worker może działać tylko:
- sandbox root,
- AgentBox cache,
- artifact staging.

Nie pisać w system paths.

---

# 67. Enrollment Approval

Nowy worker może wymagać:

```text
pending_enrollment
↓
admin approve
↓
active
```

Rekomendowane domyślnie.

---

# 68. Worker Approval UI

Dashboard:
- pending worker,
- hostname,
- IP,
- capabilities,
- approve/reject.

---

# 69. Worker Backup

Worker nie jest źródłem prawdy.

Control Plane przechowuje:
- assignments,
- artifacts,
- state,
- events.

Worker może być odtworzony.

---

# 70. Worker Local Store

Tylko:
- cache,
- active task state,
- temporary artifacts,
- checkpoints przed upload.

---

# 71. Garbage Collection Worker

Po task:
- upload artifacts,
- verify,
- release sandbox,
- cleanup temp.

---

# 72. Project Cache

Worker może utrzymywać repo cache.

Cache key:
- repo URL,
- project ID.

---

# 73. Cache Invalidation

Przy:
- remote changed,
- security policy,
- manual cleanup.

---

# 74. Worker Maintenance

```bash
agent5-worker maintenance
agent5-worker cleanup
```

---

# 75. Worker Diagnostics

```bash
agent5-worker diagnostics
```

Generuje:
- health,
- capabilities,
- version,
- recent logs,
- active tasks,
- cache stats.

Bez sekretów.

---

# 76. Multi-Node Self-Test

```bash
agent5 selftest --distributed
```

Sprawdza:
- worker registry,
- enrollment,
- heartbeat,
- assignment,
- result,
- artifact transfer,
- failover.

---

# 77. Smoke Test A — Enrollment

```text
create token
↓
worker enrolls
↓
admin approves
↓
worker online
```

---

# 78. Smoke Test B — Remote Task

```text
create task
↓
scheduler chooses worker
↓
assignment accepted
↓
task executes
↓
result returns
↓
artifact verified
```

---

# 79. Smoke Test C — Cross-Node Handoff

```text
Planner worker-a
↓
handoff
↓
Researcher worker-b
↓
artifact
↓
Planner resumes worker-a
```

---

# 80. Smoke Test D — Failover

```text
task running worker-a
↓
worker-a killed
↓
lease expires
↓
task interrupted
↓
worker-b selected
↓
task recovers
```

---

# 81. Smoke Test E — Quarantine

```text
worker sends invalid artifact checksum
↓
security event
↓
worker quarantined
↓
no new assignments
```

---

# 82. Acceptance Criteria

v5.1 jest gotowa tylko jeśli:

- [ ] Control Plane v5.0 remains stable
- [ ] worker enrollment works
- [ ] enrollment token expiry works
- [ ] worker auth scoped correctly
- [ ] heartbeat works
- [ ] offline detection works
- [ ] capabilities stored
- [ ] scheduler routes correctly
- [ ] task constraints respected
- [ ] assignment leases work
- [ ] remote sandbox works
- [ ] remote worktree works
- [ ] artifacts verified
- [ ] cross-node handoff works
- [ ] context transfer works
- [ ] memory transfer limited/scoped
- [ ] policy enforced centrally and locally
- [ ] budgets aggregated centrally
- [ ] risk routing works
- [ ] quarantine works
- [ ] drain works
- [ ] failover works
- [ ] recovery works
- [ ] dashboard worker view works
- [ ] distributed metrics work
- [ ] distributed selftest PASS
- [ ] rollback path documented

---

# 83. Deployment Guard

Control Plane nadal:

```bash
agentbox-deploy-guard
```

Worker ma własny guard:

```text
agentbox-worker-guard
```

Sprawdza:
- worker root,
- expected user,
- Tailscale connectivity,
- config.

---

# 84. Control Plane Backup

Przed v5.1:
- DB backup,
- config backup,
- release backup,
- worker registry export.

---

# 85. Worker Install Root

Rekomendacja:

```text
/opt/agentbox-worker
```

lub:

```text
~/agentbox-worker
```

zależnie od permissions.

---

# 86. Worker Config

```text
~/.config/agentbox-worker/config.ini
```

Przykład:

```ini
[worker]
name = gpu-node-1
control_plane = http://100.123.66.15:8787
heartbeat_seconds = 5
max_parallel_tasks = 2

[security]
tailscale_only = true

[sandbox]
default = worktree
docker_enabled = true
```

---

# 87. Worker Runtime Without systemd

Tak jak Control Plane:
- PID file,
- detached process,
- heartbeat,
- stop/restart CLI.

---

# 88. Distributed Recovery Report

Po failover generuj:

```text
RECOVERY_REPORT_<task>.md
```

Z:
- failed worker,
- last checkpoint,
- replacement worker,
- resumed stage,
- artifacts recovered,
- data loss estimate.

---

# 89. v5.1 Release Report

Po wdrożeniu:

```text
AgentBox v5.1.0
Control Plane: cursor
Workers: N
Online: N
Quarantined: N
Protocol: 1
Distributed selftest: PASS
Failover test: PASS
Artifact transfer: PASS
```

---

# 90. Następny etap

## AgentBox v5.2 — Intelligence Upgrade

Zakres:

```text
Semantic Project Index
Vector Memory
Advanced Context Routing
Model Router
Automatic Provider Selection
Agent Specialization
Task Classification
Learned Routing Heuristics
Experience Memory
Completion Quality Signals
Context Compression
Cross-Project Knowledge
```

v5.2 powinno skupić się na jakości inteligencji platformy, a nie na dalszej rozbudowie infrastruktury.
