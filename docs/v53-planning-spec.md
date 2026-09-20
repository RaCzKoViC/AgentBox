# AgentBox v5.3 — Autonomous Planning & Workflow Intelligence

**Środowisko główne:** AgentBox  
**Control Plane:** `100.123.66.15:22`  
**Użytkownik:** `box`  
**Hostname:** `cursor`  
**Root projektu:** `/workspace/agentbox-v5`  
**Poprzednia wersja:** `v5.2.0` — Intelligence Upgrade  
**Nowa wersja:** `v5.3.0`

> v5.3 rozwija AgentBox z inteligentnej platformy wykonawczej w system zdolny do autonomicznego planowania długich zadań, dynamicznego rozbijania celów na podzadania, adaptacyjnego budowania grafów agentów, rewizji planu podczas wykonywania oraz oceny jakości własnych decyzji. Warstwa v5.3 musi pozostawać podporządkowana Policy, Budget, Risk, Approval, Recovery, Distributed Workers oraz Intelligence Layer z v5.2.

---

# 1. Cel v5.3

AgentBox v5.3 ma umożliwiać:

- Dynamic Task Decomposition
- Goal Tracking
- Adaptive Agent Graphs
- Automatic Subtasks
- Dependency Prediction
- Plan Revision
- Workflow Templates
- Long-Horizon Task State
- Autonomous Retry Strategy
- Dynamic Handoffs
- Execution Reflection
- Plan Quality Evaluation
- Multi-Agent Orchestration
- Checkpoint-Based Continuation
- Failure Recovery
- Semantic Memory-Aware Planning
- Budget-Aware Planning
- Risk-Aware Planning
- Distributed Worker-Aware Planning

Docelowy przepływ:

```text
User Goal
   │
   ▼
Goal Analyzer
   │
   ▼
Task Classifier
   │
   ▼
Planner
   │
   ▼
Dynamic Task Graph
   │
   ├── Research
   ├── Architecture
   ├── Implementation
   ├── Testing
   ├── Review
   └── Release
   │
   ▼
Scheduler
   │
   ▼
Agents / Workers
   │
   ▼
Observation
   │
   ▼
Reflection
   │
   ├── continue
   ├── retry
   ├── revise plan
   ├── add subtask
   ├── remove subtask
   └── request approval
   │
   ▼
Goal Completion
```

---

# 2. Główne moduły v5.3

```text
agentbox/
├── planning/
│   ├── goal_analyzer.py
│   ├── planner.py
│   ├── decomposition.py
│   ├── task_graph.py
│   ├── dependencies.py
│   ├── plan_revision.py
│   ├── workflow_templates.py
│   ├── checkpoints.py
│   ├── retry_strategy.py
│   ├── reflection.py
│   ├── plan_quality.py
│   ├── execution_state.py
│   └── orchestration.py
│
├── workflows/
│   ├── registry.py
│   ├── loader.py
│   ├── compiler.py
│   └── validators.py
│
└── orchestration/
    ├── adaptive_graph.py
    ├── agent_assignment.py
    ├── dynamic_handoffs.py
    └── goal_tracker.py
```

---

# 3. Goal Object

Każde większe zadanie ma mieć nadrzędny obiekt celu.

Pola:

```text
goal_id
title
description
project_id
status
priority
success_criteria
constraints
budget_id
risk_profile
approval_policy
created_at
updated_at
completed_at
```

Statusy:

```text
created
analyzing
planning
awaiting_plan_approval
active
blocked
revising
paused
completed
failed
cancelled
```

---

# 4. Goal Success Criteria

Każdy goal powinien posiadać mierzalne kryteria.

Przykład:

```text
- build passes
- tests pass
- no policy violations
- security review passes
- acceptance criteria satisfied
- merge approved
```

Goal nie powinien być oznaczony jako `completed` tylko dlatego, że ostatni agent zakończył run.

---

# 5. Goal Analyzer

API:

```python
analyze_goal(
    title,
    description,
    project_context,
    constraints,
) -> GoalAnalysis
```

Wynik:

```json
{
  "complexity": "VERY_HIGH",
  "task_type": "architecture+implementation",
  "estimated_stages": 7,
  "required_agents": [
    "planner",
    "architect",
    "coder",
    "tester",
    "reviewer"
  ],
  "risk": "HIGH",
  "approval_points": [
    "plan",
    "merge"
  ]
}
```

---

# 6. Dynamic Task Decomposition

Planner rozbija goal na podzadania.

Przykład:

```text
Goal: Build distributed worker failover

├── Analyze current scheduler
├── Design failover states
├── Add worker lease recovery
├── Add DB migrations
├── Implement scheduler changes
├── Add tests
├── Run chaos test
├── Review
└── Prepare release report
```

---

# 7. Subtask Object

Pola:

```text
task_id
goal_id
parent_task_id
title
description
type
priority
status
assigned_agent
assigned_worker
dependencies
required_capabilities
budget
risk
acceptance_criteria
retry_policy
created_at
updated_at
```

---

# 8. Task Graph

Nie liniowa lista, ale DAG:

```text
          Research
             │
             ▼
         Architecture
        /            \
       ▼              ▼
 Backend Work      Test Design
       │              │
       └──────┬───────┘
              ▼
         Integration
              │
              ▼
            Review
```

---

# 9. Dependency Prediction

Planner powinien przewidywać zależności na podstawie:

```text
task type
project structure
semantic index
symbol graph
previous experience
workflow templates
```

---

# 10. Dependency Types

```text
hard
soft
resource
approval
artifact
context
```

Przykład:

```text
tester depends hard on coder
reviewer depends hard on tester
release depends approval on reviewer
```

---

# 11. Adaptive Agent Graph

Graf agentów może być zmieniany podczas wykonywania.

Przykład:

```text
Planner
↓
Architect
↓
Coder
```

Po wykryciu problemu:

```text
Planner
↓
Architect
↓
Coder
├── Debugger
└── Researcher
```

---

# 12. Dynamic Handoffs

Handoff nie tylko statyczny.

Planner może utworzyć nowy handoff gdy:

```text
unknown dependency
test failure
security concern
performance regression
provider limitation
missing context
```

---

# 13. Workflow Templates

Dodaj katalog:

```text
/workspace/agentbox-v5/workflows/
```

Przykładowe template:

```text
bugfix.yaml
feature.yaml
refactor.yaml
security_review.yaml
release.yaml
research.yaml
migration.yaml
incident.yaml
```

---

# 14. Workflow Template Format

Przykład:

```yaml
name: feature
stages:
  - planner
  - architect
  - coder
  - tester
  - reviewer

approvals:
  - after_plan
  - before_merge

retry:
  max_attempts: 2
```

---

# 15. Workflow Compiler

Template nie jest finalnym planem.

Pipeline:

```text
template
↓
goal analysis
↓
project context
↓
risk
↓
budget
↓
dynamic expansion
↓
compiled task graph
```

---

# 16. Plan Object

Pola:

```text
plan_id
goal_id
version
status
summary
graph_json
estimated_cost
estimated_runtime
risk_summary
approval_points
created_at
supersedes_plan_id
```

---

# 17. Plan Versioning

Każda rewizja planu:

```text
plan v1
↓
execution issue
↓
plan v2
```

Nie nadpisywać starego planu.

---

# 18. Plan Revision

Trigger:

```text
task failure
budget pressure
worker unavailable
provider unavailable
policy change
new evidence
test failure
review reject
```

---

# 19. Plan Revision API

```python
revise_plan(
    goal_id,
    current_plan,
    observations,
    constraints,
) -> RevisedPlan
```

---

# 20. Revision Scope

Plan revision może:

```text
add task
remove task
replace task
change dependency
change agent
change worker
change provider
split task
merge tasks
change retry strategy
```

Nie może:
- zwiększyć budget bez approval,
- ominąć policy,
- pominąć wymaganej approval gate.

