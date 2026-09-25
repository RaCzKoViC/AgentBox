# AgentBox v5.6 — Operations Autopilot & Autonomous Platform Maintenance

**Środowisko główne:** AgentBox  
**Control Plane:** `100.123.66.15:22`  
**Użytkownik:** `box`  
**Hostname:** `cursor`  
**Root projektu:** `/workspace/agentbox-v5`  
**Poprzednia wersja:** `v5.5.0` — Self-Improvement, Evaluation & Benchmarking  
**Nowa wersja:** `v5.6.0`

> v5.6 przekształca AgentBox z platformy zdolnej do wykonywania i oceniania pracy w platformę zdolną również do bezpiecznego utrzymywania własnego środowiska operacyjnego. Autopilot ma wykrywać degradację, przewidywać problemy, wykonywać zatwierdzone niskiego ryzyka działania naprawcze, automatyzować runbooki i eskalować operacje wysokiego ryzyka do człowieka.

---

# 1. Główna zasada v5.6

Autonomia operacyjna nie oznacza nieograniczonego dostępu administracyjnego.

AgentBox musi stosować:

```text
OBSERVE
→ DETECT
→ DIAGNOSE
→ PLAN
→ RISK
→ POLICY
→ APPROVAL
→ REMEDIATE
→ VERIFY
→ REPORT
```

Operacje LOW RISK mogą być wykonywane autonomicznie, jeśli policy na to pozwala.

Operacje MODERATE/HIGH/CRITICAL wymagają odpowiednich approval gates.

AgentBox nie może sam:
- wyłączać zabezpieczeń,
- zwiększać własnych uprawnień,
- omijać Approval Engine,
- kasować backupów potrzebnych do rollback,
- wykonywać destrukcyjnych operacji tylko dlatego, że „prawdopodobnie pomogą”.

---

# 2. Cele

v5.6 ma dostarczyć:

- Operations Autopilot
- Automated Health Remediation
- Predictive Maintenance
- Resource Forecasting
- Capacity Planning
- Configuration Drift Detection
- Worker Drift Detection
- Provider Drift Detection
- Tool Drift Detection
- Dependency Drift Detection
- Smart Backup Scheduling
- Backup Verification
- Restore Drills
- Auto Cleanup
- Storage Pressure Management
- Log/Artifact Retention
- Self-Healing Playbooks
- Runbook Automation
- Upgrade Readiness Analysis
- Maintenance Windows
- Incident Detection
- Incident Timeline
- Root Cause Assistance
- Autonomous Low-Risk Remediation
- Human-Approved High-Risk Remediation
- Post-Remediation Verification
- Maintenance Dashboard
- Operations Reports

---

# 3. Architektura

```text
Telemetry / Health / Events
           │
           ▼
    Operations Monitor
           │
           ▼
     Anomaly Detector
           │
           ▼
    Diagnosis Engine
           │
           ▼
 Maintenance Planner
           │
           ▼
 Risk + Policy Engine
           │
      ┌────┴─────┐
      ▼          ▼
 Low Risk      Higher Risk
      │          │
      ▼          ▼
 Auto Run     Approval Gate
      │          │
      └────┬─────┘
           ▼
    Runbook Executor
           │
           ▼
      Verification
           │
     ┌─────┴─────┐
     ▼           ▼
  Success      Failure
     │           │
     ▼           ▼
  Report     Rollback/Escalate
```

---

# 4. Moduły

```text
agentbox/
├── operations/
│   ├── autopilot.py
│   ├── monitor.py
│   ├── diagnosis.py
│   ├── incidents.py
│   ├── remediation.py
│   ├── verification.py
│   ├── maintenance.py
│   └── reports.py
├── health/
│   ├── checks.py
│   ├── registry.py
│   ├── scoring.py
│   └── anomalies.py
├── drift/
│   ├── config.py
│   ├── workers.py
│   ├── providers.py
│   ├── tools.py
│   └── dependencies.py
├── capacity/
│   ├── resources.py
│   ├── forecasting.py
│   ├── pressure.py
│   └── planning.py
├── backup/
│   ├── scheduler.py
│   ├── verifier.py
│   ├── retention.py
│   └── restore_drill.py
├── runbooks/
│   ├── registry.py
│   ├── executor.py
│   ├── validator.py
│   └── builtin/
└── upgrades/
    ├── readiness.py
    ├── preflight.py
    └── postflight.py
```

