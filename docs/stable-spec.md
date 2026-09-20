# AgentBox v5.0 Stable — Production Hardening, Recovery & Release Engineering

**Środowisko docelowe:** AgentBox  
**SSH:** `100.123.66.15:22`  
**Użytkownik:** `box`  
**Hostname:** `cursor`  
**Root projektu:** `/workspace/agentbox-v5`  
**Poprzednia wersja:** `v5.0-rc1` — REST API + WebSocket + Web Dashboard  
**Nowa wersja:** `v5.0.0 Stable`

> Stable nie jest kolejnym zestawem funkcji. To etap utwardzenia całej platformy AgentBox v5 przed uznaniem jej za wersję produkcyjną. Wszystkie istniejące moduły mają zostać uporządkowane, przetestowane, zabezpieczone, objęte recovery, backupem, migracjami, integralnością danych i procedurami aktualizacji.

---

# 1. Cel wersji Stable

AgentBox v5 Stable ma zapewnić:

- niezawodny start i restart,
- automatyczne wykrywanie uszkodzeń,
- recovery po awarii,
- migracje wersjonowane,
- pełny backup/restore,
- cleanup orphan processes/worktrees,
- integralność SQLite,
- rotację logów,
- retencję artifactów,
- maintenance pamięci,
- trwały upgrade framework,
- rollback framework,
- pełny security hardening,
- end-to-end testy,
- release packaging,
- dokumentację operacyjną,
- wersjonowane raporty wdrożeń.

Docelowy cykl:

```text
BOOT
 ↓
VERIFY
 ↓
RECOVER
 ↓
MIGRATE
 ↓
START
 ↓
HEALTH
 ↓
RUN
 ↓
MONITOR
 ↓
BACKUP
 ↓
MAINTAIN
 ↓
UPGRADE / ROLLBACK
```

---

# 2. Architektura Stable

```text
                         AgentBox v5 Stable
                                 │
                ┌────────────────┼────────────────┐
                │                │                │
             Control          Runtime          Recovery
             Plane            Engine            Engine
                │                │                │
         REST / WS / UI     Scheduler         Backups
                │             Workers          Restore
                │             Agents           Cleanup
                │                │                │
                └──────────────┬─┴───────────────┘
                               ▼
                         Persistent Core
                               │
        ┌───────────────┬──────┼──────┬──────────────┐
        ▼               ▼      ▼      ▼              ▼
      SQLite          Events  Memory Artifacts    Policies
        │               │      │      │              │
        └───────────────┴──────┼──────┴──────────────┘
                               ▼
                           Integrity
                               │
                         Health / Audit
```

---

# 3. Nowe moduły Stable

Dodaj lub wydziel:

```text
agentbox/
├── recovery.py
├── integrity.py
├── backups.py
├── restore.py
├── maintenance.py
├── retention.py
├── migrations.py
├── upgrade.py
├── release.py
├── diagnostics.py
├── lifecycle.py
├── crash_recovery.py
└── security_hardening.py
```

---

# 4. Lifecycle Manager

Wszystkie procesy AgentBox powinny być zarządzane przez jedną warstwę:

```text
agentboxd
agentbox-web
workers
scheduler
sampler
websocket hub
```

Lifecycle Manager odpowiada za:

```text
start
stop
restart
status
health
recover
shutdown
graceful drain
```

---

# 5. Graceful Shutdown

Przy SIGTERM:

```text
stop accepting new tasks
↓
mark scheduler draining
↓
wait for safe checkpoints
↓
pause remaining tasks
↓
flush events
↓
flush metrics
↓
close DB
↓
stop WebSocket
↓
remove PID
```

Timeout:

```text
graceful_shutdown_timeout = 30s
```

Po czasie:

```text
forced shutdown
```

ale musi zostać zapisany event.

---

# 6. Crash Recovery

Przy starcie daemon ma sprawdzić:

```text
tasks status=running
runs status=running
handoffs status=running
workers registered but dead
stale PID files
stale locks
incomplete approvals
orphan worktrees
unfinished DB transactions
```