---

# 21. Long-Horizon Task State

Długie taski muszą przechowywać:

```text
current stage
completed stages
pending stages
active dependencies
latest checkpoint
recent failures
current plan version
current context version
budget consumed
time elapsed
```

---

# 22. Execution State Machine

```text
created
↓
planned
↓
approved
↓
ready
↓
running
↓
observing
↓
reflecting
↓
continue / retry / revise / block
↓
completed
```

---

# 23. Checkpoints

Checkpoint po:

```text
completed subtask
important artifact
successful test stage
plan revision
approval
handoff completion
```

---

# 24. Checkpoint Payload

```text
goal state
plan version
task graph state
completed tasks
active tasks
artifacts
memory refs
budget usage
risk status
git SHAs
```

---

# 25. Resume

CLI:

```bash
agent5 goal resume GOAL_ID
```

System:
- odczytuje latest checkpoint,
- weryfikuje project state,
- weryfikuje policy/budget,
- wznowienie.

---

# 26. Autonomous Retry Strategy

Retry zależy od klasy błędu.

Przykłady:

```text
provider timeout
→ retry same provider

rate limit
→ fallback provider

test failure
→ debugger

syntax error
→ coder retry

policy denied
→ no retry

approval rejected
→ stop / revise

worker lost
→ failover
```

---

# 27. Retry Policy

Pola:

```text
max_attempts
backoff
fallback_agent
fallback_provider
require_reflection
require_plan_revision
```

---

# 28. Retry Budget

Każdy retry zużywa budżet.

Nie może być nieskończonego loop.

---

# 29. Loop Detection

Wykrywaj:

```text
same error
same diff
same failed test
same agent response
same plan revision
```

Po N powtórzeniach:

```text
loop_detected
```

i stop / approval / human intervention.

---

# 30. Reflection Engine

Po ważnym etapie:

```python
reflect(
    goal_id,
    task_id,
    run_result,
    context,
)
```

Wynik:

```text
CONTINUE
RETRY
REPLAN
ESCALATE
COMPLETE
```

---

# 31. Reflection Inputs

```text
task outcome
tests
review
artifacts
errors
budget
risk
provider health
worker health
semantic memory
experience memory
```

---

# 32. Reflection Output

Przykład:

```json
{
  "decision": "REPLAN",
  "confidence": 0.88,
  "reason": "Tests reveal incompatible dependency",
  "proposed_actions": [
    "add dependency research task",
    "pause integration task"
  ]
}
```

---

# 33. Plan Quality Evaluation

Ocena:

```text
coverage
dependency correctness
risk coverage
budget feasibility
parallelism
approval correctness
test coverage
```

---

# 34. Plan Quality Score

Skala:

```text
0-100
```

Nie używać jako bezwzględnej prawdy.

To sygnał pomocniczy.

---

# 35. Plan Quality Gate

Jeśli score < threshold:

```text
replan
```

Przykład:

```ini
[planning]
minimum_plan_quality = 65
```

---

# 36. Task Graph Validation

Przed execution:

```text
no cycles
all dependencies valid
all agents exist
all required capabilities available
budget feasible
policy feasible
approval gates present
```

---

# 37. Cycle Detection

DAG musi być sprawdzany przed aktywacją planu.

Cycle:

```text
A -> B -> C -> A
```

= plan invalid.

---

# 38. Critical Path

Scheduler powinien wyliczać:

```text
critical path
parallelizable tasks
blocked tasks
```

---

# 39. Parallelism

Planner może oznaczyć:

```text
parallel_safe=true
```

Przykład:

```text
research docs
+
test design
```

mogą działać równolegle.

---

# 40. Concurrency Guard

Równoległe taski nie mogą modyfikować tych samych plików bez koordynacji.

Wymagane:

```text
file ownership
worktree isolation
merge strategy
```

---

# 41. File Conflict Prediction

Na podstawie:
- semantic index,
- planned file targets,
- previous edits.

