# AgentBox v5.2 — Intelligence Upgrade

**Środowisko główne:** AgentBox  
**Control Plane:** `100.123.66.15:22`  
**Użytkownik:** `box`  
**Hostname:** `cursor`  
**Root projektu:** `/workspace/agentbox-v5`  
**Poprzednia wersja:** `v5.1.0` — Distributed Agents & Remote Workers  
**Nowa wersja:** `v5.2.0`

> v5.2 koncentruje się na jakości inteligencji AgentBox: semantic project index, vector memory, model router, automatyczny dobór providerów/modeli, zaawansowany context routing, reranking, compression, doświadczenie agentów oraz wykorzystanie wiedzy z poprzednich zadań. Infrastruktura v5.1 pozostaje fundamentem — v5.2 nie może obchodzić Policy, Budget, Risk, Approval, Recovery ani distributed worker constraints.

---

# 1. Cel v5.2

AgentBox v5.2 ma przekształcić istniejącą platformę wykonawczą w inteligentny system, który:

- rozumie semantycznie projekty,
- pamięta wcześniejsze decyzje,
- wybiera właściwy model do właściwego zadania,
- buduje lepszy kontekst dla agentów,
- wykorzystuje wyniki poprzednich tasków,
- ogranicza token waste,
- poprawia routing między agentami,
- działa lokalnie lub hybrydowo,
- obsługuje wiele providerów,
- zachowuje pełną audytowalność.

Docelowy przepływ:

```text
User Task
   │
   ▼
Task Classifier
   │
   ▼
Semantic Project Index
   │
   ▼
Memory Retrieval
   │
   ▼
Context Builder
   │
   ▼
Model Router
   │
   ├── Claude
   ├── Codex
   ├── Gemini
   ├── Ollama
   └── Other Provider
   │
   ▼
Specialized Agent
   │
   ▼
Quality Signals
   │
   ▼
Experience Memory
```

---

# 2. Główne moduły v5.2

```text
agentbox/
├── intelligence/
│   ├── semantic_index.py
│   ├── embeddings.py
│   ├── vector_store.py
│   ├── retrieval.py
│   ├── reranker.py
│   ├── context_router.py
│   ├── context_compression.py
│   ├── model_router.py
│   ├── task_classifier.py
│   ├── specialization.py
│   ├── experience.py
│   ├── quality.py
│   ├── cross_project.py
│   └── learning.py
│
├── memory/
│   ├── vector_memory.py
│   ├── memory_policy.py
│   └── memory_ranker.py
│
└── indexing/
    ├── scanner.py
    ├── chunker.py
    ├── parsers.py
    ├── symbols.py
    └── incremental.py
```

---

# 3. Semantic Project Index

Każdy projekt powinien posiadać semantyczny indeks:

```text
Project
├── files
├── symbols
├── modules
├── functions
├── classes
├── configuration
├── documentation
├── tests
├── dependencies
└── historical changes
```

Indeks ma odpowiadać na pytania typu:

```text
"gdzie obsługiwane są połączenia sieciowe?"
"który moduł odpowiada za pamięć?"
"gdzie znajduje się walidacja tasków?"
"które testy dotyczą scheduler?"
```

---

# 4. Indexing Pipeline

```text
Project Scan
   ↓
File Filtering
   ↓
Parser
   ↓
Chunker
   ↓
Metadata Extraction
   ↓
Embedding
   ↓
Vector Store
   ↓
Symbol Graph
```

---

# 5. Obsługiwane źródła

Indexuj:

```text
.py
.rs
.ts
.tsx
.js
.jsx
.go
.c
.h
.cpp
.hpp
.java
kt
swift
sh
md
toml
yaml
yml
json
sql
html
css
```

Pomijaj domyślnie:

```text
.git/
node_modules/
target/
dist/
build/
__pycache__/
venv/
.env files
binary blobs
large generated artifacts
```

---

# 6. Chunking Strategy

Kod:

```text
function
class
module
impl block
symbol group
logical section
```

Dokumentacja:

```text
heading-aware chunks
paragraph groups
code blocks
tables
```