Przykład:

```text
running task + no worker
→ status = interrupted
→ recoverable = true
→ recovery event
```

---

# 7. Recovery States

Dodaj:

```text
interrupted
recovering
recovered
recovery_failed
orphaned
stale
```

---

# 8. Recovery Policy

Konfiguracja:

```ini
[recovery]
auto_recover_tasks = true
auto_recover_runs = true
auto_cleanup_stale_pids = true
auto_cleanup_orphan_worktrees = false
max_recovery_attempts = 2
recovery_requires_approval_for_high_risk = true
```

---

# 9. SQLite Integrity

Przy starcie:

```sql
PRAGMA quick_check;
```

Regularnie:

```sql
PRAGMA integrity_check;
```

Jeśli wynik nie jest:

```text
ok
```

AgentBox:
1. zatrzymuje scheduler,
2. blokuje mutacje,
3. generuje alert,
4. próbuje recovery z backupu tylko po approval lub jawnej komendzie.

---

# 10. SQLite Backup

Backup online:

```python
sqlite3.Connection.backup(...)
```

Nie kopiować aktywnej bazy prostym `cp`, jeśli DB jest otwarta i używa WAL.

Format:

```text
backups/
└── 2026-09-19T223000/
    ├── agentbox.db
    ├── config.tar.gz
    ├── manifest.json
    ├── version.txt
    └── checksum.sha256
```

---

# 11. Backup Manager

CLI:

```bash
agent5 backup create
agent5 backup list
agent5 backup inspect BACKUP_ID
agent5 backup verify BACKUP_ID
agent5 backup prune
```

Opcjonalnie:

```bash
agent5 backup export BACKUP_ID /workspace/...
```

---

# 12. Backup Manifest

```json
{
  "backup_id": "bkp_20260919_223000",
  "version": "5.0.0",
  "schema_version": 12,
  "created_at": "...",
  "database": "agentbox.db",
  "config": "config.tar.gz",
  "sha256": "...",
  "hostname": "cursor",
  "environment": "AgentBox"
}
```

---

# 13. Automatic Backups

Przykład:

```ini
[backup]
enabled = true
interval_hours = 6
keep_daily = 7
keep_weekly = 4
keep_monthly = 3
before_upgrade = true
before_migration = true
before_restore = true
```

---

# 14. Restore Manager

CLI:

```bash
agent5 restore list
agent5 restore verify BACKUP_ID
agent5 restore BACKUP_ID
```

Restore sequence:

```text
deployment guard
↓
maintenance mode
↓
stop web
↓
stop scheduler/workers
↓
backup current state
↓
verify selected backup
↓
restore DB
↓
restore config
↓
migrate if required
↓
integrity check
↓
selftest
↓
start daemon
↓
start web
```

---

# 15. Maintenance Mode

Nowy globalny stan:

```text
normal
maintenance
degraded
read_only
recovery
```

CLI:

```bash
agent5 maintenance enter
agent5 maintenance exit
agent5 maintenance status
```

W maintenance:
- GET API działa,
- mutacje blokowane,
- scheduler zatrzymany,
- dashboard pokazuje banner.

---

# 16. Migration Framework

Każda migracja jako osobny plik:

```text
agentbox/migrations/
├── 0001_initial.py
├── 0002_handoffs.py
├── 0003_policy_budget_risk.py
├── 0004_web_control_plane.py
└── 0005_stable_hardening.py
```

Każda migracja ma:

```python
version
name
upgrade()
verify()
```

Downgrade tylko jeśli jest naprawdę bezpieczny.

---

# 17. Migration Table

```sql
CREATE TABLE IF NOT EXISTS migrations (
    version INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    applied_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    checksum TEXT NOT NULL
);
```

---

# 18. Migration Safety

Przed migracją:
- backup,
- DB integrity check,
- wolne miejsce,
- daemon stop/drain,
- schema version check.

Po migracji:
- verify(),
- quick_check,
- smoke test,
- migration event.

---

# 19. Upgrade Framework

