# INTELLIGENCE_REPORT_v5.2.0

**Date:** 2026-09-19 (Europe/Warsaw / UTC+2)  
**Host:** cursor / 100.123.66.15  
**Root:** /workspace/agentbox-v5

## Indexed projects

| Project ID | Status | Files | Chunks | Model |
|------------|--------|-------|--------|-------|
| e14a8348571a | ready | 5 | 19 | local-hash-bow |

## Chunks / vectors

- semantic_chunks total: **19**
- vector_embeddings total: **21**
- by namespace: `{"code": 19, "memory": 2}`

## Vector backend

- **sqlite + float blobs + cosine** (pure Python; optional numpy)
- Rebuild: delete vectors + reindex from source (chunks are source of truth)

## Embedding model

- id: `local-hash-bow`
- dimension: 256
- version: 1
- local: True
- numpy available: False
- ollama available: False (optional path; not required for PASS)

## Memory count

- vector_memories listed: **2**
- experience records: **1**

## Router models

- `stub/default` local=True ctx=8000 caps=['coding', 'testing', 'documentation']
- `codex/default` local=False ctx=128000 caps=['coding', 'bugfix', 'refactor', 'testing']
- `claude/sonnet` local=False ctx=200000 caps=['coding', 'architecture', 'research', 'security', 'documentation']
- `ollama/local` local=True ctx=32000 caps=['coding', 'documentation', 'research']

## Search evaluation (smoke)

- Query: `finite_number calculator add` against demo-python → hits ≥1 including main.py / calculator symbols (**PASS**)

## Context compression

- Implemented: drop low-score hits, retain critical constraints (policy/approval/security)
- Wired into context builder via compress_package

## Quality signals

- total_signals: 1
- by_model rows: 1

## Selftest

- `agent5 selftest` → **RESULT: PASS** (intelligence section + prior v5.1/stable/rc1/beta stacks)

## Open issues

- Hash/BoW embeddings are deterministic but weaker than neural models; Ollama/sentence-transformers optional later
- Cross-project memory feature-flagged off (`cross_project = false`)
- Brute-force cosine OK for local; FAISS not required for v5.2 acceptance

## Rollback path

1. Disable intelligence feature flags in `config/intelligence.toml`
2. Restore DB from pre-install backup under `~/.local/share/agentbox/v5/backups/`
3. Reinstall v5.1.0 tree / set VERSION 5.1.0
4. v5.1 workers + stable ops remain operational without intelligence routes
