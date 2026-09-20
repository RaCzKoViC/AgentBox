# AgentBox v5.4 — Tool Intelligence & Capability Runtime

**Środowisko główne:** AgentBox  
**Control Plane:** `100.123.66.15:22`  
**Użytkownik:** `box`  
**Hostname:** `cursor`  
**Root projektu:** `/workspace/agentbox-v5`  
**Poprzednia wersja:** `v5.3.0` — Autonomous Planning & Workflow Intelligence  
**Nowa wersja:** `v5.4.0`

> v5.4 rozwija AgentBox o inteligentną, kontrolowaną i audytowalną warstwę narzędzi. Celem jest umożliwienie agentom bezpiecznego odkrywania, dobierania, wykonywania i łączenia narzędzi lokalnych, zdalnych i usługowych bez utraty kontroli nad Policy, Budget, Risk, Approval, Sandboxing, Observability i Recovery.

---

# 1. Cel v5.4

AgentBox v5.4 ma zapewnić:

- Tool Registry v2,
- dynamiczne wykrywanie narzędzi,
- capability matching,
- tool planning,
- tool chaining,
- tool sandboxing,
- MCP integration,
- Connector Runtime,
- Browser/API/Database tools,
- SSH/SFTP/Tailscale tools,
- file tools,
- Git tools,
- Docker tools,
- shell tools,
- provider tools,
- risk/cost profiles per tool,
- reliability scoring,
- tool outcome memory,
- tool health checks,
- per-agent tool permissions,
- distributed tool execution,
- observability i audit dla każdego tool call.

Docelowy pipeline:

```text
Goal / Task
   │
   ▼
Planner
   │
   ▼
Tool Need Detection
   │
   ▼
Tool Registry
   │
   ▼
Capability Match
   │
   ▼
Policy / Risk / Budget
   │
   ▼
Tool Selection
   │
   ▼
Sandbox / Worker
   │
   ▼
Tool Execution
   │
   ▼
Result Validation
   │
   ▼
Artifact / Memory / Event
   │
   ▼
Next Tool / Agent / Completion
```

---

# 2. Główne moduły

```text
agentbox/
├── tools/
│   ├── registry.py
│   ├── discovery.py
│   ├── capability.py
│   ├── planner.py
│   ├── executor.py
│   ├── validator.py
│   ├── chaining.py
│   ├── health.py
│   ├── permissions.py
│   ├── reliability.py
│   ├── cost.py
│   ├── risk.py
│   ├── outcome_memory.py
│   └── adapters/
│       ├── shell.py
│       ├── filesystem.py
│       ├── git.py
│       ├── docker.py
│       ├── ssh.py
│       ├── sftp.py
│       ├── tailscale.py
│       ├── browser.py
│       ├── http.py
│       ├── database.py
│       ├── mcp.py
│       └── connector.py
│
└── capabilities/
    ├── registry.py
    ├── matcher.py
    └── schemas.py
```

---

# 3. Tool Registry v2

Każde narzędzie ma rekord:

```text
tool_id
name
display_name
category
provider
version
enabled
execution_mode
capabilities
permissions
risk_level
cost_profile
timeout
retry_policy
health_status
worker_requirements
input_schema
output_schema
created_at
updated_at
```

---

# 4. Tool Categories

```text
shell
filesystem
git
ssh
sftp
tailscale
docker
browser
http
database
search
build
test
package
artifact
memory
mcp
connector
custom
```

---

# 5. Execution Modes

```text
local
remote
worker
sandbox
container
api
mcp
connector
```

---

# 6. Capability Model

Narzędzia publikują capabilities, np.:

```text
read_file
write_file
search_code
git_status
git_diff
git_commit
ssh_exec
sftp_upload
docker_build
http_get
database_query
browser_open
artifact_create
```

---

# 7. Capability Matching

Planner nie wybiera narzędzia po nazwie, tylko po capability.

Przykład:

```text
Need:
remote_file_upload
```

Możliwe narzędzia:
- SFTP,
- rsync over SSH,
- SCP.

Matcher wybiera najlepsze na podstawie:
- bezpieczeństwa,
- dostępności,
- kosztu,
- historii sukcesów,
- platformy,
- worker capability.

---

# 8. Tool Capability API

```python
find_tools(
    capability,
    task_id=None,
    agent_name=None,
    worker_id=None,
    constraints=None,
)
```

---

# 9. Tool Selection Score

Przykład:

