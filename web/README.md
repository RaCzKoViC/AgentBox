# Web UI (Control Plane Dashboard)

Vanilla SPA served by FastAPI (`lib/web` is authoritative — `install.sh` copies `lib/` → `~/.local/lib/agentbox5`).
Mirror kept in repo-root `web/` for convenience.

Pages: Overview, Tasks, Approvals, Handoffs, Agents, Nodes, Intelligence, Plans, Tools, Eval, **Ops**, Metrics.
Auth: Bearer token via `sessionStorage` (`agent5 web token`).