---

# 5. Operations State

Globalny stan:

```text
HEALTHY
DEGRADED
MAINTENANCE
INCIDENT
RECOVERING
CRITICAL
```

Każda zmiana stanu musi emitować event.

---

# 6. Health Registry

Monitoruj co najmniej:

```text
Control Plane
REST API
WebSocket
SQLite
Event Bus
Task Scheduler
Agent Scheduler
Workers
Providers
Tool Runtime
MCP
Connectors
Memory
Vector Store
Artifact Store
Git Worktrees
Backups
Disk
RAM
CPU
Network
SSH
Tailscale
Docker
```

---

# 7. Health Check Model

Każdy check:

```text
check_id
component
severity
interval
timeout
expected
remediation_runbook
enabled
```

Wynik:

```text
healthy
degraded
failed
unknown
```

---

# 8. Composite Health Score

Health score może pomagać w UI, ale nie może ukrywać krytycznego failure.

Przykład:

```text
Overall: 92/100
CRITICAL: 0
FAILED: 1
DEGRADED: 2
```

---

# 9. Anomaly Detection

Wykrywaj m.in.:

```text
latency spike
failure-rate spike
worker heartbeat loss
disk growth
memory pressure
provider error spike
tool timeout spike
queue backlog
backup failure
DB integrity issue
```

Nie traktuj każdej anomalii jako incident.

---

# 10. Incident Engine

Incident:

```text
incident_id
title
severity
status
component
detected_at
symptoms
evidence
suspected_causes
affected_tasks
runbook
timeline
resolution
```

Status:

```text
open
diagnosing
mitigating
monitoring
resolved
escalated
```

---

# 11. Severity

```text
SEV4 informational
SEV3 degraded
SEV2 major
SEV1 critical
```

SEV1 nie może być automatycznie „zamknięty” tylko dlatego, że pojedynczy check wrócił do normy.

---

# 12. Diagnosis Engine

Koreluj:
- health checks,
- events,
- logs,
- recent deploys,
- config changes,
- provider failures,
- worker state,
- resource pressure.

Wynik ma rozróżniać:

```text
observed facts
hypotheses
confidence
missing evidence
```

---

# 13. No Hallucinated Root Cause

Nigdy nie raportuj hipotezy jako potwierdzonego root cause bez dowodu.

---

# 14. Runbook Registry

Runbook jest wersjonowanym, walidowanym workflow operacyjnym.

```text
runbook_id
name
version
trigger
risk_level
required_capabilities
steps
verification
rollback
approval_policy
```

---

# 15. Built-in Runbooks

Przygotuj co najmniej:

```text
restart-agentbox-component
restart-worker
reconnect-worker
provider-failover
clear-safe-cache
rotate-logs
cleanup-expired-artifacts
cleanup-orphan-worktrees
verify-database
backup-now
verify-backup
restore-drill
disk-pressure
queue-backlog
tool-quarantine
connector-reconnect
mcp-reconnect
```

---

# 16. Runbook Safety

Każdy runbook musi mieć:
- preconditions,
- risk,
- idempotency,
- timeout,
- rollback,
- verification.

---

# 17. Runbook Dry Run

```bash
agent5 runbook run RUNBOOK --dry-run
```

Pokazuje plan bez wykonania.

---

# 18. Autonomous Remediation Levels

```text
L0 OBSERVE
L1 RECOMMEND
L2 AUTO_LOW_RISK
L3 AUTO_MODERATE_WITH_POLICY
L4 HIGH_RISK_APPROVAL_ONLY
```

Domyślnie:

```text
L2
```

---

# 19. Low-Risk Examples

Potencjalnie autonomiczne:
- rotacja logów,
- usunięcie expired cache,
- ponowny health check,
- retry transient provider,
- cleanup znanego orphan temp directory.

Tylko w dozwolonych granicach.

---

# 20. High-Risk Examples

Approval:
- DB restore,
- package upgrade,
- firewall/network changes,
- worker removal,
- deleting persistent artifacts,
- Git destructive cleanup,
- credential rotation.

---

# 21. Remediation Pipeline

