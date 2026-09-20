#!/usr/bin/env bash
# Install AgentBox v5.6.0 (Ops Autopilot + Evaluation + Tools + Planning + Intelligence + Distributed)
set -euo pipefail

command -v agentbox-deploy-guard >/dev/null 2>&1 || { echo "[ERR] guard missing"; exit 1; }
agentbox-deploy-guard
ROOT="/workspace/agentbox-v5"
[[ "$(pwd -P)" == "$ROOT"* ]] || cd "$ROOT"

ROOT="$(cd "$(dirname "$0")" && pwd)"
VER="$(tr -d '[:space:]' < "$ROOT/VERSION")"
BIN_DIR="${HOME}/.local/bin"
LIB_DIR="${HOME}/.local/lib/agentbox5"
DATA_ROOT="${HOME}/.local/share/agentbox/v5"

echo "== AgentBox ${VER} install =="
echo "Source: $ROOT"
echo "NOTE: will NOT overwrite ${BIN_DIR}/agentbox (v4.9)"
echo "Autonomous: AGENTBOX_AUTO_APPROVE=1 (non-CRITICAL auto-approved; CRITICAL still DENY)"

# Backup before migrations (§20)
STAMP="$(date +%Y%m%d-%H%M%S)"
BACKUP="${DATA_ROOT}/backups/stable-install-${STAMP}"
BACKUP_ALT="${HOME}/.local/share/agentbox-v5/backups/stable-install-${STAMP}"
mkdir -p "$BACKUP" "$BACKUP_ALT"
cp -a "$ROOT" "$BACKUP/project" 2>/dev/null || true
cp -a "${DATA_ROOT}/data/agentbox.db" "$BACKUP/agentbox.db" 2>/dev/null || true
# also legacy path from spec
cp -a "${HOME}/.local/share/agentbox-v5/agentbox.db" "$BACKUP/agentbox-legacy.db" 2>/dev/null || true
cp -a "${HOME}/.config/agentbox-v5" "$BACKUP/config" 2>/dev/null || true
cp -a "${DATA_ROOT}/config" "$BACKUP/share-config" 2>/dev/null || true
cp -a "$BACKUP/." "$BACKUP_ALT/" 2>/dev/null || true
echo "  backup: $BACKUP"

mkdir -p "$BIN_DIR" "$LIB_DIR" \
  "$DATA_ROOT"/{config,data/{artifacts,memory,audit,tasks},memory/{user,project,agent,task},artifacts,runtime/{locks,pids/workers,queue,sockets},logs,backups} \
  "${HOME}/.config/agentbox-v5"

# Preserve Codex runner if source is stub
PRESERVE_RUNNER=""
SRC_HAS_CODEX=0
INST_HAS_CODEX=0
if grep -qE 'ab5_run_codex|codex exec' "$ROOT/lib/core/runner.sh" 2>/dev/null; then
  SRC_HAS_CODEX=1
fi
if [[ -f "$LIB_DIR/core/runner.sh" ]] && grep -qE 'ab5_run_codex|codex exec' "$LIB_DIR/core/runner.sh" 2>/dev/null; then
  INST_HAS_CODEX=1
fi
if [[ "$INST_HAS_CODEX" -eq 1 && "$SRC_HAS_CODEX" -eq 0 ]]; then
  PRESERVE_RUNNER="$(mktemp)"
  cp -f "$LIB_DIR/core/runner.sh" "$PRESERVE_RUNNER"
  echo "  preserve: existing Codex runner.sh (source is stub)"
fi
rm -rf "${LIB_DIR:?}/"*
cp -a "$ROOT/lib/." "$LIB_DIR/"
mkdir -p "$DATA_ROOT/workflows"
# v5.5 golden benchmarks
if [[ -d "$ROOT/benchmarks" ]]; then
  mkdir -p "$DATA_ROOT/benchmarks" "$LIB_DIR/../benchmarks"
  cp -a "$ROOT/benchmarks/." "$DATA_ROOT/benchmarks/"
  cp -a "$ROOT/benchmarks/." "$(dirname "$LIB_DIR")/benchmarks/" 2>/dev/null || true
fi

if [[ -d "$ROOT/workflows" ]]; then cp -a "$ROOT/workflows/." "$DATA_ROOT/workflows/"; fi
mkdir -p "$LIB_DIR/../workflows" 2>/dev/null || true
if [[ -d "$ROOT/workflows" ]]; then cp -a "$ROOT/workflows/." "$(dirname "$LIB_DIR")/workflows/" 2>/dev/null || cp -a "$ROOT/workflows/." "$DATA_ROOT/workflows/"; fi
if [[ -n "$PRESERVE_RUNNER" ]]; then
  cp -f "$PRESERVE_RUNNER" "$LIB_DIR/core/runner.sh"
  rm -f "$PRESERVE_RUNNER"
  echo "  restored: Codex runner.sh"