Jeśli konflikt:

```text
serialize tasks
```

---

# 42. Agent Assignment

Agent wybierany przez:

```text
task type
specialization
historical quality
provider availability
worker capabilities
budget
risk
```

---

# 43. Worker Assignment

v5.1 scheduler wybiera node.

v5.3 dodaje wiedzę o planie:

```text
keep related tasks on same worker
```

jeśli poprawia locality.

---

# 44. Affinity

Przykład:

```text
project affinity
artifact locality
cache locality
agent specialization
```

---

# 45. Semantic Memory Integration

Planner używa v5.2:

```text
project memory
experience memory
semantic code search
past failures
architecture decisions
```

---

# 46. Experience-Aware Planning

Jeśli podobne taski wcześniej:
- failowały w stage X,
- wymagały Debuggera,
- miały określony provider lepszy,

planner może uwzględnić te sygnały.

---

# 47. Context-Aware Subtasks

Subtask creation może być wywołany przez retrieval.

Przykład:

```text
semantic search finds migration risk
→ add migration validation task
```

---

# 48. Budget-Aware Planning

Plan ma estymować:

```text
tokens
cost
runtime
agents
workers
```

---

# 49. Budget Feasibility

Przed approval:

```text
estimated budget <= available
```

Jeśli nie:
- simplify plan,
- cheaper models,
- less parallelism,
- ask approval.

---

# 50. Risk-Aware Planning

High-risk tasks:
- więcej review,
- dodatkowy security agent,
- approval.

---

# 51. Policy-Aware Planning

Planner nie może tworzyć kroków, które są policy-denied.

---

# 52. Approval-Aware Planning

Plan sam wskazuje wymagane approval gates:

```text
after_plan
before_destructive_action
before_merge
before_push
before_release
```

---

# 53. Goal Progress

Progress nie tylko procent tasków.

Uwzględnij:
- critical path,
- task weights,
- blocked tasks.

---

# 54. Goal Progress API

```python
goal_progress(goal_id)
```

Wynik:

```json
{
  "percent": 62,
  "critical_path_percent": 48,
  "blocked": 1,
  "active": 2,
  "completed": 8
}
```

---

# 55. Goal CLI

```bash
agent5 goal create
agent5 goal list
agent5 goal show GOAL_ID
agent5 goal plan GOAL_ID
agent5 goal approve GOAL_ID
agent5 goal run GOAL_ID
agent5 goal pause GOAL_ID
agent5 goal resume GOAL_ID
agent5 goal cancel GOAL_ID
```

---

# 56. Plan CLI

```bash
agent5 plan list GOAL_ID
agent5 plan show PLAN_ID
agent5 plan graph PLAN_ID
agent5 plan revise PLAN_ID
agent5 plan validate PLAN_ID
agent5 plan explain PLAN_ID
```

---

# 57. Workflow CLI

```bash
agent5 workflow list
agent5 workflow show feature
agent5 workflow validate feature
agent5 workflow compile feature --goal GOAL_ID
```

---

# 58. Reflection CLI

```bash
agent5 reflection list GOAL_ID
agent5 reflection show REFLECTION_ID
```

---

# 59. Dashboard — Goals

Nowa sekcja:

```text
Goals
```

Tabela:

```text
Goal
Project
Status
Progress
Plan Version
Risk
Budget
Active Tasks
Blocked
```

---

# 60. Goal Detail

Sekcje:

```text
Overview
Plan
Task Graph
Timeline
Agents
Workers
Approvals
Budget
Risk
Artifacts
Memory
Reflections
```

---

# 61. Visual Task Graph

Dashboard powinien pokazywać DAG:

```text
[Research] ─→ [Architecture] ─→ [Coder]
                           └──→ [Test Design]
```

Statusy w czasie rzeczywistym.

---

# 62. Plan Revision UI

Pokazuje diff:

```text
Added tasks
Removed tasks
Dependency changes
Agent changes
Budget delta
Risk delta
```