```text
detect
↓
diagnose
↓
select runbook
↓
validate preconditions
↓
risk/policy
↓
approval if required
↓
checkpoint
↓
execute
↓
verify
↓
rollback if needed
↓
report
```

---

# 22. Verification Is Mandatory

Remediation bez verification nie jest sukcesem.

Przykład:

```text
restart API
↓
process exists
↓
health endpoint passes
↓
WebSocket passes
↓
mark resolved
```

---

# 23. Predictive Maintenance

Wykorzystuj historię metrics do prognozowania:

```text
disk exhaustion
artifact growth
DB growth
queue saturation
worker capacity
provider budget exhaustion
```

---

# 24. Forecast Windows

```text
1h
24h
7d
30d
```

Nie przedstawiaj prognozy jako pewności.

---

# 25. Resource Forecasting

CPU/RAM/disk/network:
- trend,
- peak,
- saturation,
- headroom.

---

# 26. Capacity Planning

Raport:

```text
current capacity
current demand
peak demand
headroom
projected saturation
recommended action
```

---

# 27. Queue Capacity

Monitoruj:

```text
pending tasks
running tasks
wait time
worker utilization
blocked tasks
```

---

# 28. Storage Pressure

Poziomy:

```text
NORMAL
WARNING
HIGH
CRITICAL
```

Akcje muszą być stopniowe.

Nigdy nie zaczynaj od agresywnego kasowania.

---

# 29. Cleanup Order

Preferowana kolejność:

```text
expired temp
expired cache
rotated logs beyond retention
expired benchmark artifacts
orphan worktrees after verification
```

Persistent user/project artifacts wymagają policy.

---

# 30. Retention Policies

Oddzielne dla:

```text
logs
artifacts
benchmarks
backups
temporary files
task workspaces
```

---

# 31. Smart Backup Scheduler

Backup powinien brać pod uwagę:
- czas od ostatniego backupu,
- liczbę zmian,
- przed upgrade,
- przed migration,
- przed high-risk remediation.

---

# 32. Backup Scope

Co najmniej:

```text
SQLite
configs
policies
prompt/workflow versions
tool registry
worker registry
memory metadata
critical manifests
```

---

# 33. Backup Verification

Backup nie jest valid tylko dlatego, że plik istnieje.

Sprawdź:
- checksum,
- readability,
- SQLite integrity where applicable,
- manifest completeness.

---

# 34. Restore Drills

Okresowo testuj restore w izolacji.

Nie nadpisuj production podczas drill.

---

# 35. Restore Drill Result

```text
PASS
WARN
FAIL
```

---

# 36. Configuration Drift

Canonical config snapshot + current config.

Wykrywaj:
- unexpected change,
- missing key,
- changed permission,
- disabled safety flag.

---

# 37. Drift Categories

```text
EXPECTED
AUTHORIZED
UNKNOWN
DANGEROUS
```

---

# 38. Worker Drift

Porównuj:
- AgentBox protocol,
- Python/runtime,
- tools,
- capabilities,
- config,
- labels.

---

# 39. Provider Drift

Monitoruj:
- model availability,
- auth health,
- endpoint behavior,
- latency,
- error rate.

---

# 40. Tool Drift

Wykrywaj:
- version changes,
- missing binary,
- capability changes,
- health degradation.

Integracja z v5.4.

---

# 41. Dependency Drift

Dla Python/npm/system dependencies:
- lockfile vs installed,
- security-sensitive unexpected changes,
- incompatible upgrades.

Nie aktualizuj automatycznie wszystkiego.

---

# 42. Upgrade Readiness

Przed upgrade:

```text
health
DB integrity
backup
disk space
worker compatibility
provider status
tool compatibility
benchmark baseline
pending critical tasks
```

---

# 43. Upgrade Readiness Status

```text
READY
READY_WITH_WARNINGS
BLOCKED
```

---

# 44. Integration with v5.5

Przed promocją upgrade:
- regression suite,
- golden tasks,
- quality gate.

Po upgrade:
- postflight benchmark.

---

# 45. Maintenance Windows

Obsługuj:
- immediate,
- scheduled,
- recurring.

---

# 46. Maintenance Mode