Nie używać wyłącznie sztywnego chunk size.

---

# 7. Chunk Metadata

Każdy chunk:

```text
chunk_id
project_id
file_path
language
symbol
symbol_type
start_line
end_line
git_commit
content_hash
embedding_model
embedding_version
created_at
updated_at
```

---

# 8. Incremental Indexing

Nie indeksować całego repo po każdej zmianie.

Pipeline:

```text
git diff / file hash
↓
changed files
↓
changed chunks
↓
re-embed only changed data
```

---

# 9. Symbol Graph

Poza vector index utrzymuj relacje:

```text
imports
calls
implements
extends
uses
depends_on
tests
configures
```

Przykład:

```text
scheduler.py
  ├── imports policy.py
  ├── uses WorkerRegistry
  └── tested_by test_scheduler.py
```

---

# 10. Vector Memory

Nowa pamięć semantyczna:

```text
User Memory
Project Memory
Agent Memory
Task Memory
Run Memory
Experience Memory
Cross-Project Memory
```

Każdy memory record:

```text
memory_id
scope
scope_id
type
content
summary
embedding
importance
confidence
provenance
created_at
last_used_at
usage_count
ttl
pinned
```

---

# 11. Memory Types

```text
decision
fact
constraint
preference
architecture
failure
fix
lesson
pattern
dependency
test_result
security_note
performance_note
```

---

# 12. Memory Importance

Przykładowa skala:

```text
0.0 - 1.0
```

Wpływa na retrieval.

Przykład:

```text
critical architecture decision = 0.95
temporary debug note = 0.35
```

---

# 13. Memory Provenance

Każda pamięć musi mieć źródło:

```text
task_id
run_id
agent
artifact
file
commit
manual
```

Nie zapisywać „wiedzy” bez provenance.

---

# 14. Memory Write Policy

Nie każde zdanie z agent output trafia do pamięci.

Memory write powinno przejść:

```text
candidate memory
↓
importance evaluation
↓
deduplication
↓
policy check
↓
persist
```

---

# 15. Memory Deduplication

Przed zapisem:

```text
semantic similarity
exact hash
same provenance
same project
```

Jeśli duplikat:
- zwiększ usage/confidence,
- nie twórz kolejnego wpisu.

---

# 16. Memory Retrieval

Query:

```text
task goal
current stage
agent role
project
recent errors
current files
```

Ranking:

```text
semantic similarity
importance
recency
scope proximity
usage success
confidence
```

---

# 17. Scope Priority

Przykład:

```text
Task Memory
> Project Memory
> Agent Memory
> Cross-Project Memory
> Global Memory
```

ale zależnie od kontekstu.

---

# 18. Embedding Engine

Nowy abstraction layer:

```python
embed(text, model=None)
embed_batch(texts, model=None)
```

Provider może być:

```text
local
Ollama embedding model
sentence-transformers
remote embeddings provider
```

---

# 19. Local-First Embeddings

Preferowane dla prywatności:

```text
sentence-transformers
Ollama embeddings
local embedding model
```

Remote embeddings tylko jeśli policy pozwala.

---

# 20. Embedding Model Registry

Każdy model:

```text
id
provider
dimension
max_tokens
local
cost
latency
quality_score
enabled
```

---

# 21. Vector Store

Warstwa abstrakcji:

```python
upsert(...)
query(...)
delete(...)
rebuild(...)
stats(...)
```

---

# 22. Vector Store Options

Wspieraj co najmniej:

```text
SQLite + vector extension, jeśli dostępne
FAISS
Chroma
Qdrant local
```

Nie wiąż core z jednym vendor-specific backendem.

---

# 23. Domyślny Backend

Dla pojedynczego serwera preferuj:

```text
FAISS lub local lightweight store
```

Dla distributed:
- centralny vector store,
- lokalne read-through caches na workerach.

---

# 24. Vector Index Metadata DB

SQLite pozostaje źródłem metadanych.

Vector store przechowuje:
- embeddings,
- vector IDs.

SQLite:
- provenance,
- file paths,
- scopes,
- versions.

---