```text
capability match      35%
policy fit            20%
reliability           15%
latency               10%
cost                  10%
worker locality        5%
historical success     5%
```

---

# 10. Tool Discovery

Źródła:

```text
PATH binaries
AgentBox adapters
MCP servers
connected plugins/connectors
worker capabilities
project-local tools
Docker images
configured APIs
```

---

# 11. Safe Discovery

Discovery ma być read-only.

Przykłady:

```bash
command -v git
command -v docker
command -v rsync
command -v tailscale
```

Nie instalować narzędzi automatycznie podczas discovery.

---

# 12. Tool Manifest

Każdy adapter powinien mieć manifest:

```yaml
id: ssh.exec
name: SSH Exec
category: ssh
capabilities:
  - remote_exec

risk:
  default: moderate

permissions:
  - network
  - remote_shell

execution:
  mode: local
  timeout: 120
```

---

# 13. Tool Input Schema

Każdy tool musi mieć walidowane wejście.

Przykład:

```json
{
  "host": "agentbox",
  "command": "agent5 health",
  "timeout": 30
}
```

---

# 14. Tool Output Schema

Przykład:

```json
{
  "ok": true,
  "exit_code": 0,
  "stdout": "...",
  "stderr": "",
  "duration_ms": 251
}
```

---

# 15. Tool Executor

Centralny executor:

```python
execute_tool(
    tool_id,
    input_payload,
    task_context,
    agent_context,
)
```

Przed wykonaniem:

```text
resolve tool
↓
validate input
↓
permission check
↓
risk assessment
↓
budget check
↓
approval if required
↓
select worker/sandbox
↓
execute
↓
validate output
↓
record event
```

---

# 16. Tool Permissions

Każdy agent ma dozwolone capabilities.

Przykład:

```text
Planner:
read_file
search_code
browser_search
http_get

Coder:
read_file
write_file
git_diff
build
test

Reviewer:
read_file
git_diff
test

Release:
git_commit
git_merge
git_push (approval)
```

---

# 17. Tool Risk Profiles

Przykładowe:

```text
read_file           LOW
write_file          MODERATE
delete_file         HIGH
git_commit          MODERATE
git_push            HIGH
force_push          CRITICAL
docker_build        MODERATE
docker_privileged   CRITICAL
database_read       MODERATE
database_write      HIGH
ssh_exec            MODERATE/HIGH
system_write        CRITICAL
```

---

# 18. Tool Cost Profiles

Koszt może obejmować:

```text
API cost
tokens
runtime
CPU
RAM
network
GPU
disk
```

---

# 19. Budget Integration

Tool call zużywa budżet.

Przed:
- estimate.

Po:
- record actual usage.

---

# 20. Reliability Score

Każdy tool ma historię:

```text
successes
failures
timeouts
validation failures
retries
avg latency
```

Score np. 0-100.

---

# 21. Tool Health

Status:

```text
healthy
degraded
unavailable
disabled
quarantined
```

---

# 22. Tool Health Checks

Przykłady:

```text
git -> git --version
docker -> docker info
ssh -> ssh -V
tailscale -> tailscale status
database -> SELECT 1
MCP -> handshake
HTTP API -> health endpoint
```

---

# 23. Tool Quarantine

Jeśli narzędzie:
- wielokrotnie zwraca uszkodzone wyniki,
- łamie schema,
- przekracza timeout,
- narusza policy,

status:

```text
quarantined
```

---

# 24. MCP Integration

v5.4 ma obsługiwać MCP jako jeden z runtime.

Elementy:

```text
MCP Server Registry
MCP Capability Discovery
MCP Tool Import
MCP Resource Import
MCP Prompt Import
MCP Health
MCP Permissions
MCP Audit
```

---

# 25. MCP Server Record

```text
mcp_id
name
transport
endpoint
command
enabled
capabilities
auth_mode
health
trust_level
```

---

# 26. MCP Transports

Obsługuj:

```text
stdio
HTTP
SSE
```

zgodnie z tym, co wspiera użyta biblioteka/runtime.

---

# 27. MCP Safety

MCP tool nie omija Policy Engine.

Pipeline:

```text
MCP tool
↓
import capability
↓
AgentBox policy
↓
risk
↓
budget
↓
approval
↓
execute
```

---

# 28. Connector Runtime

Connector to integracja z zewnętrzną usługą.

Przykłady:

```text
GitHub
Gmail
Google Drive
Airtable
custom REST API
database
ticketing system
```

---

# 29. Connector Manifest