CLI:

```bash
agent5 upgrade check
agent5 upgrade plan
agent5 upgrade apply
agent5 upgrade status
```

Każde upgrade ma:

```text
preflight
backup
migration
deploy
selftest
health
activate
```

---

# 20. Atomic Release Switching

Rekomendowana struktura:

```text
/workspace/agentbox-releases/
├── v5.0.0-rc1/
├── v5.0.0/
└── current -> v5.0.0
```

Wrappery wskazują na:

```text
/workspace/agentbox-releases/current
```

Dzięki temu rollback aplikacji może być szybki.

---

# 21. Rollback Framework

CLI:

```bash
agent5 rollback plan
agent5 rollback apply
agent5 rollback status
```

Rollback:
- aplikacja,
- config,
- DB tylko z kompatybilnego backupu.

Nigdy nie wykonywać ślepego downgrade schema.

---

# 22. Release Manifest

Każde wydanie:

```json
{
  "version": "5.0.0",
  "build": "stable",
  "schema_version": 12,
  "python_min": "3.11",
  "created_at": "...",
  "files_sha256": "...",
  "migration_required": true
}
```

---

# 23. Process Registry

Dodaj tabelę:

```sql
CREATE TABLE IF NOT EXISTS runtime_processes (
    id TEXT PRIMARY KEY,
    component TEXT NOT NULL,
    pid INTEGER,
    state TEXT NOT NULL,
    started_at TEXT,
    heartbeat_at TEXT,
    metadata_json TEXT
);
```

Procesy:
- daemon,
- web,
- scheduler,
- worker,
- sampler.

---

# 24. Stale PID Cleanup

Przy starcie:

```text
PID file exists
↓
process exists?
├── yes -> validate command/process ownership
└── no  -> remove stale PID
```

Nigdy nie zabijać procesu wyłącznie na podstawie numeru PID bez walidacji.

---

# 25. Lock Manager

Locks:

```text
migration.lock
backup.lock
restore.lock
upgrade.lock
scheduler.lock
```

Lock zawiera:
- PID,
- timestamp,
- operation id,
- hostname.

---

# 26. Orphan Worktree Cleanup

CLI:

```bash
agent5 worktree audit
agent5 worktree prune
```

Kategorie:

```text
active
recoverable
orphaned
safe_to_remove
manual_review
```

Nigdy nie usuwać worktree z uncommitted changes bez backup/artifact.

---

# 27. Artifact Retention

Konfiguracja:

```ini
[retention]
task_artifacts_days = 90
logs_days = 30
metrics_days = 30
events_days = 180
failed_task_artifacts_days = 180
```

Dla ważnych artifactów:

```text
pinned = true
```

Pinned nie jest automatycznie usuwany.

---

# 28. Artifact Integrity

Każdy artifact powinien mieć:

```text
sha256
size
mime
created_at
task_id
run_id
agent_name
```

Przy odczycie opcjonalne verify checksum.

---

# 29. Log Rotation

Logi:

```text
agentboxd.log
web.log
scheduler.log
workers/*.log
security.log
audit.log
```

Rotacja:
- max size,
- max files,
- compress old.

Przykład:

```ini
[logs]
max_size_mb = 50
keep_files = 10
compress = true
```

---

# 30. JSONL Logging

Standard:

```json
{
  "ts": "...",
  "level": "INFO",
  "component": "scheduler",
  "event": "task.started",
  "task_id": "tsk_...",
  "run_id": "run_...",
  "request_id": null,
  "message": "..."
}
```

---

# 31. Secret Redaction

Centralny filtr usuwa:
- API keys,
- bearer tokens,
- passwords,
- cookies,
- secret env vars,
- known credential patterns.

Nie logować całych env.

---

# 32. Memory Maintenance

Memory Engine dostaje maintenance:

```bash
agent5 memory stats
agent5 memory compact
agent5 memory deduplicate
agent5 memory verify
```

Cel:
- usuwanie duplikatów,
- oznaczanie stale memory,
- kompaktowanie indeksów,
- zachowanie provenance.