# 25. Retrieval Engine

API:

```python
retrieve_context(
    query,
    project_id=None,
    task_id=None,
    agent_name=None,
    top_k=20,
    filters=None,
)
```

---

# 26. Hybrid Retrieval

Nie polegaj tylko na vector similarity.

Łącz:

```text
semantic search
keyword search
symbol lookup
git history
memory
artifact search
```

---

# 27. Reranker

Top-N wyników przechodzi przez reranker:

```text
100 candidates
↓
hybrid score
↓
30
↓
reranker
↓
10 final
```

---

# 28. Ranking Score

Przykład:

```text
semantic          40%
symbol proximity  20%
project scope     15%
recency           10%
importance        10%
usage success      5%
```

---

# 29. Context Builder v2

Context Builder z beta1 dostaje nowy pipeline:

```text
Task
↓
Task classification
↓
Relevant memories
↓
Semantic code retrieval
↓
Artifacts
↓
Agent-specific routing
↓
Token budget
↓
Compression
↓
Final Context Package
```

---

# 30. Context Package

Przykład:

```json
{
  "task": {},
  "project_summary": "...",
  "relevant_files": [],
  "symbols": [],
  "memories": [],
  "artifacts": [],
  "constraints": [],
  "recent_failures": [],
  "token_budget": 24000
}
```

---

# 31. Context Routing

Różni agenci dostają różny context.

Planner:
- architecture,
- project summary,
- historical decisions.

Coder:
- files,
- symbols,
- tests,
- constraints.

Tester:
- changed files,
- test map,
- known failures.

Reviewer:
- diff,
- policy,
- architecture,
- acceptance criteria.

---

# 32. Context Compression

Jeśli context przekracza budżet:

```text
deduplicate
↓
drop low-score chunks
↓
summarize long artifacts
↓
compress historical context
↓
preserve critical constraints
```

---

# 33. Never Drop Rules

Nigdy nie usuwać z context compression:

```text
task goal
security constraints
policy constraints
approval requirements
critical architecture decisions
acceptance criteria
```

---

# 34. Task Classifier

Classifier rozpoznaje typ zadania:

```text
coding
bugfix
refactor
research
security
performance
documentation
testing
architecture
deployment
data analysis
```

---

# 35. Task Complexity

Ocena:

```text
LOW
MEDIUM
HIGH
VERY_HIGH
```

Czynniki:
- liczba modułów,
- rozmiar repo,
- ryzyko,
- cross-project scope,
- required agents,
- expected runtime.

---

# 36. Task Classifier API

```python
classify_task(title, description, project_context)
```

Wynik:

```json
{
  "type": "bugfix",
  "complexity": "HIGH",
  "required_roles": [
    "planner",
    "coder",
    "tester",
    "reviewer"
  ],
  "recommended_context": [
    "code",
    "tests",
    "recent_failures"
  ]
}
```

---

# 37. Agent Specialization

Agent Registry może mieć specialization profiles:

```text
rust-kernel
python-backend
frontend
security
networking
database
testing
devops
documentation
```

---

# 38. Agent Profile

```text
name
role
specializations
preferred_models
supported_languages
tools
historical_success
avg_runtime
quality_score
```

---

# 39. Model Router

Model Router wybiera:

```text
provider
model
reason
fallbacks
budget estimate
```

---

# 40. Router Inputs

```text
task type
complexity
agent role
project language
context size
latency requirement
budget
provider health
provider availability
historical quality
policy
privacy requirement
```

---

# 41. Router Output

Przykład:

```json
{
  "provider": "claude",
  "model": "preferred-coding-model",
  "score": 91,
  "fallbacks": [
    "codex",
    "gemini"
  ],
  "reasons": [
    "large Rust context",
    "high coding quality",
    "budget available"
  ]
}
```

---

# 42. Model Registry

Tabela logiczna:

```text
provider
model
capabilities
context_window
tool_use
coding_score
reasoning_score
latency_score
cost_input
cost_output
local
privacy_level
enabled
```

---

# 43. Provider Health Integration

Router musi używać observability:

```text
healthy
degraded
rate_limited
offline
auth_failed
```

Nie wybierać provider offline.

---

# 44. Budget Integration

Router musi uwzględniać:
- task budget,
- daily budget,
- token budget.

Jeśli high-end model przekracza budżet:
- wybierz tańszy,
- albo approval.

---

# 45. Policy Integration

Przykład:

```text
project sensitive
↓
remote provider forbidden
↓
router selects local Ollama
```

---

# 46. Privacy Routing

Mode:

```text
LOCAL_ONLY
PRIVATE_REMOTE
ANY_APPROVED
```

---

# 47. Automatic Provider Selection

CLI może pozwolić:

```text
provider = auto
model = auto
```

Router decyduje dynamicznie.

---

# 48. Fallback Chain

```text
primary model
↓ failure
fallback #1
↓ failure
fallback #2
```

Każdy fallback:
- policy check,
- budget check,
- capability check.

---

# 49. Experience Memory

Po zakończeniu taska zapisuj:

```text
what worked
what failed
which model
which agent
runtime
cost
test outcome
review outcome
retries
handoffs
```

---

# 50. Experience Record

```json
{
  "task_type": "rust bugfix",
  "provider": "claude",
  "model": "...",
  "agent": "coder",
  "outcome": "success",
  "runtime": 312,
  "retries": 0,
  "review_pass": true
}
```

---

# 51. Quality Signals

Źródła jakości:

```text
tests passed
review verdict
user approval
merge success
rollback occurred
retries
post-merge failure
manual rating
```

---

# 52. Quality Score

Per:

```text
model
agent
task type
project
specialization
```

Nie traktować score jako prawdy absolutnej.

To heurystyka do routingu.

---

# 53. Learned Routing

Router może korzystać z historii:

```text
"for Rust kernel tasks, model X had 92% review-pass"
```

ale:
- bez autonomicznego trenowania modelu,
- tylko heurystyczne statystyki v5.2.

---

# 54. Cross-Project Knowledge

AgentBox może wykorzystywać patterns z innych projektów.

Przykład:
- testing patterns,
- deployment patterns,
- architecture lessons.

Nie mieszać project-specific secrets.

---

# 55. Cross-Project Memory Policy

Record musi być oznaczony:

```text
shareable=true/false
```

Default:
- false dla sensitive,
- true tylko dla generic lessons.

---

# 56. Semantic Search CLI

```bash
agent5 search "scheduler recovery"
```

Filtry:

```bash
agent5 search \
  "memory allocator" \
  --project PROJECT_ID \
  --type code \
  --limit 20
```

---

# 57. Memory CLI

```bash
agent5 memory search "..."
agent5 memory show MEMORY_ID
agent5 memory stats
agent5 memory compact
agent5 memory deduplicate
```

---

# 58. Index CLI

```bash
agent5 index build PROJECT_ID
agent5 index update PROJECT_ID
agent5 index status PROJECT_ID
agent5 index stats PROJECT_ID
agent5 index rebuild PROJECT_ID
```

---

# 59. Router CLI

```bash
agent5 router explain TASK_ID
```

Wynik:

```text
Task type: bugfix
Complexity: HIGH
Agent: coder
Selected: claude / model-x
Fallback: codex / model-y
Reason:
- Rust project
- large context
- provider healthy
- budget OK
```

---

# 60. Context CLI

```bash
agent5 context build TASK_ID --agent coder
agent5 context inspect TASK_ID --agent reviewer
```

---

# 61. Intelligence Dashboard

Nowe sekcje:

```text
Semantic Index
Memory
Model Router
Context
Experience
Quality
```

---

# 62. Semantic Index Dashboard

Pokazuje:

```text
Project
Indexed files
Chunks
Symbols
Last update
Embedding model
Index health
```

---

# 63. Search UI

Global semantic search:

```text
Search code, memory, artifacts, decisions
```

Filtry:
- project,
- type,
- agent,
- date,
- source.

---

# 64. Memory UI

Widoki:

```text
Project Memory
Experience Memory
Agent Memory
Task Memory
Cross-Project
```

---