```text
connector_id
name
service
capabilities
auth_type
scopes
enabled
risk
rate_limit
```

---

# 30. Credential Isolation

Sekrety connectorów:
- nie w SQLite plaintext,
- nie w logs,
- nie w artifacts,
- nie w model context bez potrzeby.

---

# 31. Browser Tool

Browser capabilities:

```text
open_url
search_web
extract_text
download_file
inspect_page
```

Nie domyślnie:
- arbitrary credential entry,
- unsafe form submission.

---

# 32. HTTP Tool

Capabilities:

```text
GET
POST
PUT
PATCH
DELETE
```

POST/DELETE mogą wymagać wyższego risk/approval.

---

# 33. Database Tool

Tryby:

```text
read-only
read-write
migration
admin
```

Domyślnie read-only.

---

# 34. Database Query Guard

Blokować lub approval dla:

```text
DROP
TRUNCATE
DELETE without WHERE
ALTER destructive
```

---

# 35. SSH Tool

Integracja z istniejącym skill/host registry AgentBox.

Capabilities:

```text
ssh.verify
ssh.exec
ssh.upload
ssh.download
ssh.health
```

---

# 36. SFTP Tool

Capabilities:

```text
sftp.list
sftp.stat
sftp.upload
sftp.download
sftp.rename
```

Delete wymaga wyższego risk.

---

# 37. Tailscale Tool

Capabilities:

```text
tailscale.status
tailscale.ping
tailscale.peers
tailscale.netcheck
```

Logout/reset:
- CRITICAL,
- approval/deny.

---

# 38. Tool Chaining

Agent może tworzyć łańcuch:

```text
search code
↓
read file
↓
edit file
↓
run test
↓
git diff
```

---

# 39. Chain Planner

```python
plan_tool_chain(goal, capabilities, constraints)
```

---

# 40. Chain Validation

Przed execution:
- no forbidden tool,
- no policy bypass,
- dependencies valid,
- expected outputs compatible.

---

# 41. Chain Checkpoints

Po każdym high-impact tool call:
- checkpoint,
- artifact,
- event.

---

# 42. Dynamic Tool Substitution

Jeśli tool unavailable:

```text
rsync unavailable
↓
fallback to SFTP
```

Tylko jeśli capability-equivalent i policy allowed.

---

# 43. Tool Outcome Memory

Po każdym tool call zapisuj:

```text
tool
capability
task type
input class
success
failure type
latency
worker
provider
```

---

# 44. Experience Integration

v5.2 Experience Memory może wpływać na wybór narzędzia.

---

# 45. Tool Planning with v5.3

Planner może umieścić w planie:

```text
required_capability = "git_diff"
```

niekoniecznie konkretny tool.

Runtime rozwiązuje capability później.

---

# 46. Adaptive Tool Graph

W execution:

```text
tool A fails
↓
reflection
↓
tool B chosen
↓
continue
```

---

# 47. Tool Reflection

Po failed call:

```text
retry same tool
fallback tool
replan
escalate
```

---

# 48. Distributed Tool Runtime

v5.1 workers mogą publikować capabilities.

Przykład:

```text
worker-gpu:
  docker
  python
  ollama
  gpu
```

---

# 49. Worker Tool Registry

Control Plane posiada global registry.

Worker posiada lokalny registry.

Synchronizacja:
- manifesty,
- versions,
- health,
- capabilities.

---

# 50. Tool Version Compatibility

Assignment może wymagać:

```text
tool_id
min_version
```

---

# 51. Tool Locality

Scheduler preferuje worker, który już ma:
- tool,
- cache,
- project,
- artifact.

---

# 52. Sandbox Profiles

```text
readonly
workspace-write
network-limited
docker
high-risk-isolated
```

---

# 53. Shell Tool

Domyślny shell tool nie powinien być nieograniczonym `exec any`.

Wprowadź:

```text
command categories
allowlists
denylists
risk parser
```

---

# 54. Shell Risk Parser

Wykrywa m.in.:

```text
rm -rf
sudo
dd
mkfs
shutdown
reboot
iptables
nft
git reset --hard
git clean -fd
git push --force
docker system prune
```

---

# 55. Filesystem Tool

Capabilities:

```text
read
write
mkdir
copy
move
stat
search
```

Delete oddzielnie.

---

# 56. Path Guard

Dozwolone roots:

```text
/workspace
~/.local/share/agentbox-v5
~/.config/agentbox-v5
```

zgodnie z policy.

---

# 57. Git Tool

Capabilities:

```text
status
diff
log
branch
fetch
commit
merge
push
worktree
```

---

# 58. Git Protected Operations

```text
merge protected branch -> approval
push -> approval
force push -> deny
reset hard -> approval
clean -fd -> approval
```

---

# 59. Docker Tool

Capabilities:

```text
ps
logs
inspect
build
run
exec
stop
```

High-risk:
- privileged,
- host network,
- bind system paths.

---

# 60. Package Tool

Obsługa:

```text
apt
pip
npm
cargo
go
```

Instalacja globalna:
- approval.

Project-local:
- policy-dependent.

---

# 61. Build/Test Tools

Wykrywanie:

```text
pytest
cargo test
npm test
go test
make
cmake
```

---

# 62. Project Tool Profiles

Każdy projekt może mieć:

```text
build_command
test_command
lint_command
format_command
run_command
```

---

# 63. Tool Registry SQLite

```sql
CREATE TABLE IF NOT EXISTS tools (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    category TEXT NOT NULL,
    provider TEXT,
    version TEXT,
    enabled INTEGER NOT NULL DEFAULT 1,
    execution_mode TEXT NOT NULL,
    capabilities_json TEXT NOT NULL,
    permissions_json TEXT,
    risk_level TEXT,
    cost_profile_json TEXT,
    timeout_seconds INTEGER,
    health_status TEXT,
    worker_requirements_json TEXT,
    input_schema_json TEXT,
    output_schema_json TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS tool_runs (
    id TEXT PRIMARY KEY,
    tool_id TEXT NOT NULL,
    task_id TEXT,
    run_id TEXT,
    agent_name TEXT,
    worker_id TEXT,
    status TEXT NOT NULL,
    input_hash TEXT,
    output_hash TEXT,
    exit_code INTEGER,
    duration_ms INTEGER,
    risk_score INTEGER,
    cost REAL,
    error TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    finished_at TEXT,
    FOREIGN KEY(tool_id) REFERENCES tools(id)
);

CREATE TABLE IF NOT EXISTS tool_health (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    tool_id TEXT NOT NULL,
    status TEXT NOT NULL,
    latency_ms INTEGER,
    details_json TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY(tool_id) REFERENCES tools(id)
);

CREATE TABLE IF NOT EXISTS tool_reliability (
    tool_id TEXT PRIMARY KEY,
    success_count INTEGER NOT NULL DEFAULT 0,
    failure_count INTEGER NOT NULL DEFAULT 0,
    timeout_count INTEGER NOT NULL DEFAULT 0,
    reliability_score REAL NOT NULL DEFAULT 50,
    avg_latency_ms REAL,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY(tool_id) REFERENCES tools(id)
);

CREATE TABLE IF NOT EXISTS mcp_servers (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    transport TEXT NOT NULL,
    endpoint TEXT,
    command TEXT,
    enabled INTEGER NOT NULL DEFAULT 1,
    auth_mode TEXT,
    trust_level TEXT,
    health_status TEXT,
    metadata_json TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
```

---

# 64. Tool Events

Dodaj:

```text
tool.discovered
tool.registered
tool.selected
tool.started
tool.completed
tool.failed
tool.timeout
tool.quarantined
tool.fallback

mcp.connected
mcp.disconnected
mcp.tool_imported

connector.connected
connector.error
```

---

# 65. Tool Metrics

```text
agentbox_tool_runs_total
agentbox_tool_failures_total
agentbox_tool_duration_seconds
agentbox_tool_fallbacks_total
agentbox_tool_quarantined_total
agentbox_mcp_servers_online
agentbox_connector_errors_total
```

---

# 66. CLI — Tools

```bash
agent5 tool list
agent5 tool show TOOL_ID
agent5 tool discover
agent5 tool health
agent5 tool test TOOL_ID
agent5 tool enable TOOL_ID
agent5 tool disable TOOL_ID
agent5 tool quarantine TOOL_ID
```

---

# 67. CLI — Capabilities

```bash
agent5 capability list
agent5 capability search ssh_exec
agent5 capability explain CAPABILITY
```

---

# 68. CLI — MCP

```bash
agent5 mcp list
agent5 mcp add
agent5 mcp remove MCP_ID
agent5 mcp health MCP_ID
agent5 mcp tools MCP_ID
```

---

# 69. CLI — Tool Plans

```bash
agent5 tool-plan TASK_ID
agent5 tool-plan explain TASK_ID
```

---

# 70. Dashboard — Tools

