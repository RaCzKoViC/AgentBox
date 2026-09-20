#!/usr/bin/env bash
# AgentBox v5 — task helpers
set -euo pipefail

# shellcheck source=state.sh
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/state.sh"

ab5_task_create() {
  ab5_ensure_env
  ab5_db create-task "$@"
}

ab5_task_list() {
  ab5_ensure_env
  ab5_db list-tasks "$@"
}

ab5_task_show() {
  ab5_ensure_env
  ab5_db get-task "$@"
}

ab5_task_set_status() {
  ab5_ensure_env
  ab5_db set-status "$@"
}