---

# 63. Reflection UI

Każda reflection:

```text
Trigger
Decision
Confidence
Reason
Actions
```

---

# 64. Workflow Template UI

Możliwość:
- list,
- inspect,
- clone,
- create,
- validate.

---

# 65. New SQLite Tables

```sql
CREATE TABLE IF NOT EXISTS goals (
    id TEXT PRIMARY KEY,
    project_id TEXT,
    title TEXT NOT NULL,
    description TEXT,
    status TEXT NOT NULL DEFAULT 'created',
    priority INTEGER NOT NULL DEFAULT 100,
    success_criteria_json TEXT,
    constraints_json TEXT,
    budget_id TEXT,
    risk_profile TEXT,
    approval_policy TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    completed_at TEXT
);

CREATE TABLE IF NOT EXISTS plans (
    id TEXT PRIMARY KEY,
    goal_id TEXT NOT NULL,
    version INTEGER NOT NULL,
    status TEXT NOT NULL,
    summary TEXT,
    graph_json TEXT NOT NULL,
    estimated_cost REAL,
    estimated_runtime_seconds REAL,
    risk_summary_json TEXT,
    approval_points_json TEXT,
    quality_score REAL,
    supersedes_plan_id TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY(goal_id) REFERENCES goals(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS goal_tasks (
    goal_id TEXT NOT NULL,
    task_id TEXT NOT NULL,
    weight REAL NOT NULL DEFAULT 1.0,
    PRIMARY KEY(goal_id, task_id),
    FOREIGN KEY(goal_id) REFERENCES goals(id) ON DELETE CASCADE,
    FOREIGN KEY(task_id) REFERENCES tasks(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS reflections (
    id TEXT PRIMARY KEY,
    goal_id TEXT NOT NULL,
    task_id TEXT,
    run_id TEXT,
    decision TEXT NOT NULL,
    confidence REAL,
    reason TEXT,
    proposed_actions_json TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY(goal_id) REFERENCES goals(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS checkpoints (
    id TEXT PRIMARY KEY,
    goal_id TEXT NOT NULL,
    plan_id TEXT,
    state_json TEXT NOT NULL,
    git_state_json TEXT,
    budget_state_json TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY(goal_id) REFERENCES goals(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS workflow_templates (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL UNIQUE,
    version INTEGER NOT NULL DEFAULT 1,
    definition_json TEXT NOT NULL,
    enabled INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
```

---

# 66. Graph Metadata

Każdy node:

```text
task_id
type
agent
worker
status
dependencies
estimated_runtime
estimated_cost
risk
parallel_safe
critical
```

---

# 67. Plan Events

Dodaj:

```text
goal.created
goal.started
goal.completed
goal.failed

plan.created
plan.approved
plan.revised
plan.rejected

task.decomposed
task.auto_created
dependency.predicted

reflection.created
reflection.replan
reflection.retry

checkpoint.created
checkpoint.restored

workflow.compiled
workflow.failed
```

---

# 68. Planning Metrics

```text
agentbox_goals_total
agentbox_goals_active
agentbox_goal_completion_seconds
agentbox_plan_revisions_total
agentbox_auto_subtasks_total
agentbox_reflections_total
agentbox_retries_total
agentbox_loop_detections_total
agentbox_plan_quality_score
agentbox_critical_path_seconds
```

---

# 69. Planner Observability

Dashboard:

```text
Plan revisions
Average plan quality
Retry rate
Replan rate
Blocked task rate
Goal completion rate
```

---

# 70. Execution Reflection Quality

Mierzyć:
- successful replans,
- unnecessary retries,
- recovered failures,
- prevented loops.

---

# 71. Failure Taxonomy

```text
TRANSIENT
CODE
TEST
DEPENDENCY
PROVIDER
WORKER
POLICY
BUDGET
APPROVAL
SECURITY
UNKNOWN
```

---

# 72. Failure Classifier

Reflection Engine klasyfikuje błąd przed retry.

