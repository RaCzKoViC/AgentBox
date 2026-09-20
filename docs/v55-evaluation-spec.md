# AgentBox v5.5 — Self-Improvement, Evaluation & Benchmarking

**Środowisko główne:** AgentBox  
**Control Plane:** `100.123.66.15:22`  
**Użytkownik:** `box`  
**Hostname:** `cursor`  
**Root projektu:** `/workspace/agentbox-v5`  
**Poprzednia wersja:** `v5.4.0` — Tool Intelligence & Capability Runtime  
**Nowa wersja:** `v5.5.0`

> v5.5 zamyka pętlę jakości AgentBox. Platforma ma nie tylko wykonywać zadania, lecz także mierzyć skuteczność, wykrywać regresje, porównywać agentów/modeli/workflowów/narzędzia, analizować niepowodzenia i bezpiecznie proponować ulepszenia. Self-improvement w v5.5 oznacza **mierzenie, ocenę i generowanie propozycji zmian**, a nie niekontrolowane modyfikowanie własnego core.

## 1. Cel v5.5

AgentBox v5.5 ma zapewnić:

- Evaluation Harness
- Golden Tasks
- Regression Suite
- Task Benchmarks
- Agent Benchmarks
- Model Benchmarks
- Tool Benchmarks
- Workflow Benchmarks
- Prompt Versioning
- Workflow Versioning
- A/B Testing
- Quality Gates
- Performance Baselines
- Cost/Quality Optimization
- Failure Mining
- Error Taxonomy
- Self-Improvement Proposals
- Safe Prompt Evolution
- Safe Workflow Evolution
- Human-Approved Optimization
- Benchmark Dashboard
- Continuous Evaluation

Docelowa pętla:

```text
Task / Benchmark
      │
      ▼
 Execute Variant
      │
      ▼
 Collect Signals
      │
      ▼
    Evaluate
      │
      ▼
 Compare Baseline
      │
      ├── PASS
      ├── REGRESSION
      └── IMPROVEMENT
      │
      ▼
 Improvement Proposal
      │
      ▼
 Human Approval
      │
      ▼
 Canary / A-B Test
      │
      ▼
 Promote / Reject / Rollback
```

## 2. Główne moduły

```text
agentbox/
├── evaluation/
│   ├── harness.py
│   ├── suites.py
│   ├── cases.py
│   ├── runners.py
│   ├── judges.py
│   ├── scoring.py
│   ├── baselines.py
│   ├── regressions.py
│   ├── ab_testing.py
│   ├── golden_tasks.py
│   ├── reports.py
│   └── quality_gates.py
├── benchmarks/
│   ├── tasks.py
│   ├── agents.py
│   ├── models.py
│   ├── tools.py
│   ├── workflows.py
│   ├── providers.py
│   └── distributed.py
├── improvement/
│   ├── proposals.py
│   ├── failure_mining.py
│   ├── prompt_evolution.py
│   ├── workflow_evolution.py
│   ├── optimization.py
│   ├── canary.py
│   └── promotion.py
└── versioning/
    ├── prompts.py
    ├── workflows.py
    ├── agents.py
    └── benchmark_sets.py
```

## 3. Evaluation Harness

Centralne API:

```python
evaluate(
    subject,
    benchmark_suite,
    variants=None,
    baseline=None,
    constraints=None,
)
```

`subject` może oznaczać:

```text
agent
model
provider
tool
workflow
prompt
router
planner
context strategy
```

## 4. Golden Tasks

Golden Task to stabilny przypadek referencyjny.

Przykłady:

```text
golden-rust-compile-fix
golden-python-bugfix
golden-planner-decomposition
golden-tool-fallback
golden-memory-retrieval
```

Struktura:

```text
benchmarks/golden/
└── rust_compile_fix/
    ├── task.yaml
    ├── fixture/
    ├── expected/
    ├── validators.py
    └── README.md
```

## 5. Evaluation Signals

Zbieraj:

```text
success
test_pass
review_pass
policy_violations
risk_events
retries
runtime
tokens
cost
tool_calls
tool_failures
handoffs
plan_revisions
context_tokens
artifact_quality
user_approval
rollback
```

## 6. Scoring Dimensions

```text
correctness
quality
safety
efficiency
cost
latency
robustness
maintainability
tool reliability
context efficiency
```

Nie opieraj wszystkiego na jednej liczbie. Pokazuj breakdown.

## 7. Scoring Methods

```text
deterministic validator
tests
schema validator
diff validator
artifact validator
policy validator
LLM-as-judge
human rating
hybrid
```

LLM-as-judge nie może być jedynym źródłem prawdy dla security, policy i test success.

## 8. Baselines i Regression Detection

Baseline przechowuje:

```text
version
agent
model
workflow
score distribution
cost
runtime
```