---

# 33. Memory Retention

Kategorie:
- permanent project decisions,
- temporary task context,
- run scratch data.

Nie wszystko ma być trwałe.

---

# 34. Event Compaction

Stare telemetry events mogą być agregowane.

Przykład:

```text
raw metrics 30 days
hourly aggregates 90 days
daily aggregates 1 year
```

Nie kompaktować:
- security events,
- approvals,
- policy denies,
- merge history.

---

# 35. Scheduler Recovery

Po restart:
- queued pozostają queued,
- blocked pozostają blocked,
- running bez worker -> interrupted,
- interrupted może być recovered.

---

# 36. Worker Recovery

Worker heartbeat:

```text
worker heartbeat every 5s
worker considered stale after 30s
```

Stale worker:
- run interrupted,
- task recovery policy.

---

# 37. Provider Failure Handling

Stany:

```text
healthy
degraded
rate_limited
unavailable
auth_failed
```

Circuit breaker:

```text
N failures
↓
provider temporarily disabled
↓
cooldown
↓
health probe
↓
re-enable
```

---

# 38. Provider Fallback

Jeśli policy zezwala:

```text
Claude unavailable
↓
Codex fallback
```

Ale tylko:
- kompatybilna rola,
- zgodny budget,
- approval policy.

---

# 39. Health Model

Global health:

```text
HEALTHY
DEGRADED
UNHEALTHY
MAINTENANCE
RECOVERING
```

---

# 40. Health Endpoint Stable

```text
GET /api/v1/health
```

Rozszerzony:

```json
{
  "status": "degraded",
  "components": {
    "database": "healthy",
    "scheduler": "healthy",
    "websocket": "healthy",
    "provider_claude": "degraded",
    "backup": "healthy"
  }
}
```

---

# 41. Diagnostics Bundle

CLI:

```bash
agent5 diagnostics create
```

Generuje:

```text
diagnostics/
├── health.json
├── version.json
├── schema.json
├── processes.json
├── daemon-tail.log
├── web-tail.log
├── scheduler-tail.log
├── recent-errors.json
└── manifest.json
```

Bez sekretów.

---

# 42. Self-Healing

Dozwolone automatyczne działania:
- stale PID cleanup,
- stale lock cleanup,
- worker restart,
- provider health retry,
- WebSocket restart,
- index rebuild.

Niedozwolone bez approval:
- DB restore,
- destructive cleanup,
- deleting worktree with changes,
- policy bypass.

---

# 43. Security Hardening

Stable musi wymusić:

```text
Tailscale-only dashboard
auth required
session expiry
CSRF protection
same-origin
rate limiting
secret redaction
path traversal prevention
workspace-only writes
admin-only policy mutation
admin-only settings mutation
audit trail
```

---

# 44. File Permissions

Przykład:

```text
config          700
secrets         700
admin.token     600
database        600/640
backups         700
runtime pids    700
```

---

# 45. HTTP Security Headers

Dashboard:

```text
Content-Security-Policy
X-Content-Type-Options: nosniff
Referrer-Policy
X-Frame-Options / frame-ancestors
Permissions-Policy
```

---

# 46. CSP

Minimalnie:
- brak inline scripts, jeśli możliwe,
- brak remote CDN,
- assets lokalne.

---

# 47. API Hardening

- strict Pydantic schemas,
- request size limits,
- pagination limits,
- file download limits,
- WebSocket connection limit,
- timeout dla API calls,
- no traceback exposure.

---

# 48. WebSocket Hardening

- auth,
- max message size,
- heartbeat,
- idle timeout,
- subscription validation,
- per-client rate limit.

---

# 49. Database Hardening

Przy połączeniu:

```text
foreign_keys=ON
journal_mode=WAL
busy_timeout
synchronous=NORMAL/FULL według testów
```

Regular:
- quick_check,
- backup,
- checkpoint WAL.

---

# 50. Dashboard Stable