# 65. Router Dashboard

Tabela:

```text
Task
Agent
Selected Provider
Model
Score
Fallback
Budget Estimate
Reason
```

---

# 66. Quality Dashboard

Statystyki:

```text
Model success rate
Review pass rate
Average runtime
Retries
Cost
Task types
```

---

# 67. Distributed Worker Integration

Worker może posiadać lokalne:

```text
embedding capability
GPU
vector cache
local model
```

Scheduler może wysłać:
- indexing task,
- embedding task,
- reranking task

na worker z odpowiednią capability.

---

# 68. Intelligence Worker Labels

Przykład:

```text
embedding
gpu
ollama
reranker
large-memory
```

---

# 69. Distributed Indexing

Central metadata DB.

Workers:
- process file chunks,
- generate embeddings,
- return vectors.

Control Plane:
- validates,
- stores,
- updates index.

---

# 70. Embedding Job Queue

Nowy job type:

```text
index.scan
index.chunk
index.embed
index.commit
```

---

# 71. Embedding Cache

Hash:

```text
content_hash + embedding_model + model_version
```

Jeśli istnieje:
- reuse embedding.

---

# 72. Index Versioning

Każdy projekt:

```text
index_version
embedding_model
embedding_version
last_commit
```

---

# 73. Reindex Rules

Reindex jeśli:
- model changed,
- chunking algorithm changed,
- parser version changed.

---

# 74. Vector Store Backup

Vector store musi mieć backup/export.

Metadane + index checksum.

---

# 75. Vector Store Recovery

Jeśli index uszkodzony:
- rebuild from source,
- nie traktować vector store jako source of truth.

---

# 76. SQLite Migration

Dodaj tabele:

```sql
CREATE TABLE IF NOT EXISTS semantic_indexes (
    id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL,
    embedding_model TEXT NOT NULL,
    embedding_version TEXT,
    index_version INTEGER NOT NULL DEFAULT 1,
    status TEXT NOT NULL DEFAULT 'new',
    last_commit TEXT,
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
    vector_id TEXT,
    metadata_json TEXT,
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
```

---

# 77. Index Security

Nie indeksować:
- private keys,
- `.env`,
- token files,
- secrets,
- credential stores.

Secret scanner przed embedding.

---

# 78. Remote Embedding Security

Jeśli remote embedding:
- policy check,
- secret scan,
- content classification,
- audit event.

---

# 79. Intelligence Events

Dodaj:

```text
index.started
index.completed
index.failed
chunk.created
embedding.created
embedding.cache_hit

memory.created
memory.retrieved
memory.deduplicated

router.selected
router.fallback
router.failed

context.built
context.compressed

experience.recorded
quality.updated
```

---

# 80. Intelligence Metrics

```text
agentbox_index_chunks_total
agentbox_index_duration_seconds
agentbox_embedding_requests_total
agentbox_embedding_cache_hits_total
agentbox_memory_retrievals_total
agentbox_context_tokens_before
agentbox_context_tokens_after
agentbox_router_decisions_total
agentbox_router_fallbacks_total
agentbox_quality_review_pass_rate
```

---

# 81. Context Efficiency

Dashboard pokazuje:

```text
raw candidate tokens
final context tokens
compression ratio
retrieval hits used
retrieval hits discarded
```

---

# 82. Search Evaluation

Utwórz zestaw test queries dla projektów.

Mierzyć:
- recall@k,
- precision@k,
- MRR opcjonalnie.

---

# 83. Router Evaluation

Test matrix:

```text
coding small
coding large
security
research
documentation
local-only
low-budget
provider degraded
```

---

# 84. Intelligence Self-Test

```bash
agent5 selftest --intelligence
```

Sprawdza:

```text
semantic index
embedding provider
vector store
memory retrieval
reranker
task classifier
model router
context builder
experience store
quality signals
```

---

# 85. Smoke Test A — Semantic Search

```text
index project
↓
query known symbol
↓
correct file in top results
```

---

# 86. Smoke Test B — Memory Retrieval

```text
store architecture decision
↓
new related task
↓
memory retrieved
↓
context contains decision
```

