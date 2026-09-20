#!/usr/bin/env bash
# AgentBox v5 — SQLite helpers (wraps db.py)
set -euo pipefail

_ab5_find_db_py() {
  if [[ -n "${AGENTBOX_V5_LIB:-}" && -f "${AGENTBOX_V5_LIB}/storage/db.py" ]]; then
    echo "${AGENTBOX_V5_LIB}/storage/db.py"
    return
  fi
  local here
  here="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
  if [[ -f "${here}/storage/db.py" ]]; then
    echo "${here}/storage/db.py"
    return
  fi
  # source tree: lib/core -> lib/storage
  if [[ -f "${here}/../lib/storage/db.py" ]]; then
    echo "${here}/../lib/storage/db.py"
    return
  fi
  echo "db.py not found" >&2
  return 1
}

ab5_db() {
  local py
  py="$(_ab5_find_db_py)"
  python3 "$py" "$@"
}

ab5_data_root() {
  echo "${AGENTBOX_V5_HOME:-$HOME/.local/share/agentbox/v5}"
}

ab5_db_path() {
  echo "${AGENTBOX_V5_DB:-$(ab5_data_root)/data/agentbox.db}"
}

ab5_ensure_env() {
  export AGENTBOX_V5_HOME="$(ab5_data_root)"
  export AGENTBOX_V5_DB="$(ab5_db_path)"
  if [[ -z "${AGENTBOX_V5_LIB:-}" ]]; then
    if [[ -d "$HOME/.local/lib/agentbox5" ]]; then
      export AGENTBOX_V5_LIB="$HOME/.local/lib/agentbox5"
    else
      export AGENTBOX_V5_LIB="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
    fi
  fi
}