Dashboard powinien dostać:
- global health banner,
- backup status,
- recovery status,
- maintenance mode,
- release version,
- migration status,
- diagnostics panel.

---

# 51. New Dashboard Sections

```text
System Health
Backups
Recovery
Diagnostics
Releases
Maintenance
```

---

# 52. Backup UI

Pokazuje:

```text
Backup ID
Version
Schema
Created
Size
Verified
```

Akcje:
- verify,
- download/export,
- restore request.

Restore zawsze approval + confirmation.

---

# 53. Recovery UI

Pokazuje:
- interrupted tasks,
- orphan workers,
- stale worktrees,
- stale locks,
- recoverable runs.

---

# 54. Release UI

Pokazuje:

```text
Current: 5.0.0
Previous: 5.0.0-rc1
Schema: 12
Upgrade status: healthy
```

---

# 55. Maintenance UI

Admin może:
- enter maintenance,
- exit maintenance,
- run integrity,
- run backup,
- run cleanup,
- create diagnostics.

---

# 56. CLI Stable

Dodaj:

```bash
agent5 health
agent5 integrity check
agent5 integrity full
```

```bash
agent5 backup create
agent5 backup list
agent5 backup verify ID
agent5 backup prune
```

```bash
agent5 restore verify ID
agent5 restore ID
```

```bash
agent5 recovery status
agent5 recovery scan
agent5 recovery apply
```

```bash
agent5 maintenance enter
agent5 maintenance exit
```

```bash
agent5 diagnostics create
```

```bash
agent5 release info
agent5 upgrade plan
agent5 rollback plan
```

---

# 57. Deployment Guard

Nadal obowiązkowy:

```bash
agentbox-deploy-guard
```

Stable deploy ma przerwać się jeśli:
- hostname != cursor,
- user != box,
- Tailscale IP mismatch,
- root missing.

---

# 58. Stable Preflight

Przed upgrade:

```text
deployment guard PASS
beta/rc selftest PASS
database quick_check PASS
disk free sufficient
backup writable
no migration running
no restore running
no unresolved critical recovery
```

---

# 59. Disk Space Guard

Upgrade powinien wymagać np.:

```text
minimum free = max(
  2 GB,
  3 x database size,
  release size + backup size
)
```

---

# 60. Stable Backup Before Upgrade

Obowiązkowo:
- DB online backup,
- config,
- current release manifest,
- selected artifacts metadata,
- checksums.

---

# 61. Stable Deployment Sequence

```text
VERIFY HOST
↓
PREFLIGHT
↓
DRAIN
↓
BACKUP
↓
MAINTENANCE MODE
↓
STOP WEB
↓
STOP WORKERS
↓
STOP DAEMON
↓
INSTALL RELEASE
↓
MIGRATE
↓
INTEGRITY CHECK
↓
SELFTEST
↓
START DAEMON
↓
START WEB
↓
HEALTH PROBE
↓
END-TO-END TEST
↓
EXIT MAINTENANCE
↓
MARK RELEASE ACTIVE
```

---

# 62. Canary Test

Po starcie Stable uruchom testowe zadanie:

```text
read-only task
↓
planner
↓
handoff
↓
policy
↓
artifact
↓
approval simulation
↓
complete
```

Nie używać od razu RacOS do pierwszego testu.

---

# 63. End-to-End Tests

Dodaj:

```text
tests/e2e/
├── test_task_lifecycle.py
├── test_handoff_lifecycle.py
├── test_approval_lifecycle.py
├── test_policy_deny.py
├── test_budget_pause.py
├── test_websocket_live.py
├── test_backup_restore.py
├── test_crash_recovery.py
├── test_daemon_restart.py
├── test_web_restart.py
├── test_worker_recovery.py
└── test_upgrade_rollback.py
```

---

# 64. Chaos Tests

Kontrolowane:
- kill worker,
- kill web,
- kill daemon,
- provider failure,
- DB busy,
- network interruption,
- stale PID,
- stale lock.

System ma wrócić do stabilnego stanu.

---

# 65. Backup Restore Test

Nie wystarczy tworzyć backup.