Regresja:

```text
correctness drop
cost increase
latency increase
retry increase
policy violation increase
tool failure increase
```

Przykład progów:

```ini
[evaluation]
correctness_regression_percent = 5
cost_regression_percent = 15
latency_regression_percent = 20
failure_rate_regression_percent = 5
```

## 9. Quality Gates

Release nie przechodzi, jeśli:

```text
critical golden task fails
security regression
policy regression
DB/recovery regression
benchmark score below minimum
```

Pipeline:

```text
candidate release
↓
unit tests
↓
integration tests
↓
golden suite
↓
benchmark suite
↓
regression analysis
↓
quality gate
↓
approve/reject
```

## 10. Benchmarking

Porównuj:

```text
Planner v1 vs Planner v2
Coder A vs Coder B
Reviewer prompt v3 vs v4
Model A vs Model B
Tool A vs Tool B
Workflow v1 vs v2
Provider A vs Provider B
```

Mierz:

```text
completion
review pass
runtime
cost
retries
failures
tool usage
policy/risk incidents
```

## 11. Prompt Versioning

Każdy prompt:

```text
prompt_id
name
version
content_hash
content
created_at
parent_version
status
```

Statusy:

```text
draft
candidate
canary
active
deprecated
rejected
```

## 12. Workflow Versioning

Analogicznie:

```text
workflow_id
version
definition
parent_version
status
```

## 13. A/B Testing

Przykład:

```text
50% Planner v3
50% Planner v4
```

Tylko dla low/medium risk.

A/B assignment powinien być stabilny względem `task_id`.

## 14. Canary Testing

Nowa wersja:
- 5–10% bezpiecznych tasków,
- obserwacja,
- promote/reject.

High-risk tasks nie używają candidate variant domyślnie.

## 15. Improvement Proposal

System nie modyfikuje od razu produkcji.

Generuje:

```text
proposal_id
target
current_version
proposed_change
evidence
expected_gain
risk
benchmark_plan
status
```

Przykład:

```text
Target:
Coder prompt

Evidence:
18 failures caused by missing test-before-review step

Proposal:
add explicit test gate

Expected:
lower reviewer rejection rate

Risk:
LOW
```

## 16. Proposal States

```text
draft
evaluating
awaiting_approval
approved
canary
promoted
rejected
rolled_back
```

## 17. Failure Mining

Analizuj:

```text
failed tasks
review rejections
test failures
timeouts
tool failures
policy denies
budget exceed
loops
replans
```

Grupuj według signature:

```text
error class
message fingerprint
task type
agent
model
tool
project
```

## 18. Safe Prompt / Workflow Evolution

Pipeline:

```text
failure mining
↓
proposal
↓
candidate
↓
benchmark
↓
A/B or canary
↓
approval
↓
promote
```

v5.5 nie może samodzielnie:
- wdrażać zmian core bez approval,
- zmieniać security policy,
- zwiększać budgets,
- bypassować approvals.

## 19. Optimization Engine

Cel:

```text
maximize quality
subject to:
  budget
  latency
  risk
  privacy
```

Wspieraj Pareto analysis:
- quality vs cost,
- quality vs latency,
- cost vs reliability.

## 20. Feedback do istniejących modułów

v5.2 Model Router dostaje:
- task-type quality,
- cost,
- latency,
- reliability.

v5.4 Tool Runtime dostaje:
- reliability,
- latency,
- failure profile.

v5.3 Planner dostaje:
- plan quality,
- replan frequency,
- completion success.

Experience Memory dostaje wyniki evaluation.

## 21. Benchmark Isolation

Każdy benchmark:

```text
benchmark=true
isolated worktree
temporary DB if needed
artifact isolation
fixed fixture
```

## 22. Determinism Controls

Gdzie możliwe:

```text
fixed seeds
fixed commit
fixed fixture
fixed tool versions
```

Dla probabilistycznych zadań:
- wiele powtórzeń,
- mean,
- median,
- variance.

## 23. Distributed Benchmarks

v5.1 workers mogą wykonywać benchmarki równolegle.

Labels:

```text
benchmark
gpu
local-model
isolated
```

Evaluation queue ma niższy priorytet niż produkcyjne taski.

## 24. Continuous Evaluation

Triggery:

```text
manual
nightly
weekly
pre-release
post-upgrade
prompt_change
workflow_change
model_change
tool_change
```

## 25. Migracja SQLite

