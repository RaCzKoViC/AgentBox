# AgentBox — Agents & Capabilities Catalog

Pipeline and specialized agents used by the orchestrator / planner. Delegation is constrained by `can_delegate` in the agent registry and by Policy/Risk.

## Core pipeline agents

| Agent | Role | Typical capabilities | May delegate to |
|-------|------|----------------------|-----------------|
| **planner** | Decompose goals, pick workflow, create plan | read project, memory retrieve, intelligence search | researcher, architect |
| **researcher** | Dependency / API / codebase research | read-only tools, semantic search | — |
| **architect** | Design & structure | read/write design docs | security, performance, coder |
| **coder** | Implement changes in worktree | file write, git, shell (gated), Codex | tester, debugger |
| **tester** | Run tests, report | shell tests, git | debugger |
| **reviewer** | Quality / VERDICT | read-only review | security, debugger |
| **merger** | Merge approved worktrees | git merge (approval) | — |
| **debugger** | Fix failing runs | file write, shell, logs | — |
| **security** | Security review handoff | read-only / reports | — |
| **performance** | Perf suggestions (often optional handoff) | benchmarks, profiling notes | — |

## Control-plane “system agents”

| Component | What it does |
|-----------|----------------|
| **agentboxd** | Daemon: queue workers, sampler, scheduler hooks |
| **agentbox-web** | FastAPI + Dashboard + WebSocket hub (`:8787`) |
| **agent5-worker** | Remote/local worker runtime (enroll, heartbeat, execute assignments) |
| **enforcement** | Policy → Risk → Budget → Approval before actions/tools |
| **intelligence** | Semantic index, vector memory, model router |
| **planning** | Goals, task graphs, workflow templates, reflection |
| **tools** | Registry v2 + sandboxed tool executor |
| **evaluation** | Golden benchmarks, proposals (human-approved) |

## Built-in tools (v5.4+)

| Tool | Risk | Notes |
|------|------|-------|
| `file.read` / `file.write` | LOW / MODERATE | Workspace-only writes |
| `git.status` / `git.diff` | LOW | |
| `shell.run` | HIGH→approval / CRITICAL deny | Allowlist + denylist |
| `http.get` | MODERATE | Outbound gated by policy |
| `docker.ps` | LOW | If Docker available |

## Workflow templates (`workflows/`)

- `software_feature`, `bugfix`, `refactor`, `security_review`
- `release`, `research`, `migration`, `incident`

## Providers

- **Codex** (`codex exec --approve-for-me` / read-only stages)  
- **Stub** (tests / offline)  
- Optional Claude / others via provider config (never commit API keys)

## Grok Bot companion agents (ops side)

When operating from Grok Bot / Cursor desktop, related assistants may include photo/style agents — they are **not** part of the AgentBox Control Plane runtime. AgentBox agents above are the execution graph.