Stable wymaga automatycznego testu:
1. backup,
2. restore do temporary DB,
3. integrity check,
4. schema check.

Dopiero wtedy backup:

```text
verified = true
```

---

# 66. Regression Suite

Każdy moduł beta1-beta3 + rc1:
- memory,
- context,
- agents,
- scheduler,
- handoffs,
- observability,
- policy,
- budget,
- risk,
- approvals,
- API,
- WebSocket,
- dashboard.

---

# 67. Release Acceptance Criteria

Stable można oznaczyć tylko jeśli:

- [ ] full migration PASS
- [ ] DB integrity PASS
- [ ] backup creation PASS
- [ ] backup verify PASS
- [ ] restore dry-run PASS
- [ ] crash recovery PASS
- [ ] stale PID recovery PASS
- [ ] stale lock recovery PASS
- [ ] orphan worker recovery PASS
- [ ] worktree audit PASS
- [ ] provider health PASS
- [ ] policy regression PASS
- [ ] budget regression PASS
- [ ] approvals regression PASS
- [ ] REST API PASS
- [ ] WebSocket PASS
- [ ] dashboard PASS
- [ ] iPhone dashboard PASS
- [ ] Tailscale-only access PASS
- [ ] security hardening PASS
- [ ] log redaction PASS
- [ ] backup retention PASS
- [ ] artifact retention PASS
- [ ] memory maintenance PASS
- [ ] E2E suite PASS
- [ ] release rollback plan verified
- [ ] documentation complete

---

# 68. Stable Self-Test

```bash
agent5 selftest --full
```

Docelowo:

```text
AgentBox v5.0.0

Core
[OK] database
[OK] migrations
[OK] daemon
[OK] scheduler
[OK] workers
[OK] agent registry
[OK] memory
[OK] context builder

Execution
[OK] handoffs
[OK] policies
[OK] budgets
[OK] risk
[OK] approvals
[OK] enforcement

Control Plane
[OK] REST API
[OK] WebSocket
[OK] dashboard
[OK] authentication

Operations
[OK] backups
[OK] restore verification
[OK] integrity
[OK] recovery
[OK] maintenance
[OK] retention
[OK] log rotation
[OK] diagnostics

Security
[OK] Tailscale bind
[OK] session security
[OK] secret redaction
[OK] path safety
[OK] permission checks

RESULT: PASS
```

---

# 69. Stable Versioning

Wersja:

```text
5.0.0
```

Nie:

```text
5.0.0-stable
```

Release metadata może mieć:

```text
channel = stable
```

---

# 70. Release Notes

Wygenerować:

```text
RELEASE_NOTES_v5.0.0.md
```

Zawartość:
- architecture,
- features,
- migrations,
- compatibility,
- known limitations,
- upgrade path,
- rollback,
- security notes.

---

# 71. Operator Runbook

Utworzyć:

```text
docs/OPERATIONS.md
```

Sekcje:
- start/stop,
- health,
- logs,
- backup,
- restore,
- recovery,
- approvals,
- maintenance,
- upgrade,
- rollback.

---

# 72. Disaster Recovery Runbook

```text
docs/DISASTER_RECOVERY.md
```

Scenariusze:
- DB corruption,
- disk full,
- lost worktree,
- daemon crash loop,
- broken upgrade,
- provider outage,
- backup restore.

---

# 73. Security Runbook

```text
docs/SECURITY.md
```

Obejmuje:
- token rotation,
- session revoke,
- secret exposure,
- suspicious request,
- policy deny spike,
- provider auth issue.

---

# 74. Architecture Documentation

```text
docs/ARCHITECTURE.md
```

Powinno opisywać:
- control plane,
- scheduler,
- agents,
- handoffs,
- memory,
- policy,
- risk,
- budget,
- observability,
- recovery.

---

# 75. API Documentation

```text
docs/API.md
```

plus OpenAPI.

---

# 76. Database Documentation

```text
docs/DATABASE.md
```

Zawiera:
- tables,
- relationships,
- schema versions,
- migration rules.