elif [[ "$SRC_HAS_CODEX" -eq 1 ]]; then
  echo "  runner: installed from source (Codex + context)"
fi
cp -f "$ROOT/VERSION" "$DATA_ROOT/VERSION"

install -m 0755 "$ROOT/bin/agentbox5" "$BIN_DIR/agentbox5"
install -m 0755 "$ROOT/bin/agentboxd" "$BIN_DIR/agentboxd"
install -m 0755 "$ROOT/bin/agent5-worker" "$BIN_DIR/agent5-worker"
ln -sfn "$BIN_DIR/agentbox5" "$BIN_DIR/agent5"
if [[ -f "$ROOT/bin/agentbox-deploy-guard" ]]; then
  install -m 0755 "$ROOT/bin/agentbox-deploy-guard" "$BIN_DIR/agentbox-deploy-guard"
fi

# Refresh configs
for f in policies.toml budgets.toml agentbox.toml providers.toml memory.toml agents.toml policies.ini recovery.ini backup.ini web.ini intelligence.toml tools.toml evaluation.toml ops_autopilot.toml; do
  if [[ -f "$ROOT/config/$f" ]]; then
    cp -f "$ROOT/config/$f" "$DATA_ROOT/config/$f"
    echo "  config: refreshed $f"
  fi
done
# Seed ~/.config/agentbox-v5/
for f in policies.ini recovery.ini backup.ini; do
  if [[ -f "$ROOT/config/$f" ]]; then
    cp -f "$ROOT/config/$f" "${HOME}/.config/agentbox-v5/$f"
    echo "  config: seeded ~/.config/agentbox-v5/$f"
  fi
done

export AGENTBOX_V5_HOME="$DATA_ROOT"
export AGENTBOX_V5_DB="$DATA_ROOT/data/agentbox.db"
export AGENTBOX_V5_LIB="$LIB_DIR"
export AGENTBOX_AUTO_APPROVE=1
python3 "$LIB_DIR/storage/db.py" init >/dev/null
echo "  db: $AGENTBOX_V5_DB (schema + legacy migrate)"
# Stable: versioned migrations (backup-before-migrate inside runner unless --no-backup)
if [[ -f "$LIB_DIR/ops/migrations.py" ]]; then
  python3 "$LIB_DIR/ops/migrations.py" run >/dev/null || python3 "$LIB_DIR/ops/migrations.py" run --no-backup
  echo "  migrations: stable framework applied"
fi

# Seed policies + budgets + agents
python3 "$LIB_DIR/agents/registry.py" seed >/dev/null 2>&1 || true
python3 "$LIB_DIR/policy/policies.py" seed >/dev/null 2>&1 || true
python3 "$LIB_DIR/policy/budgets.py" seed >/dev/null 2>&1 || true
echo "  agents/policies/budgets: seeded"

mkdir -p "$DATA_ROOT/config"
grep -q 'AGENTBOX_AUTO_APPROVE' "$DATA_ROOT/config/env.sh" 2>/dev/null || \
  echo 'export AGENTBOX_AUTO_APPROVE=1' >> "$DATA_ROOT/config/env.sh"

if [[ ":$PATH:" != *":$BIN_DIR:"* ]]; then
  echo "WARN: $BIN_DIR not on PATH — add: export PATH=\"\$HOME/.local/bin:\$PATH\""
fi
if [[ -e "$BIN_DIR/agentbox" ]]; then
  echo "  v4.9 launcher intact: $BIN_DIR/agentbox"
fi

echo
echo "Installed:"
echo "  $BIN_DIR/agentbox5"
echo "  $BIN_DIR/agent5 -> agentbox5"
echo "  $BIN_DIR/agentboxd"
echo "  $BIN_DIR/agent5-worker"
echo "  $LIB_DIR/"
echo "  $DATA_ROOT/"
echo "  backup: $BACKUP"
echo
echo "Next steps:"
echo "  agentbox5 version"
echo "  agent5 version"
echo "  agentbox5 selftest"
echo "  agentbox5 status"
echo "  agent5 policy list"
echo "  agent5 backup create"
echo "  agent5 doctor"
echo "  agent5 recover --dry-run"
echo "  agent5 selftest"
echo "  agent5 worker list"
echo "  agent5-worker enroll --url http://127.0.0.1:8787 --token ..."