```sql
CREATE TABLE IF NOT EXISTS benchmark_suites (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    version INTEGER NOT NULL,
    description TEXT,
    enabled INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS benchmark_cases (
    id TEXT PRIMARY KEY,
    suite_id TEXT NOT NULL,
    name TEXT NOT NULL,
    definition_json TEXT NOT NULL,
    version INTEGER NOT NULL DEFAULT 1,
    enabled INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY(suite_id) REFERENCES benchmark_suites(id)
);

CREATE TABLE IF NOT EXISTS evaluation_runs (
    id TEXT PRIMARY KEY,
    suite_id TEXT NOT NULL,
    subject_type TEXT NOT NULL,
    subject_id TEXT NOT NULL,
    variant TEXT,
    status TEXT NOT NULL,
    started_at TEXT,
    finished_at TEXT,
    metadata_json TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS evaluation_results (
    id TEXT PRIMARY KEY,
    evaluation_run_id TEXT NOT NULL,
    case_id TEXT NOT NULL,
    success INTEGER,
    scores_json TEXT,
    metrics_json TEXT,
    artifacts_json TEXT,
    error TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY(evaluation_run_id) REFERENCES evaluation_runs(id),
    FOREIGN KEY(case_id) REFERENCES benchmark_cases(id)
);

CREATE TABLE IF NOT EXISTS baselines (
    id TEXT PRIMARY KEY,
    suite_id TEXT NOT NULL,
    subject_type TEXT NOT NULL,
    subject_id TEXT NOT NULL,
    version TEXT,
    summary_json TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS improvement_proposals (
    id TEXT PRIMARY KEY,
    target_type TEXT NOT NULL,
    target_id TEXT NOT NULL,
    current_version TEXT,
    proposed_version TEXT,
    proposal_json TEXT NOT NULL,
    evidence_json TEXT,
    risk_level TEXT,
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
    status TEXT NOT NULL,
    parent_id TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(prompt_name, version)
);
```

## 26. Evaluation Events

```text
evaluation.started
evaluation.completed
evaluation.failed
benchmark.case_started
benchmark.case_completed
regression.detected
improvement.detected

proposal.created
proposal.approved
proposal.rejected
proposal.canary_started
proposal.promoted
proposal.rolled_back
proposal.auto_rollback
```

## 27. Metrics

```text
agentbox_evaluations_total
agentbox_benchmark_cases_total
agentbox_regressions_total
agentbox_improvements_total
agentbox_eval_cost_total
agentbox_eval_duration_seconds
agentbox_canary_success_rate
agentbox_proposals_total
```

## 28. CLI

Evaluation:

```bash
agent5 eval suite list
agent5 eval suite show SUITE
agent5 eval run SUITE --subject ...
agent5 eval status RUN_ID
agent5 eval report RUN_ID
```

Benchmarks:

```bash
agent5 benchmark list
agent5 benchmark run SUITE
agent5 benchmark compare RUN_A RUN_B
agent5 benchmark baseline set RUN_ID
```

Improvements:

```bash
agent5 improvement list
agent5 improvement show PROPOSAL_ID
agent5 improvement approve PROPOSAL_ID
agent5 improvement reject PROPOSAL_ID
agent5 improvement canary PROPOSAL_ID
agent5 improvement promote PROPOSAL_ID
agent5 improvement rollback PROPOSAL_ID
```

Prompt versions:

```bash
agent5 prompt list
agent5 prompt versions NAME
agent5 prompt diff NAME V1 V2
```

## 29. Dashboard

Nowe sekcje:

```text
Evaluation
Benchmarks
Regressions
Improvements
A/B Tests
Canaries
Failure Mining
Prompt Versions
Workflow Versions
Baselines
```

## 30. Dashboard — Evaluation

Tabela:

```text
Suite
Version
Cases
Last Run
Baseline
Status
```

Evaluation Run Detail:
- Overview,
- Cases,
- Scores,
- Cost,
- Latency,
- Failures,
- Artifacts,
- Regression,
- Comparison.

## 31. Dashboard — Improvements

Pokazuje:

```text
Target
Evidence
Expected Gain
Risk
Status
```

Z diff dla prompt/workflow candidate.

## 32. Dashboard — Failure Mining

Top clusters:

```text
error signature
count
affected agent
affected model
affected tool
trend
```

## 33. API

```text
GET  /api/v1/evaluation/suites
POST /api/v1/evaluation/runs
GET  /api/v1/evaluation/runs/{id}
GET  /api/v1/evaluation/runs/{id}/report

GET  /api/v1/benchmarks
POST /api/v1/benchmarks/{id}/run

GET  /api/v1/improvements
GET  /api/v1/improvements/{id}
POST /api/v1/improvements/{id}/approve
POST /api/v1/improvements/{id}/canary
POST /api/v1/improvements/{id}/promote

POST /api/v1/quality-gates/check
```

## 34. Safe Canary Promotion

Promotion wymaga:

```text
minimum sample size
no critical regression
quality improvement
budget acceptable
human approval
```

## 35. Automatic Rollback

Jeśli canary powoduje:
- security regression,
- critical golden failure,