Podczas maintenance:
- nie przyjmuj nowych risky tasks,
- pozwól zakończyć bezpieczne active tasks lub je checkpointuj,
- dashboard pokazuje stan.

---

# 47. Task Drain

```text
maintenance requested
↓
stop new assignments
↓
checkpoint active tasks
↓
wait/terminate according to policy
↓
maintenance
```

---

# 48. Worker Drain

```bash
agent5 worker drain WORKER_ID
```

---

# 49. Self-Healing Limits

Maksymalna liczba automatycznych prób.

Przykład:

```text
max_auto_remediation_attempts = 2
```

Potem eskalacja.

---

# 50. Loop Detection

Jeśli:

```text
remediate → fail → remediate → fail
```

STOP i escalate.

---

# 51. Circuit Breaker

Dla niestabilnego komponentu:
- stop repeated action,
- mark degraded,
- fallback,
- alert/operator report.

---

# 52. Change Freeze

W czasie SEV1 można aktywować:

```text
change_freeze=true
```

Blokuje nieistotne zmiany.

---

# 53. Operations Policies

Przykład:

```yaml
operations:
  autonomy_level: L2
  max_auto_remediation_attempts: 2
  allow_auto_log_rotation: true
  allow_auto_cache_cleanup: true
  allow_auto_package_upgrade: false
  allow_auto_db_restore: false
```

---

# 54. Operations Budget

Maintenance ma własne limity:

```text
runtime
API cost
CPU
network
disk writes
```

---

# 55. Maintenance Priority

Production incidents > production tasks > scheduled maintenance > benchmarks.

---

# 56. Operations SQLite

```sql
CREATE TABLE IF NOT EXISTS incidents (
    id TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    severity TEXT NOT NULL,
    status TEXT NOT NULL,
    component TEXT,
    symptoms_json TEXT,
    evidence_json TEXT,
    suspected_causes_json TEXT,
    resolution_json TEXT,
    detected_at TEXT NOT NULL,
    resolved_at TEXT
);

CREATE TABLE IF NOT EXISTS runbooks (
    id TEXT NOT NULL,
    version INTEGER NOT NULL,
    name TEXT NOT NULL,
    risk_level TEXT NOT NULL,
    definition_json TEXT NOT NULL,
    enabled INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY(id, version)
);

CREATE TABLE IF NOT EXISTS remediation_runs (
    id TEXT PRIMARY KEY,
    incident_id TEXT,
    runbook_id TEXT NOT NULL,
    runbook_version INTEGER NOT NULL,
    status TEXT NOT NULL,
    risk_level TEXT,
    approval_id TEXT,
    result_json TEXT,
    started_at TEXT,
    finished_at TEXT
);

CREATE TABLE IF NOT EXISTS health_samples (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    check_id TEXT NOT NULL,
    component TEXT NOT NULL,
    status TEXT NOT NULL,
    value_json TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS drift_events (
    id TEXT PRIMARY KEY,
    drift_type TEXT NOT NULL,
    target TEXT NOT NULL,
    classification TEXT NOT NULL,
    before_hash TEXT,
    after_hash TEXT,
    details_json TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS backup_records (
    id TEXT PRIMARY KEY,
    backup_type TEXT NOT NULL,
    path TEXT NOT NULL,
    checksum TEXT,
    status TEXT NOT NULL,
    verified_at TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
```

---

# 57. Events

```text
operations.state_changed
health.degraded
health.recovered
incident.created
incident.escalated
incident.resolved
remediation.started
remediation.completed
remediation.failed
remediation.rolled_back
drift.detected
backup.created
backup.verified
backup.failed
restore_drill.completed
capacity.warning
maintenance.started
maintenance.completed
```

---

# 58. Metrics

```text
agentbox_health_check_failures_total
agentbox_incidents_total
agentbox_incident_resolution_seconds
agentbox_remediations_total
agentbox_remediation_failures_total
agentbox_drift_events_total
agentbox_backup_failures_total
agentbox_disk_pressure
agentbox_queue_depth
agentbox_worker_utilization
```

---

# 59. CLI — Operations

```bash
agent5 ops status
agent5 ops health
agent5 ops incidents
agent5 ops incident show ID
agent5 ops diagnose ID
agent5 ops autopilot status
agent5 ops autopilot enable
agent5 ops autopilot disable
```

