# AgentBox v5.6 — Operations Autopilot & Autonomous Platform Maintenance

**Previous:** 5.5.0  
**Version:** 5.6.0  
**Host:** cursor / 100.123.66.15 / box / /workspace/agentbox-v5

## Goal
Safe automated platform maintenance using evaluation signals + doctor/recovery:

- Automated Health Remediation (low-risk auto; high-risk → approval)
- Predictive Maintenance / Resource Forecasting (simple thresholds)
- Capacity Planning hints
- Auto Cleanup (logs, old artifacts, orphan PIDs dry-run default)
- Smart Backup Scheduling
- Upgrade Readiness Analysis
- Configuration / Worker / Provider Drift Detection
- Self-Healing Playbooks + Runbook Automation
- Maintenance Planning
- Human-Approved High-Risk Remediation

## MUST
1. `lib/ops_autopilot/` or extend `lib/ops/`: playbooks, drift, forecast, cleanup, backup_schedule, remediation, readiness
2. Schema: playbook_runs, remediation_actions, drift_snapshots, maintenance_plans
3. CLI: `agent5 ops status|scan|remediate|--dry-run|playbook list|run|drift|forecast|cleanup|backup-schedule`
4. Fix `agent5 doctor` version check to accept any `5.x.y` as OK (current DEGRADED bug)
5. Low-risk auto: restart sampler, prune old logs, clear stale PID files
6. High-risk: quarantine worker, restore backup → require approval
7. REST `/api/v1/ops/*` + Dashboard Ops page
8. Selftest PASS; VERSION 5.6.0; web RUNNING; report live/v56-report.md
9. Push updates to GitHub RaCzKoViC/AgentBox after PASS (no secrets)
10. README next note TBD

Respect Policy/Risk/Budget/Approval. deploy-guard on install.
