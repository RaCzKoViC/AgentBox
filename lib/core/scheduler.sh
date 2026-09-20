#!/usr/bin/env bash
# AgentBox v5 — scheduler (alpha2)
set -euo pipefail

# shellcheck source=state.sh
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/state.sh"

_ab5_scheduler_py() {
  if [[ -n "${AGENTBOX_V5_LIB:-}" && -f "${AGENTBOX_V5_LIB}/core/scheduler.py" ]]; then
    echo "${AGENTBOX_V5_LIB}/core/scheduler.py"
    return
  fi
  echo "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/scheduler.py"
}

ab5_scheduler_pick_ready() {
  local max_n="${1:-1}"
  ab5_ensure_env
  python3 "$(_ab5_scheduler_py)" pick-ready --max "$max_n"
}

ab5_scheduler_pick_for_workers() {
  local mw="${1:-2}"
  ab5_ensure_env
  python3 "$(_ab5_scheduler_py)" pick-for-workers --max-workers "$mw"
}

ab5_scheduler_tick() {
  local mw="${1:-2}"
  ab5_scheduler_pick_for_workers "$mw"
}

ab5_read_max_workers() {
  local cfg="${AGENTBOX_V5_HOME:-$HOME/.local/share/agentbox/v5}/config/agentbox.toml"
  local fallback=2
  if [[ ! -f "$cfg" ]]; then
    # try source tree / installed defaults
    if [[ -f "${AGENTBOX_V5_LIB:-}/../config/agentbox.toml" ]]; then
      cfg="$(cd "${AGENTBOX_V5_LIB}/.." && pwd)/config/agentbox.toml"
    elif [[ -f "$HOME/.local/share/agentbox/v5/config/agentbox.toml" ]]; then
      cfg="$HOME/.local/share/agentbox/v5/config/agentbox.toml"
    else
      echo "$fallback"
      return
    fi
  fi
  python3 -c '
import sys
try:
    import tomllib
except ImportError:
    try:
        import tomli as tomllib  # type: ignore
    except ImportError:
        print(sys.argv[2]); sys.exit(0)
path, fallback = sys.argv[1], int(sys.argv[2])
try:
    with open(path, "rb") as f:
        data = tomllib.load(f)
    print(int(data.get("scheduler", {}).get("max_workers", fallback)))
except Exception:
    print(fallback)
' "$cfg" "$fallback"
}