Enable/disable musi respektować permissions.

---

# 60. CLI — Runbooks

```bash
agent5 runbook list
agent5 runbook show ID
agent5 runbook validate ID
agent5 runbook run ID --dry-run
agent5 runbook run ID
```

---

# 61. CLI — Maintenance

```bash
agent5 maintenance status
agent5 maintenance plan
agent5 maintenance enter
agent5 maintenance exit
agent5 maintenance readiness
```

---

# 62. CLI — Drift

```bash
agent5 drift status
agent5 drift config
agent5 drift workers
agent5 drift tools
agent5 drift providers
```

---

# 63. CLI — Backup

```bash
agent5 backup status
agent5 backup create
agent5 backup verify BACKUP_ID
agent5 backup drill BACKUP_ID
```

---

# 64. Dashboard — Operations

Nowa główna sekcja:

```text
Operations
```

Karty:
- Platform Health
- Active Incidents
- Autopilot
- Maintenance
- Capacity
- Backups
- Drift
- Runbooks.

---

# 65. Health Dashboard

Pokaż:
- component,
- status,
- last check,
- latency,
- failures,
- trend.

---

# 66. Incident Detail

```text
Summary
Severity
Timeline
Evidence
Affected components
Suspected causes
Remediation
Verification
Rollback
```

---

# 67. Autopilot Dashboard

Pokazuje:

```text
Autonomy Level
Allowed automatic actions
Blocked actions
Recent remediations
Success rate
Escalations
```

---

# 68. Capacity Dashboard

Wykresy:
- CPU,
- RAM,
- disk,
- queue,
- workers,
- projected saturation.

---

# 69. Backup Dashboard

```text
Last backup
Last verified backup
Restore drill
Retention
Next scheduled backup
```

---

# 70. Drift Dashboard

Tabela:

```text
Target
Type
Classification
Detected
Before
After
Status
```

---

# 71. API

```text
GET  /api/v1/operations/status
GET  /api/v1/operations/health
GET  /api/v1/incidents
GET  /api/v1/incidents/{id}
POST /api/v1/incidents/{id}/diagnose

GET  /api/v1/runbooks
POST /api/v1/runbooks/{id}/execute

GET  /api/v1/drift
GET  /api/v1/capacity
GET  /api/v1/backups
POST /api/v1/backups
POST /api/v1/backups/{id}/verify
```

---

# 72. WebSocket

Live events dla:
- health,
- incidents,
- remediation,
- capacity,
- backup,
- drift.

---

# 73. Alert Deduplication

Nie spamuj tym samym incidentem.

Fingerprint:
- component,
- check,
- error class,
- time window.

---

# 74. Alert Suppression

Maintenance window może tłumić oczekiwane alerts, ale nie SEV1 safety failures.

---

# 75. Incident Correlation

Powiąż np.:

```text
disk pressure
→ DB latency
→ task failures
```

zamiast trzech niezależnych incidentów, jeśli dowody wskazują wspólne źródło.

---

# 76. Operations Memory

Zapamiętuj:
- incidents,
- skuteczne runbooki,
- failed remediation,
- recurring patterns.

---

# 77. Outcome Learning

v5.5 evaluation może mierzyć skuteczność runbooków.

---

# 78. Runbook Reliability

Score:
- executions,
- successes,
- rollbacks,
- failures,
- avg recovery time.

---

# 79. Safe Runbook Evolution

Zmiana runbooka:

```text
proposal
→ test
→ simulation
→ approval
→ canary
→ active
```

Integracja z v5.5.

---

# 80. Simulation Mode

Runbook powinien mieć możliwość testowania na fixture/sandbox, gdy jest to możliwe.

---

# 81. Chaos Tests

Kontrolowane testy:
- worker offline,
- provider unavailable,
- disk near threshold,
- tool unavailable,
- API restart.

Nie wykonywać destrukcyjnego chaos test na produkcji bez approval.

---

# 82. Failure Injection

Tylko w test environment/fixture.

---

# 83. Recovery Objectives

Konfigurowalne:

```text
RTO
RPO
```

Nie deklaruj ich spełnienia bez pomiaru.

---

# 84. Startup Recovery