Nowa sekcja:

```text
Tools
```

Tabela:

```text
Name
Category
Capabilities
Health
Risk
Reliability
Worker
Version
```

---

# 71. Tool Detail

Sekcje:

```text
Overview
Capabilities
Permissions
Health
Runs
Reliability
Risk
Cost
Workers
Events
```

---

# 72. Dashboard — MCP

Sekcja:

```text
MCP Servers
```

Pokazuje:
- transport,
- health,
- imported tools,
- trust level.

---

# 73. Dashboard — Connectors

Pokazuje:
- service,
- scopes,
- health,
- rate limit,
- recent errors.

Nigdy nie wyświetla sekretów.

---

# 74. Dashboard — Tool Runs

Tabela:

```text
Task
Agent
Tool
Worker
Status
Duration
Risk
Cost
```

---

# 75. Tool Graph UI

Task detail może pokazać:

```text
Search
↓
Read
↓
Edit
↓
Test
↓
Diff
```

---

# 76. Tool Approval UI

Dla high-risk call:

```text
Tool: git.push
Agent: release
Target: main
Risk: HIGH
Reason: protected branch

Approve / Reject
```

---

# 77. API Additions

```text
GET  /api/v1/tools
GET  /api/v1/tools/{id}
POST /api/v1/tools/discover
POST /api/v1/tools/{id}/test

GET  /api/v1/capabilities
GET  /api/v1/mcp
POST /api/v1/mcp
GET  /api/v1/tool-runs
```

---

# 78. Tool Execution API

Nie wystawiać dowolnego publicznego endpointu:

```text
POST /execute arbitrary shell
```

Wszystko przez registered tool + validated schema.

---

# 79. Tool Discovery Security

Discovery nie może:
- uruchamiać nieznanych binaries,
- automatycznie ufać MCP server,
- importować arbitrary credentials.

---

# 80. MCP Trust Levels

```text
trusted
standard
restricted
untrusted
```

---

# 81. Untrusted MCP

Może być:
- read-only,
- isolated,
- no secrets,
- approval per write action.

---

# 82. Tool Outcome Validation

Każdy tool ma validator.

Przykłady:
- JSON schema,
- exit code,
- checksum,
- expected file exists,
- test command pass.

---

# 83. False Success Prevention

Nie traktuj `exit_code=0` jako jedynego sygnału.

Np. upload:
- verify remote file,
- checksum.

---

# 84. Tool Retry

Retry tylko dla:
- timeout,
- transient network,
- temporary unavailable.

Nie dla:
- permission denied,
- policy denied,
- invalid input,
- destructive failure.

---

# 85. Tool Chain Rollback

Dla chain z mutacjami:
- checkpoint przed high-risk steps,
- rollback jeśli możliwe.

---

# 86. Tool Planning with Model Router

v5.2 Model Router i v5.4 Tool Planner współpracują:

```text
task
↓
choose agent/model
↓
choose tools
↓
execute
```

---

# 87. Tool Use Context

Context Builder może dołączyć:

```text
available tools
allowed capabilities
tool constraints
```

---

# 88. Agent-Specific Tool Views

Agent nie musi widzieć wszystkich narzędzi.

Planner:
- high-level search/read.

Coder:
- edit/build/test.

Reviewer:
- read/diff/test.

---

# 89. Tool Token Efficiency

Nie wysyłaj agentowi całych schematów 100 tools.

Wybierz relevant tool subset.

---

# 90. Capability Compression

Context:

```text
git.diff(path?)
filesystem.read(path)
test.run(scope)
```

zamiast pełnych wielkich manifestów.

---

# 91. Distributed Tool Security

Worker nie może ogłosić dowolnej capability bez walidacji Control Plane.

---

# 92. Worker Tool Attestation

Minimum:
- tool path,
- version,
- health,
- capability manifest.

---

# 93. Tool Cache

Registry cache:
- TTL,
- invalidate on worker change,
- invalidate on version update.

---

# 94. Tool Upgrade Detection

Jeśli version zmieni się:
- health recheck,
- reliability reset/partial decay,
- compatibility validation.

---

# 95. Feature Flags

```ini
[tools]
dynamic_discovery = true
tool_chaining = true
mcp = true
connectors = true
reliability_scoring = true
tool_outcome_memory = true
```

---

# 96. Compatibility Mode

Jeśli v5.4 wyłączone:
- v5.3 workflows nadal mogą używać legacy tools.

---

# 97. Tests