---

# 77. Stable Release Package

Przykład:

```text
agentbox-v5.0.0/
├── agentbox/
├── web/
├── migrations/
├── scripts/
├── tests/
├── docs/
├── config/
├── install.sh
├── upgrade.sh
├── rollback.sh
├── uninstall.sh
├── VERSION
├── RELEASE_MANIFEST.json
└── README.md
```

---

# 78. Checksums

Release:

```text
SHA256SUMS
```

Installer powinien weryfikować pliki release przed aktywacją.

---

# 79. Install Script

`install.sh`:
- deployment guard,
- preflight,
- backup existing,
- dependencies,
- config,
- database,
- migrate,
- selftest,
- activate.

---

# 80. Upgrade Script

`upgrade.sh`:
- source version check,
- target version check,
- backup,
- migration,
- validation,
- activation,
- rollback on failure.

---

# 81. Rollback Script

`rollback.sh`:
- validate previous release,
- check schema compatibility,
- restore config,
- restore DB backup if needed,
- switch current symlink,
- selftest.

---

# 82. Uninstall

`uninstall.sh` nie usuwa danych domyślnie.

Opcje:

```text
--keep-data
--purge-data
```

`--purge-data` wymaga dodatkowego potwierdzenia.

---

# 83. Stable Dashboard URL

Docelowo:

```text
http://100.123.66.15:8787
```

lub bezpieczniejszy hostname Tailscale/MagicDNS, jeśli skonfigurowany.

---

# 84. HTTPS — następny krok opcjonalny

Stable może działać w Tailscale bez publicznej ekspozycji, ale można rozważyć:
- Tailscale HTTPS,
- reverse proxy,
- certyfikaty.

Nie wystawiać dashboardu publicznie bez osobnego security pass.

---

# 85. Stable Runtime Targets

Założenia:
- Debian 13 containerized host,
- brak polegania na systemd,
- Python 3,
- SQLite,
- Tailscale userspace networking,
- Docker opcjonalny,
- Git worktrees.

---

# 86. Stable Operational Metrics

Dashboard:
- uptime,
- restart count,
- recovery count,
- backup age,
- DB size,
- artifact storage,
- memory storage,
- event volume,
- queue depth,
- provider health.

---

# 87. SLO / Health Goals

Przykład:

```text
daemon restart recovery < 60s
web restart < 15s
backup verify PASS
zero silent task loss
zero direct main modifications without policy
```

---

# 88. Final Stable Activation

Po pełnym PASS:

```text
release = 5.0.0
channel = stable
status = active
```

Zapisać event:

```text
release.activated
```

---

# 89. Deployment Report

Wygenerować:

```text
DEPLOYMENT_REPORT_v5.0.0.md
```

Zawiera:

```text
Target host
Version
Previous version
Backup ID
Schema version
Release checksum
Migration results
Selftest results
E2E results
Security checks
Dashboard URL
Daemon PID
Web PID
Open issues
Rollback path
```

---

# 90. Następna roadmapa po v5.0 Stable

Po ustabilizowaniu v5.0 kolejną gałęzią rozwoju może być:

## AgentBox v5.1 — Distributed Agents & Remote Workers

Zakres:

```text
multiple AgentBox workers
remote execution nodes
worker registration
worker capabilities
task routing
distributed queue
remote sandboxes
node health
node budgets
cross-node handoffs
artifact transfer
```

Alternatywnie:

## AgentBox v5.1 — Intelligence Upgrade

```text
semantic project index
vector memory
advanced context routing
agent specialization
model router
automatic provider selection
learning from completed tasks
```

Priorytet v5.1 powinien zostać wybrany dopiero po rzeczywistym użyciu Stable.

---

# 91. Zasada Stable

AgentBox v5.0 Stable nie może zostać oznaczony jako ukończony tylko dlatego, że UI działa.

Warunek:

```text
recoverable
auditable
upgradeable
rollbackable
observable
secure by default
```

Dopiero wtedy jest to pełna platforma AgentBox v5.