Po restarcie:
- load incidents,
- recover maintenance state,
- inspect incomplete remediation,
- verify locks,
- resume safe monitoring.

---

# 85. Incomplete Remediation

Nigdy nie zakładaj, że interrupted remediation się udała.

Status:

```text
UNKNOWN_NEEDS_VERIFICATION
```

---

# 86. Locking

Zapobiegaj równoległym sprzecznym maintenance operations.

---

# 87. Idempotency

Runbooki powinny być idempotentne tam, gdzie możliwe.

---

# 88. Audit Trail

Każda operacja:

```text
actor
reason
incident
runbook
approval
commands/tools
result
verification
rollback
```

Sekrety redagowane.

---

# 89. Security Boundary

Operations Autopilot korzysta wyłącznie z capabilities nadanych przez Tool Runtime/Policy Engine.

Nie daje sobie nowych uprawnień.

---

# 90. SSH/Tailscale Safety

Nie wykonuj autonomicznie zmian mogących odciąć jedyny dostęp SSH/Tailscale.

Takie zmiany:

```text
CRITICAL
approval required
rollback plan required
```

---

# 91. Docker Safety

Nie używaj automatycznie:

```text
docker system prune -a
```

Preferuj targetowane cleanup.

---

# 92. Git Safety

Nie używaj automatycznie:

```text
git reset --hard
git clean -fd
git push --force
```

---

# 93. SQLite Safety

Przed migration/repair/restore:
- backup,
- integrity check,
- maintenance mode.

---

# 94. Provider Failover

Jeśli provider degraded:
- circuit breaker,
- route new work elsewhere,
- preserve current task state,
- retry according to policy.

---

# 95. Worker Recovery

Lost worker:
- mark unavailable,
- wait lease timeout,
- recover task from checkpoint,
- reassign.

---

# 96. Tool Recovery

Unhealthy tool:
- quarantine,
- fallback capability-equivalent tool,
- report.

---

# 97. Artifact Recovery

Sprawdź checksum i provenance.

Nie używaj uszkodzonego artifact jako recovery source.

---

# 98. Scheduled Maintenance

Scheduler powinien respektować:
- active critical tasks,
- maintenance windows,
- backups,
- worker load.

---

# 99. Maintenance Plan

Generuj:

```text
MAINTENANCE_PLAN_<timestamp>.md
```

---

# 100. Incident Report

Po resolved:

```text
INCIDENT_REPORT_<id>.md
```

Zawiera:
- timeline,
- evidence,
- root cause status,
- mitigation,
- remediation,
- verification,
- prevention actions.

---

# 101. Daily Operations Report

Opcjonalny:

```text
OPERATIONS_DAILY_<date>.md
```

---

# 102. Upgrade Readiness Report

```text
UPGRADE_READINESS_<version>.md
```

---

# 103. Feature Flags

```ini
[operations]
autopilot = true
autonomy_level = "L2"
predictive_maintenance = true
drift_detection = true
smart_backups = true
restore_drills = true
auto_cleanup = true
auto_package_upgrades = false
auto_db_restore = false
```

---

# 104. Default Safe Configuration

Najbardziej destrukcyjne automatyzacje domyślnie OFF.

---

# 105. Tests

```text
tests/operations/
├── test_health.py
├── test_incidents.py
├── test_diagnosis.py
├── test_runbooks.py
├── test_remediation.py
├── test_verification.py
├── test_rollback.py
├── test_drift.py
├── test_capacity.py
├── test_backups.py
├── test_restore_drill.py
├── test_maintenance.py
├── test_autopilot_policy.py
└── test_loop_detection.py
```

---

# 106. Smoke Test A — Health

```text
healthy component
↓
health PASS
```

---

# 107. Smoke Test B — Low-Risk Remediation

```text
safe cache issue
↓
detect
↓
L2 policy allows
↓
runbook
↓
verify
↓
resolved
```

---

# 108. Smoke Test C — High-Risk Approval

```text
DB restore required
↓
HIGH
↓
approval gate
↓
no execution before approval
```

---

# 109. Smoke Test D — Failed Remediation

```text
runbook fails
↓
verification FAIL
↓
rollback
↓
escalate
```

---

# 110. Smoke Test E — Loop Detection

```text
two failed auto attempts
↓
circuit breaker
↓
escalate
```

