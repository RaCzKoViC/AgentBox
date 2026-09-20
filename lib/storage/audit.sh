#!/usr/bin/env bash
# AgentBox v5 — audit stub (writes JSONL under data/audit/)
set -euo pipefail

ab5_audit() {
  local action="$1"; shift
  local detail="${*:-}"
  local root="${AGENTBOX_V5_HOME:-$HOME/.local/share/agentbox/v5}"
  local dir="${root}/data/audit"
  mkdir -p "$dir"
  local ts
  ts="$(date -u '+%Y-%m-%dT%H:%M:%SZ')"
  printf '{"ts":"%s","action":"%s","detail":%s}\n' \
    "$ts" "$action" "$(python3 -c 'import json,sys; print(json.dumps(sys.argv[1]))' "$detail")" \
    >> "${dir}/audit.jsonl"
}