---

# 73. Retry Decision Matrix

Przykład:

```text
TRANSIENT -> retry
CODE -> debugger
TEST -> coder/debugger
DEPENDENCY -> researcher/replan
PROVIDER -> fallback
WORKER -> failover
POLICY -> block
BUDGET -> pause
APPROVAL -> wait
SECURITY -> block
UNKNOWN -> reflection/replan
```

---

# 74. Human Escalation

Jeśli:
- retries exhausted,
- repeated loop,
- conflicting policies,
- high uncertainty,

status:

```text
needs_human
```

---

# 75. Confidence

Planner/reflection może podawać confidence.

Nie może zastąpić policy/risk.

---

# 76. Plan Approval Gate

Dla high-risk goal:

```text
plan
↓
human approval
↓
execution
```

---

# 77. Automatic Low-Risk Goals

Low-risk, read-only goal może być auto-approved jeśli policy pozwala.

---

# 78. Workflow Memory

AgentBox zapisuje:

```text
which workflows worked for which task type
```

do Experience Memory v5.2.

---

# 79. Workflow Recommendation

Przy nowym goal:

```text
feature
bugfix
security review
```

system proponuje najlepszy template.

---

# 80. Distributed Goal Execution

Goal może obejmować wiele workerów.

Scheduler v5.1:
- przypisuje subtasks,
- zachowuje dependencies,
- respektuje critical path.

---

# 81. Cross-Worker Checkpoints

Checkpoint centralny.

Nie polegać wyłącznie na lokalnym workerze.

---

# 82. Worker Loss

Jeśli worker znika:
- impacted subtasks interrupted,
- graph recomputed,
- failover,
- plan revision jeśli wymagane.

---

# 83. Provider Loss

Jeśli provider znika:
- router v5.2 fallback,
- jeśli brak fallback -> blocked,
- reflection może zmienić plan.

---

# 84. Semantic Replanning

Replan używa:
- semantic index,
- latest artifacts,
- failures,
- experience memory.

---

# 85. Goal Context

Nie budować jednego ogromnego context.

Goal context:
- summary,
- plan,
- current stage,
- key constraints.

Task context osobno.

---

# 86. Plan Compression

Długi plan może być kompresowany dla modeli, ale pełny graph pozostaje w DB.

---

# 87. Orchestration Safety

Autonomia nie może:
- sama podnieść limitów,
- bypassować approvals,
- wykonywać policy-denied action,
- force push,
- zmieniać protected settings.

---

# 88. Feature Flags

```ini
[planning]
autonomous_decomposition = true
adaptive_graphs = true
automatic_subtasks = true
plan_revision = true
reflection = true
workflow_templates = true
auto_retry = true
```

Dla pierwszego wdrożenia:

```ini
automatic_subtasks = false
```

można włączyć po smoke testach.

---

# 89. Compatibility Mode

Jeśli planner v5.3 wyłączony:
- task engine działa jak v5.2.

---

# 90. Tests

Dodaj:

```text
tests/planning/
├── test_goal_analyzer.py
├── test_decomposition.py
├── test_task_graph.py
├── test_dependencies.py
├── test_plan_revision.py
├── test_workflow_templates.py
├── test_checkpoints.py
├── test_retry_strategy.py
├── test_reflection.py
├── test_plan_quality.py
├── test_loop_detection.py
└── test_goal_resume.py
```

---

# 91. Smoke Test A — Decomposition

```text
create feature goal
↓
planner decomposes
↓
valid DAG
↓
agents assigned
↓
budget feasible
```

---

# 92. Smoke Test B — Retry

```text
coder fails syntax test
↓
failure classified CODE
↓
debugger task
↓
tester reruns
↓
continue
```

---

# 93. Smoke Test C — Replan

```text
dependency incompatible
↓
reflection REPLAN
↓
new research task
↓
plan v2
↓
execution resumes
```

---

# 94. Smoke Test D — Worker Loss

