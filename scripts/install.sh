#!/usr/bin/env bash
# AgentBox v5 — one-way deploy: source tree (this repo) -> installed locations.
#
#   scripts/install.sh [--dry-run] [--no-migrate]
#
# * Idempotent: rsync --checksum, only changed files are written.
# * Code only: lib/, bin/ launchers, VERSION, workflows/, benchmarks/.
#   Never touches the live DB, config/, secrets, tokens, venvs or logs.
# * Never deploys *.bak*, __pycache__ or *.pyc; installed-side backups are kept
#   (excluded files are protected from --delete).
# * Runs agentbox-deploy-guard first (host/user/tree check).  The guard's expected
#   hostname is taken from [doctor] expected_hostnames in the live agentbox.toml
#   when the current host is listed there (AGENTBOX_EXPECTED_HOST wins if set).
# * After a real deploy, pending DB migrations are applied (backup-first) unless
#   --no-migrate.  Restart daemon/web yourself if code they run changed:
#     agent5 daemon stop && agent5 daemon start ; agent5 web restart
set -euo pipefail

DRY=0
MIGRATE=1
for a in "$@"; do
  case "$a" in
    --dry-run|-n) DRY=1 ;;
    --no-migrate) MIGRATE=0 ;;
    -h|--help) sed -n '2,20p' "$0"; exit 0 ;;
    *) echo "unknown option: $a" >&2; exit 2 ;;
  esac
done

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd -P)"
BIN_DIR="${HOME}/.local/bin"
LIB_PARENT="${HOME}/.local/lib"
LIB_DIR="${LIB_PARENT}/agentbox5"
DATA_ROOT="${AGENTBOX_V5_HOME:-${HOME}/.local/share/agentbox/v5}"
VER="$(tr -d '[:space:]' < "$ROOT/VERSION")"

command -v rsync >/dev/null 2>&1 || { echo "[ERR] rsync not installed" >&2; exit 1; }
[[ -f "$ROOT/lib/storage/db.py" && -f "$ROOT/bin/agentbox5" ]] || { echo "[ERR] $ROOT is not an AgentBox v5 tree" >&2; exit 1; }

# --- deploy guard -----------------------------------------------------------
GUARD="$ROOT/bin/agentbox-deploy-guard"
[[ -x "$GUARD" ]] || GUARD="$(command -v agentbox-deploy-guard || true)"
[[ -n "$GUARD" ]] || { echo "[ERR] agentbox-deploy-guard missing" >&2; exit 1; }
if [[ -z "${AGENTBOX_EXPECTED_HOST:-}" && -f "$DATA_ROOT/config/agentbox.toml" ]]; then
  host_now="$(hostname -s 2>/dev/null || hostname)"
  if python3 - "$DATA_ROOT/config/agentbox.toml" "$host_now" <<'PY'
import re, sys
t = open(sys.argv[1]).read()
m = re.search(r"^\[doctor\](.*?)(?=^\[|\Z)", t, re.S | re.M)
hosts = re.findall(r'"([^"]+)"', re.search(r"expected_hostnames\s*=\s*\[(.*?)\]", m.group(1), re.S).group(1)) if m and "expected_hostnames" in m.group(1) else []
raise SystemExit(0 if sys.argv[2] in hosts else 1)
PY
  then
    export AGENTBOX_EXPECTED_HOST="$host_now"
  fi
fi
bash "$GUARD"

echo "== AgentBox ${VER} deploy $([[ $DRY == 1 ]] && echo '(DRY RUN)') =="
echo "source: $ROOT"

RS=(rsync -rlp --checksum --itemize-changes --out-format='%i %n%L')
[[ "$DRY" == 1 ]] && RS+=(--dry-run)
EXCL=(--exclude='__pycache__/' --exclude='*.pyc' --exclude='*.bak' --exclude='*.bak-*' --exclude='*.bak.*' --exclude='.git/')

CHANGES=0
run_rs() {  # label, rsync args...
  local label="$1"; shift
  local out
  out="$("${RS[@]}" "${EXCL[@]}" "$@")"
  out="$(grep -v '^\.d' <<<"$out" | grep -v '^$' || true)"
  if [[ -n "$out" ]]; then
    CHANGES=$((CHANGES + $(wc -l <<<"$out")))
    sed "s|^|  [$label] |" <<<"$out"
  fi
}

mkdir_p() { [[ "$DRY" == 1 ]] || mkdir -p "$@"; }
mkdir_p "$BIN_DIR" "$LIB_DIR" "$LIB_PARENT/workflows" "$LIB_PARENT/benchmarks" "$DATA_ROOT/workflows" "$DATA_ROOT/benchmarks"

run_rs lib --delete "$ROOT/lib/" "$LIB_DIR/"
for b in agentbox5 agentboxd agent5-worker agentbox-deploy-guard; do
  [[ -f "$ROOT/bin/$b" ]] && run_rs bin --chmod=F755 "$ROOT/bin/$b" "$BIN_DIR/$b"
done
run_rs version "$ROOT/VERSION" "$LIB_PARENT/VERSION"
run_rs version "$ROOT/VERSION" "$DATA_ROOT/VERSION"
[[ -d "$ROOT/workflows" ]] && { run_rs workflows "$ROOT/workflows/" "$LIB_PARENT/workflows/"; run_rs workflows "$ROOT/workflows/" "$DATA_ROOT/workflows/"; }
[[ -d "$ROOT/benchmarks" ]] && { run_rs benchmarks "$ROOT/benchmarks/" "$LIB_PARENT/benchmarks/"; run_rs benchmarks "$ROOT/benchmarks/" "$DATA_ROOT/benchmarks/"; }

if [[ "$(readlink "$BIN_DIR/agent5" 2>/dev/null)" != "$BIN_DIR/agentbox5" ]]; then
  CHANGES=$((CHANGES + 1)); echo "  [bin] symlink agent5 -> agentbox5"
  [[ "$DRY" == 1 ]] || ln -sfn "$BIN_DIR/agentbox5" "$BIN_DIR/agent5"
fi

echo "changes: $CHANGES"
if [[ "$DRY" == 1 ]]; then
  echo "dry run — nothing written"
  exit 0
fi

if [[ "$MIGRATE" == 1 ]]; then
  PY="python3"
  for c in "$DATA_ROOT/venv/bin/python3" "$DATA_ROOT/venv/bin/python"; do [[ -x "$c" ]] && { PY="$c"; break; }; done
  pending="$(AGENTBOX_V5_HOME="$DATA_ROOT" "$PY" "$LIB_DIR/ops/migrations.py" status 2>/dev/null \
    | "$PY" -c 'import json,sys; print(len(json.load(sys.stdin).get("pending",[])))' 2>/dev/null || echo "?")"
  if [[ "$pending" != "0" ]]; then
    echo "migrations pending: $pending — applying (backup first)"
    AGENTBOX_V5_HOME="$DATA_ROOT" "$PY" "$LIB_DIR/ops/migrations.py" run >/dev/null
    echo "migrations: applied"
  else
    echo "migrations: up to date"
  fi
fi
echo "deployed AgentBox ${VER}. Restart daemon/web if needed (see header)."
