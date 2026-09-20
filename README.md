# AgentBox v5.6.0 — Operations Autopilot

Versioned AgentBox v5 control plane. **v5.6 = Operations Autopilot** (playbooks, drift, forecast, cleanup, smart backup, remediation, upgrade readiness) on top of v5.5 Evaluation + v5.4 Tools + v5.3 Planning + v5.2 Intelligence + v5.1 Distributed Workers + Stable Ops.

> **Does not replace v4.9.** Launcher `~/.local/bin/agentbox` remains. v5 installs `agentbox5` (+ symlink `agent5`), `agentboxd`, and `agent5-worker`.
>
> **Low-risk auto; high-risk needs approval.** Playbooks like `quarantine_worker` / `restore_backup` never apply without human approval.
>
> **Deploy:** only host `cursor` / Tailscale `100.123.66.15` / user `box` / root `/workspace/agentbox-v5` — `agentbox-deploy-guard`.

## Operations Autopilot (v5.6)

```bash
agent5 ops status
agent5 ops scan
agent5 ops remediate --dry-run          # default dry-run
agent5 ops remediate --apply            # auto low-risk only
agent5 ops playbook list
agent5 ops playbook run clear_stale_pids --apply
agent5 ops drift
agent5 ops forecast
agent5 ops cleanup --dry-run
agent5 ops backup-schedule
agent5 ops readiness
agent5 ops plan --list
```

Pragmatic playbooks: `clear_stale_pids`, `prune_old_logs`, `smart_backup`, `restart_web_if_down`, `detect_config_drift` (LOW/auto). HIGH: `quarantine_worker`, `restore_backup`.

REST: `/api/v1/ops/status|scan|remediate|playbooks|drift|forecast|cleanup|backup-schedule|readiness|plans`  
Dashboard: **Ops** page.

Doctor version check accepts any semver `5.x.y`.

## Evaluation (v5.5) / Tools (v5.4) / Planning (v5.3) / …

```bash
agent5 eval list|run golden
agent5 tool list|run …
agent5 goal create … / agent5 plan create …
agent5 intelligence status|search …
agent5 worker list
```

## Install

```bash
cd /workspace/agentbox-v5
./install.sh
agent5 version   # 5.6.0
agent5 doctor    # HEALTHY
agent5 selftest  # RESULT: PASS
```

## Next (not implemented)

**TBD**
