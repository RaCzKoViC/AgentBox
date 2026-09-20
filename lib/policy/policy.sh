#!/usr/bin/env bash
# AgentBox v5 — policy shell helpers (alpha3)
set -euo pipefail

ab5_policy_check() {
  local action="${1:-}"
  ab5_ensure_env 2>/dev/null || true
  python3 "${AGENTBOX_V5_LIB}/policy/policies.py" check "$action"
}

ab5_budget_show() {
  ab5_ensure_env
  python3 "${AGENTBOX_V5_LIB}/policy/budgets.py" show
}

ab5_approval_list() {
  ab5_ensure_env
  python3 "${AGENTBOX_V5_LIB}/policy/approvals.py" list "$@"
}
