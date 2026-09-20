# AgentBox v5.5.0 — Evaluation Platform Report

**Date:** 2026-09-20 (Europe/Warsaw UTC+2)  
**Host:** cursor / 100.123.66.15 / box  
**Root:** `/workspace/agentbox-v5`  
**Previous:** 5.4.0  
**Result:** **PASS**

## Summary

Implemented Self-Improvement, Evaluation & Benchmarking:

- `lib/evaluation/` — harness, suites, cases, metrics, scoring, baselines, regressions, quality_gates, proposals, prompt_versioning, workflow_versioning, failure_mining (clustering), ab_test stub, store, cli
- `lib/benchmarks/` — registry, runners, tasks/tools/workflows stubs
- Golden suite `benchmarks/golden/` (≥3 cases): `memory_retrieval`, `tool_git_status`, `plan_software_feature` — fast deterministic, no Codex
- Schema migration **0010 / mig_0010_evaluation**: `benchmark_suites`, `benchmark_cases`, `evaluation_runs`, `evaluation_results`, `baselines`, `improvement_proposals`, `prompt_versions`, `workflow_versions`, `regression_events`
- CLI: `agent5 eval list|run|show`, `benchmark list`, `propose list|show|approve|reject`, `baseline show`
- Quality gate: fail run if score < threshold (default 0.80) or critical case fails; regression events recorded
- Improvement proposals from failure mining — **human approve required**; `AGENTBOX_AUTO_APPROVE` only for low-risk explicit `--apply`
- REST: `/api/v1/eval/...`, `/api/v1/proposals`, `/api/v1/benchmarks`, `/api/v1/quality-gates/check`
- Dashboard: **Eval** page (suites, runs, baselines, proposals, failure clusters)
- VERSION **5.5.0**; deploy-guard OK; pre-install backup; web RUNNING HTTP 200

## Verification

| Check | Result |
|-------|--------|
| `agent5 version` | `5.5.0` |
| `agent5 selftest` | `RESULT: PASS` (evaluation + tools + planning + intelligence + distributed + ops) |
| Golden suite | PASS score 1.0 / gate PASS / 3/3 cases |
| Baseline | set for `golden` |
| Propose mine → reject | OK |
| Propose approve (+ apply LOW) | promoted |
| Web `/` | HTTP 200, version 5.5.0, Eval nav present |
| Deploy guard | cursor / box / 100.123.66.15 |

## Safety

Self-improvement = **measure + propose**. Core is never auto-mutated. Proposal apply requires explicit `--apply`, `risk_level=LOW`, and `AGENTBOX_AUTO_APPROVE=1`. `auto_promotion = false` in `config/evaluation.toml`.

## Backup / Deploy

- Deploy guard: OK
- Pre-v5.5 backup: `bkp_20260919_235744_pre_v55`
- Install backup: `stable-install-20260920-000111`

## Rollback

Disable evaluation flags in `config/evaluation.toml` (`[self_improvement] evaluation=false`), restore DB backup if needed, reinstall 5.4.0. Historical evaluation rows can be preserved.

## Next (not implemented)

**v5.6 — Operations Autopilot & Autonomous Platform Maintenance**