```text
active subtask
↓
worker offline
↓
checkpoint
↓
failover
↓
graph continues
```

---

# 95. Smoke Test E — Budget Pressure

```text
estimated remaining cost > budget
↓
replan
↓
cheaper model/router choice
↓
continue
```

---

# 96. Smoke Test F — Loop Detection

```text
same failure x3
↓
loop_detected
↓
no further retry
↓
needs_human
```

---

# 97. Acceptance Criteria

v5.3 jest gotowa jeśli:

- [ ] goal objects działają
- [ ] dynamic decomposition działa
- [ ] task DAG validation działa
- [ ] dependency prediction działa
- [ ] adaptive agent graph działa
- [ ] automatic subtasks działają
- [ ] workflow templates działają
- [ ] plan versioning działa
- [ ] plan revision działa
- [ ] checkpoints działają
- [ ] goal resume działa
- [ ] retry strategy działa
- [ ] loop detection działa
- [ ] reflection działa
- [ ] plan quality działa
- [ ] semantic memory wpływa na planning
- [ ] model router działa z planning
- [ ] distributed workers działają z DAG
- [ ] budget/policy/risk są respektowane
- [ ] approvals są respektowane
- [ ] dashboard goal graph działa
- [ ] planning selftest PASS
- [ ] rollback path istnieje

---

# 98. Self-Test

```bash
agent5 selftest --planning
```

Powinien sprawdzać:

```text
goal store
plan store
workflow registry
DAG validation
dependency prediction
decomposition
reflection
retry
checkpoint
resume
distributed orchestration
policy integration
budget integration
risk integration
semantic memory integration
```

---

# 99. Deployment Guard

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

# 100. Backup Before v5.3

Backup:
- SQLite,
- v5.2 semantic metadata,
- vector store,
- configs,
- workflow templates,
- current release,
- worker registry.

---

# 101. Upgrade Sequence

```text
deployment guard
↓
v5.2 selftest
↓
backup
↓
maintenance mode
↓
DB migration
↓
install planning modules
↓
load workflow templates
↓
planning selftest
↓
smoke tests
↓
enable feature flags
↓
activate
```

---

# 102. Rollback

Jeśli planner v5.3 failuje:
- disable planning feature flags,
- preserve goals/plans as data,
- restore DB backup if migration issue,
- switch release,
- return to v5.2 task execution.

---

# 103. Dashboard Additions

Dodaj:

```text
Goals
Plans
Workflows
Reflections
Checkpoints
```

---

# 104. API Additions

```text
GET  /api/v1/goals
POST /api/v1/goals
GET  /api/v1/goals/{id}
POST /api/v1/goals/{id}/plan
POST /api/v1/goals/{id}/run
POST /api/v1/goals/{id}/pause
POST /api/v1/goals/{id}/resume

GET /api/v1/plans/{id}
POST /api/v1/plans/{id}/revise
POST /api/v1/plans/{id}/approve

GET /api/v1/workflows
GET /api/v1/reflections
GET /api/v1/checkpoints
```

---

# 105. Intelligence Report

Po wdrożeniu wygenerować:

```text
PLANNING_REPORT_v5.3.0.md
```

Zawiera:

```text
Goals created
Plans generated
Plan quality
Revisions
Auto subtasks
Retries
Loops detected
Reflection outcomes
Distributed execution
Budget impact
Open issues
Rollback path
```

---

# 106. Następny etap roadmapy

## AgentBox v5.4 — Tool Intelligence & Capability Runtime

Zakres:

```text
Tool Registry v2
Dynamic Tool Discovery
Tool Capability Matching
Tool Sandboxing
MCP Integration
Connector Runtime
Browser / API / Database Tools
Tool Cost & Risk Profiles
Tool Chaining
Tool Outcome Memory
Tool Reliability Scoring
Agent Tool Planning
```

v5.4 powinno dać agentom bardziej inteligentny i kontrolowany dostęp do narzędzi, zamiast rozbudowywać wyłącznie sam proces planowania.