natychmiast:
- candidate disabled,
- active restored,
- rollback event.

## 36. Evaluation of Intelligence Components

Benchmarkuj:
- semantic retrieval,
- context compression,
- task classifier,
- Model Router,
- Tool Router,
- Planner,
- distributed scheduler.

Retrieval:
- recall@k,
- precision@k,
- MRR.

Planner:
- DAG validity,
- completion,
- revisions,
- unnecessary subtasks,
- budget accuracy.

## 37. Evaluation Budget

Osobny od production:

```ini
[evaluation]
daily_budget_usd = 5
max_parallel_runs = 2
max_cases_per_run = 100
```

## 38. Feature Flags

```ini
[self_improvement]
evaluation = true
benchmarks = true
failure_mining = true
proposals = true
ab_testing = true
canary = true
auto_promotion = false
```

`auto_promotion = false` domyślnie.

## 39. Tests

```text
tests/evaluation/
├── test_harness.py
├── test_suites.py
├── test_scoring.py
├── test_baselines.py
├── test_regressions.py
├── test_ab_testing.py
├── test_quality_gates.py
├── test_failure_mining.py
├── test_prompt_versioning.py
├── test_workflow_versioning.py
├── test_proposals.py
├── test_canary.py
└── test_promotion.py
```

## 40. Smoke Tests

### A — Golden Suite

```text
run golden suite
↓
all critical cases pass
↓
baseline created
```

### B — Regression

```text
worse candidate
↓
benchmark
↓
regression detected
↓
quality gate FAIL
```

### C — Improvement

```text
candidate prompt
↓
benchmark
↓
better score
↓
proposal awaits approval
```

### D — Canary

```text
approve proposal
↓
small canary
↓
no regression
↓
eligible for promotion
```

### E — Auto Rollback

```text
canary causes critical failure
↓
candidate disabled
↓
active restored
↓
rollback event
```

### F — Failure Mining

```text
multiple similar failures
↓
cluster created
↓
proposal generated
```

## 41. Acceptance Criteria

- [ ] evaluation harness działa
- [ ] golden tasks działają
- [ ] benchmark suites są versioned
- [ ] baselines działają
- [ ] regression detection działa
- [ ] quality gates działają
- [ ] agent/model/tool/workflow benchmarks działają
- [ ] prompt versioning działa
- [ ] workflow versioning działa
- [ ] A/B tests działają
- [ ] canary działa
- [ ] failure mining działa
- [ ] improvement proposals działają
- [ ] promotion wymaga approval
- [ ] auto rollback działa
- [ ] distributed benchmarks działają
- [ ] dashboard evaluation działa
- [ ] evaluation selftest PASS
- [ ] rollback path istnieje

## 42. Self-Test

```bash
agent5 selftest --evaluation
```

Sprawdza:

```text
suite registry
golden cases
evaluation runner
scoring
baselines
regressions
quality gates
versioning
A/B
canary
failure mining
proposals
promotion
rollback
distributed execution
```

## 43. Deployment Guard

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

## 44. Backup Before v5.5

Backup:
- SQLite,
- prompt versions,
- workflow versions,
- benchmark definitions,
- baselines,
- v5.4 tool registry,
- current release.

## 45. Upgrade Sequence

```text
deployment guard
↓
v5.4 selftest
↓
backup
↓
maintenance mode
↓
DB migration
↓
install evaluation layer
↓
register golden suites
↓
run evaluation selftest
↓
run smoke suite
↓
set initial baseline
↓
activate
```

## 46. Rollback

Jeśli v5.5 failuje:
- disable evaluation feature flags,
- preserve historical results,
- restore DB/config if migration issue,
- switch release,
- v5.4 remains operational.

## 47. Evaluation Platform Report

Po wdrożeniu wygenerować:

```text
EVALUATION_PLATFORM_REPORT_v5.5.0.md
```

Zawiera:

```text
Suites
Golden tasks
Baselines
Prompt versions
Workflow versions
Evaluation cost
Regressions
Improvements
Canary status
Failure clusters
Open issues
Rollback path
```

## 48. Następny etap roadmapy

### AgentBox v5.6 — Operations Autopilot & Autonomous Platform Maintenance

Zakres:

```text
Automated Health Remediation
Predictive Maintenance
Resource Forecasting
Capacity Planning
Auto Cleanup
Smart Backup Scheduling
Upgrade Readiness Analysis
Configuration Drift Detection
Worker Drift Detection
Provider Drift Detection
Self-Healing Playbooks
Runbook Automation
Maintenance Planning
Autonomous Low-Risk Remediation
Human-Approved High-Risk Remediation
```

v5.6 powinno wykorzystać evaluation layer z v5.5 do bezpiecznej automatyzacji utrzymania całej platformy.
