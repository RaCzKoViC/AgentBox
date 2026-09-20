# AgentBox

**Autonomous multi-agent execution platform** — Control Plane on a dedicated host with policy, budgets, risk, distributed workers, intelligence, planning, tools, and evaluation.

| | |
|--|--|
| **Version** | `5.5.0` |
| **Org** | [RaCzKoViC](https://github.com/RaCzKoViC) |
| **Control Plane (example)** | Tailscale `100.123.66.15` · hostname `cursor` · user `box` |
| **Dashboard** | `http://<tailscale-ip>:8787` |

> **Security:** Never commit admin tokens, SSH passwords, or API keys. Use `agent5 web token` on the server and SSH keys / your password manager for login.

---

## What it is

AgentBox turns a Linux host into a **Control Plane** for AI coding agents:

- Task queue + Git worktrees + Codex/Claude runners  
- Policy / Budget / Risk / Approvals (enforcement on every sensitive action)  
- Observability (metrics, timeline, handoffs)  
- Memory + semantic index + model router  
- Autonomous planning (goals, workflows, plan revision)  
- Tool registry (file/git/shell/docker/http + MCP stub)  
- Evaluation harness + golden benchmarks + improvement proposals  
- Web dashboard (REST + WebSocket)  
- Remote workers (enroll / heartbeat / assign)

---

## Quick start (on Control Plane host)

```bash
git clone https://github.com/RaCzKoViC/AgentBox.git
cd AgentBox
./install.sh          # runs agentbox-deploy-guard when configured
agent5 version
agent5 selftest
agent5 web start
agent5 web token      # paste into http://<host>:8787/login
```

Shared live terminal (Termius + desktop):

```bash
agentbox-live    # tmux attach -t agentbox-live
```

---

## Documentation

| Doc | Description |
|-----|-------------|
| [docs/AGENTS.md](docs/AGENTS.md) | All agents & capabilities |
| [docs/SSH_AND_DEPLOY.md](docs/SSH_AND_DEPLOY.md) | SSH / Tailscale / Termius / deploy guard |
| [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) | Layered architecture |
| [docs/ROADMAP.md](docs/ROADMAP.md) | Version history & next steps |
| Specs under `docs/*-spec.md` | Design docs for each release |

---

## CLI surface (high level)

```text
agent5 status | doctor | selftest | start|stop|restart
agent5 task | queue | handoff | approval | policy | budget | risk
agent5 memory | intelligence | goal | plan | workflow | tool
agent5 worker | eval | benchmark | propose | backup | restore
agent5 web start|stop|status|token
agent5-worker enroll|start|status
```

---

## License

MIT — see [LICENSE](LICENSE).