---

# 87. Smoke Test C — Router

```text
high complexity coding task
↓
router evaluates models
↓
selects capable provider
↓
decision audited
```

---

# 88. Smoke Test D — Budget-Aware Routing

```text
expensive model exceeds task budget
↓
router selects cheaper compatible model
```

---

# 89. Smoke Test E — Privacy Routing

```text
LOCAL_ONLY task
↓
remote providers excluded
↓
local model selected
```

---

# 90. Smoke Test F — Context Compression

```text
retrieved context > model budget
↓
compression
↓
critical constraints retained
↓
final context below limit
```

---

# 91. Acceptance Criteria

v5.2 jest gotowa jeśli:

- [ ] semantic indexing działa
- [ ] incremental indexing działa
- [ ] secret files nie są indeksowane
- [ ] vector store działa
- [ ] vector store można odbudować
- [ ] memory retrieval działa
- [ ] memory deduplication działa
- [ ] provenance jest zachowane
- [ ] hybrid retrieval działa
- [ ] reranker działa
- [ ] context routing per agent działa
- [ ] context compression działa
- [ ] critical context nie jest tracony
- [ ] task classifier działa
- [ ] model router działa
- [ ] provider health wpływa na routing
- [ ] budget wpływa na routing
- [ ] privacy policy wpływa na routing
- [ ] fallback działa
- [ ] experience memory działa
- [ ] quality signals zapisują się
- [ ] distributed indexing działa
- [ ] intelligence dashboard działa
- [ ] intelligence selftest PASS
- [ ] rollback path istnieje

---

# 92. Deployment Guard

Control Plane:

```bash
agentbox-deploy-guard
```

v5.2 deploy tylko na:

```text
hostname=cursor
user=box
root=/workspace/agentbox-v5
```

---

# 93. Backup Before v5.2

Backup:
- SQLite,
- config,
- model registry,
- memory metadata,
- vector store,
- index metadata,
- current release.

---

# 94. Upgrade Sequence

```text
deployment guard
↓
v5.1 selftest
↓
backup
↓
maintenance
↓
stop intelligence workers
↓
migration
↓
install modules
↓
vector backend init
↓
index migration
↓
selftest
↓
reindex selected test project
↓
smoke tests
↓
activate
```

---

# 95. Rollback

Jeśli v5.2 fails:
- disable intelligence features,
- restore DB backup,
- restore vector index snapshot,
- switch release,
- v5.1 remains operational.

---

# 96. Feature Flags

Wprowadź:

```ini
[intelligence]
semantic_index = true
vector_memory = true
model_router = true
context_compression = true
experience_learning = true
cross_project = false
```

Cross-project może pozostać wyłączone domyślnie.

---

# 97. Compatibility Mode

Jeśli vector backend unavailable:

```text
fallback:
keyword + symbol + classic memory
```

AgentBox nie może całkowicie przestać działać.

---

# 98. Model Router Safety

Router:
- nie może sam zwiększać budget,
- nie może bypassować policy,
- nie może użyć disabled provider,
- nie może wysłać private context do niedozwolonego remote model.

---

# 99. Intelligence Report

Po wdrożeniu wygenerować:

```text
INTELLIGENCE_REPORT_v5.2.0.md
```

Zawiera:

```text
Indexed projects
Chunks
Vector backend
Embedding model
Memory count
Router models
Search evaluation
Context compression stats
Quality signals
Selftest
Open issues
Rollback path
```

---

# 100. Następny etap roadmapy

## AgentBox v5.3 — Autonomous Planning & Workflow Intelligence

Zakres:

```text
Dynamic Task Decomposition
Adaptive Agent Graphs
Plan Revision
Goal Tracking
Automatic Subtasks
Dependency Prediction
Dynamic Handoffs
Autonomous Retry Strategy
Workflow Templates
Long-Horizon Task State
Execution Reflection
Plan Quality Evaluation
```

v5.3 powinno wykorzystać intelligence layer z v5.2 do lepszego autonomicznego planowania, zamiast jedynie dodawać kolejną warstwę infrastruktury.
