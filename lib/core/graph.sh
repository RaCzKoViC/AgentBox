#!/usr/bin/env bash
# AgentBox v5 — dependency graph (alpha2)
set -euo pipefail

# shellcheck source=state.sh
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/state.sh"

_ab5_graph_py() {
  if [[ -n "${AGENTBOX_V5_LIB:-}" && -f "${AGENTBOX_V5_LIB}/core/graph.py" ]]; then
    echo "${AGENTBOX_V5_LIB}/core/graph.py"
    return
  fi
  echo "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/graph.py"
}

ab5_graph_show() {
  ab5_ensure_env
  "${AGENTBOX_V5_PYTHON:-python3}" "$(_ab5_graph_py)" show "$@"
}

ab5_graph_depend() {
  ab5_ensure_env
  "${AGENTBOX_V5_PYTHON:-python3}" "$(_ab5_graph_py)" depend "$@"
}

ab5_graph_depends_on() {
  ab5_graph_depend "$@"
}

ab5_graph_ready() {
  # True (exit 0) if task is ready (deps satisfied) — uses db list-ready
  local tid="${1:-}"
  [[ -n "$tid" ]] || return 1
  ab5_ensure_env
  "${AGENTBOX_V5_PYTHON:-python3}" -c '
import json, os, sys
sys.path.insert(0, os.environ["AGENTBOX_V5_LIB"] + "/storage")
import db
tid = sys.argv[1]
t = db.get_task(tid)
if not t:
    sys.exit(1)
sys.exit(0 if db.deps_satisfied(t) else 1)
' "$tid"
}
