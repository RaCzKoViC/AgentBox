#!/usr/bin/env bash
# AgentBox v5 — sandbox shell helpers (alpha3)
set -euo pipefail

ab5_sandbox_path() {
  local task_id="$1"
  local root="${AGENTBOX_V5_HOME:-$HOME/.local/share/agentbox/v5}"
  echo "${root}/data/tasks/${task_id}/worktree"
}

ab5_sandbox_create() {
  local task_id="$1"; shift || true
  ab5_ensure_env
  python3 "${AGENTBOX_V5_LIB}/sandbox/manager.py" create "$task_id" "$@"
}

ab5_sandbox_inspect() {
  ab5_ensure_env
  python3 "${AGENTBOX_V5_LIB}/sandbox/manager.py" inspect "$1"
}

ab5_sandbox_destroy() {
  ab5_ensure_env
  python3 "${AGENTBOX_V5_LIB}/sandbox/manager.py" destroy "$1"
}