---

# 111. Smoke Test F — Drift

```text
config unexpectedly changed
↓
drift detected
↓
classified
↓
operator visible
```

---

# 112. Smoke Test G — Backup

```text
backup
↓
checksum
↓
verify
↓
restore drill in isolation
```

---

# 113. Smoke Test H — Worker Failure

```text
worker heartbeat lost
↓
lease expires
↓
checkpoint recovery
↓
task reassigned
```

---

# 114. Acceptance Criteria

v5.6 jest gotowa, jeśli:

- [ ] health registry działa
- [ ] anomaly detection działa
- [ ] incident engine działa
- [ ] diagnosis oddziela fakty od hipotez
- [ ] runbook registry działa
- [ ] runbook validation działa
- [ ] low-risk auto remediation działa
- [ ] high-risk approval działa
- [ ] verification jest obowiązkowe
- [ ] rollback działa
- [ ] loop detection działa
- [ ] circuit breaker działa
- [ ] predictive maintenance działa
- [ ] capacity forecasting działa
- [ ] drift detection działa
- [ ] smart backups działają
- [ ] backup verification działa
- [ ] restore drills działają
- [ ] maintenance mode działa
- [ ] task/worker drain działa
- [ ] dashboard Operations działa
- [ ] API/WebSocket działa
- [ ] audit trail działa
- [ ] operations selftest PASS
- [ ] v5.5 regression gate PASS

---

# 115. Self-Test

```bash
agent5 selftest --operations
```

Sprawdza:

```text
health
incidents
diagnosis
runbooks
policy
approvals
remediation
verification
rollback
drift
capacity
backup
restore drill
maintenance
worker recovery
tool recovery
```

---

# 116. Deployment Guard

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

Nie zakładaj systemd.

---

# 117. Backup Before v5.6

Przed wdrożeniem:
- DB backup,
- config backup,
- policies,
- v5.5 evaluation state,
- tool/worker registry,
- current release,
- checksum manifest.

---

# 118. Upgrade Sequence

```text
deployment guard
↓
v5.5 selftest
↓
backup + verify
↓
upgrade readiness
↓
maintenance mode
↓
DB migration
↓
install operations modules
↓
register safe runbooks
↓
operations selftest
↓
smoke tests
↓
v5.5 golden/regression suite
↓
activate L1
↓
observe
↓
promote to L2 after verification
```

Nie włączaj od razu agresywnej autonomii.

---

# 119. Rollback

Jeśli v5.6 failuje:

```text
disable autopilot
↓
stop remediation queue
↓
preserve incidents/audit
↓
restore config/DB if required
↓
switch release
↓
v5.5 remains operational
```

---

# 120. Final Deployment Report

Po wdrożeniu wygeneruj:

```text
OPERATIONS_AUTOPILOT_REPORT_v5.6.0.md
```

Zawiera:

```text
Version
Environment
Health checks
Runbooks
Autonomy level
Policies
Incidents
Backups
Restore drill
Drift
Capacity
Smoke tests
Regression results
Warnings
Rollback path
```

---

# 121. Definition of Done

Nie uznawaj v5.6 za wdrożoną wyłącznie dlatego, że pliki istnieją.

Rozróżniaj:

```text
FILES INSTALLED
MIGRATION PASSED
SELFTEST PASSED
SMOKE TESTS PASSED
REGRESSION GATE PASSED
AUTOPILOT L1 ACTIVE
AUTOPILOT L2 VERIFIED
PRODUCTION READY
```

---

# 122. Następny etap roadmapy

## AgentBox v5.7 — Governance, Security Intelligence & Enterprise Control Plane

Planowany zakres:

```text
RBAC v2
Fine-Grained Permissions
Policy-as-Code
Secrets Governance
Security Posture
Threat/Anomaly Correlation
Supply-Chain Controls
SBOM
Dependency Provenance
Signed Artifacts
Audit Export
Compliance Profiles
Multi-Tenant Isolation
Organization/Team Scopes
Approval Delegation
Break-Glass Procedures
Enterprise Governance Dashboard
```

v5.7 powinno wykorzystać v5.6 Operations Autopilot, ale umieścić jego autonomię w jeszcze silniejszym modelu governance, security i audytu.