```text
tests/tools/
├── test_registry.py
├── test_discovery.py
├── test_capability_match.py
├── test_executor.py
├── test_permissions.py
├── test_risk.py
├── test_cost.py
├── test_health.py
├── test_reliability.py
├── test_chaining.py
├── test_mcp.py
├── test_connector.py
├── test_ssh_adapter.py
├── test_sftp_adapter.py
└── test_tool_fallback.py
```

---

# 98. Smoke Test A — Discovery

```text
discover git
↓
register
↓
health check
↓
capabilities visible
```

---

# 99. Smoke Test B — Safe Tool Call

```text
filesystem.read
↓
policy allow
↓
execute
↓
validated output
↓
event
```

---

# 100. Smoke Test C — High-Risk Tool

```text
git.push
↓
risk HIGH
↓
approval
↓
approved
↓
execute
```

---

# 101. Smoke Test D — Tool Fallback

```text
rsync unavailable
↓
matcher chooses sftp
↓
transfer succeeds
```

---

# 102. Smoke Test E — MCP

```text
connect MCP
↓
discover tools
↓
import restricted tool
↓
policy applied
↓
safe call
```

---

# 103. Smoke Test F — Worker Tool

```text
task requires docker
↓
scheduler selects worker with docker
↓
tool executes remotely
↓
result returns
```

---

# 104. Acceptance Criteria

v5.4 jest gotowa jeśli:

- [ ] Tool Registry działa
- [ ] discovery działa
- [ ] capability matching działa
- [ ] input/output schemas są walidowane
- [ ] tool permissions działają
- [ ] policy/risk/budget działają per tool
- [ ] approval gate działa
- [ ] reliability scoring działa
- [ ] health checks działają
- [ ] quarantine działa
- [ ] tool chaining działa
- [ ] fallback działa
- [ ] MCP integration działa
- [ ] connector runtime działa
- [ ] SSH/SFTP/Tailscale adapters działają
- [ ] distributed tool execution działa
- [ ] outcome memory działa
- [ ] dashboard tools działa
- [ ] tool selftest PASS
- [ ] rollback path istnieje

---

# 105. Self-Test

```bash
agent5 selftest --tools
```

Sprawdza:

```text
registry
discovery
capability matcher
executor
permissions
risk
budget
approvals
health
reliability
chaining
MCP
connectors
SSH
SFTP
distributed worker tools
```

---

# 106. Deployment Guard

Obowiązkowo:

```bash
agentbox-deploy-guard
```

Deploy tylko:

```text
hostname=cursor
user=box
root=/workspace/agentbox-v5
```

---

# 107. Backup Before v5.4

Backup:
- SQLite,
- configs,
- tool registry,
- MCP config,
- connector metadata,
- v5.3 planning state,
- current release.

---

# 108. Upgrade Sequence

```text
deployment guard
↓
v5.3 selftest
↓
backup
↓
maintenance mode
↓
DB migration
↓
install tool runtime
↓
discover safe local tools
↓
health checks
↓
tool selftest
↓
smoke tests
↓
enable feature flags
↓
activate
```

---

# 109. Rollback

Jeśli v5.4 failuje:
- disable dynamic tool runtime,
- fall back to legacy tool paths,
- restore DB/config backup if required,
- switch release,
- preserve planning/tasks.

---

# 110. Tool Intelligence Report

Po wdrożeniu wygenerować:

```text
TOOL_RUNTIME_REPORT_v5.4.0.md
```

Zawiera:

```text
Registered tools
Capabilities
Healthy tools
Quarantined tools
MCP servers
Connectors
Tool success rates
Fallbacks
Risk events
Approvals
Distributed tool runs
Open issues
Rollback path
```

---

# 111. Następny etap roadmapy

## AgentBox v5.5 — Self-Improvement, Evaluation & Benchmarking

Zakres:

```text
Evaluation Harness
Task Benchmarks
Agent Benchmarks
Model Benchmarks
Tool Benchmarks
Regression Detection
Quality Gates
Golden Tasks
Automatic A/B Tests
Prompt/Workflow Versioning
Performance Baselines
Cost/Quality Optimization
Failure Mining
Self-Improvement Proposals
Safe Prompt Evolution
Safe Workflow Evolution
Human-Approved Optimization
```

v5.5 powinno zamknąć pętlę jakości: AgentBox nie tylko wykonuje zadania, ale mierzy własną skuteczność i potrafi proponować bezpieczne ulepszenia swoich agentów, modeli, workflowów i narzędzi.
