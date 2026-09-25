# Changelog

## 5.6.3 — 2026-09-25

- **Isolated selftest + live guard**: `agent5 selftest` runs in a fresh `mkdtemp` dir
  (temp HOME / `AGENTBOX_V5_HOME` / DB, stub runner) and aborts if any resolved path points
  at the live data dir. Live config is never touched.
- **Doctor hostname check → WARN**: hostname mismatch is a WARN (not FAIL); allowed names come
  from `[doctor] expected_hostnames` in the live `agentbox.toml`.
- **Tasks API**: `GET /api/v1/tasks?order=asc|desc` (dashboard lists newest first);
  journal tasks (`provider=journal`) hide Queue/Resume in the dashboard so they cannot trigger a Codex run.
- **`scripts/install.sh`**: one-way, idempotent rsync deploy of the source tree into
  `~/.local/lib/agentbox5` + `~/.local/bin` launchers (+ VERSION, workflows, benchmarks),
  `--dry-run`, excludes `__pycache__`/`*.bak*`, never touches DB/config/secrets, runs the
  deploy guard, applies pending migrations (backup-first).
- **Pending decisions ("Czeka na Macieja")**: new `pending_decisions` table (migration 12),
  API `GET/POST /api/v1/pending`, `GET/PATCH /api/v1/pending/{id}` (+ `POST .../resolve`),
  CLI `agent5 pending list|add "text" [--context C]|resolve ID [--note N]|reopen ID`,
  dashboard nav section + Overview panel with open-count badge.
- **Daemon interpreter fix**: `agentboxd`, the runner, scheduler and graph helpers now call Python via
  a single resolved `AGENTBOX_V5_PYTHON` (AgentBox venv with PyYAML + psutil, fallback `python3`)
  instead of bare system `python3` (which lacks PyYAML/psutil — e.g. the resource sampler silently
  fell back to /proc).
- Repo hygiene: source tree is now a git checkout of `RaCzKoViC/AgentBox`; `.gitignore` covers
  `__pycache__`, `*.bak*`, DBs, venvs, logs, tokens, secrets.
