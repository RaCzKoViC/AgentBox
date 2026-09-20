# Architecture (v5.5)

```text
                 CLI / REST / Web UI / WebSocket
                              │
                        Control Plane
                              │
        ┌─────────────┬───────┼───────┬─────────────┐
        ▼             ▼       ▼       ▼             ▼
     Tasks        Policy    Risk   Budget      Approvals
        │             └───────┬───────┘             │
        ▼                     ▼                     ▼
    Scheduler            Enforcement            Audit/Events
        │
        ├── Planning (goals, graphs, workflows)
        ├── Intelligence (index, vectors, router)
        ├── Tools (registry, sandbox, MCP stub)
        ├── Handoffs / Agents registry
        ├── Workers (local + remote)
        └── Evaluation (golden, proposals)
                              │
                    Sandbox / Worktree / Providers
```

Data: `~/.local/share/agentbox/v5/`  
Config: `~/.config/agentbox-v5/`  
Source: this repository.
