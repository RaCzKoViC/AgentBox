#!/usr/bin/env bash
# Install AgentBox v5.0-rc1 (REST API + WebSocket + Web Dashboard)
set -euo pipefail

command -v agentbox-deploy-guard >/dev/null 2>&1 || { echo "[ERR] guard missing"; exit 1; }
agentbox-deploy-guard

ROOT="$(cd "$(dirname "$0")" && pwd)"
[[ "$(pwd -P)" == "$ROOT"* ]] || cd "$ROOT"

VER="$(tr -d '[:space:]' < "$ROOT/VERSION")"
BIN_DIR="${HOME}/.local/bin"
LIB_DIR="${HOME}/.local/lib/agentbox5"
DATA_ROOT="${HOME}/.local/share/agentbox/v5"
VENV="${DATA_ROOT}/venv"

echo "== AgentBox ${VER} install (rc1) =="

STAMP="$(date +%Y%m%d-%H%M%S)"
BACKUP="${DATA_ROOT}/backups/rc1-install-${STAMP}"
mkdir -p "$BACKUP"
cp -a "$ROOT" "$BACKUP/project" 2>/dev/null || true
cp -a "${DATA_ROOT}/data/agentbox.db" "$BACKUP/agentbox.db" 2>/dev/null || true
cp -a "${HOME}/.config/agentbox-v5" "$BACKUP/config" 2>/dev/null || true
echo "  backup: $BACKUP"

mkdir -p "$BIN_DIR" "$LIB_DIR" \
  "$DATA_ROOT"/{config,data,runtime/{locks,pids/workers,queue,sockets},logs,backups} \
  "${HOME}/.config/agentbox-v5/secrets"

# Preserve Codex runner if source is stub
PRESERVE_RUNNER=""
SRC_HAS_CODEX=0
INST_HAS_CODEX=0
if grep -qE 'ab5_run_codex|codex exec' "$ROOT/lib/core/runner.sh" 2>/dev/null; then SRC_HAS_CODEX=1; fi
if [[ -f "$LIB_DIR/core/runner.sh" ]] && grep -qE 'ab5_run_codex|codex exec' "$LIB_DIR/core/runner.sh" 2>/dev/null; then INST_HAS_CODEX=1; fi
if [[ "$INST_HAS_CODEX" -eq 1 && "$SRC_HAS_CODEX" -eq 0 ]]; then
  PRESERVE_RUNNER="$(mktemp)"
  cp -f "$LIB_DIR/core/runner.sh" "$PRESERVE_RUNNER"
  echo "  preserve: Codex runner.sh"
fi

rm -rf "${LIB_DIR:?}/"*
cp -a "$ROOT/lib/." "$LIB_DIR/"
# also copy web assets next to lib if present
if [[ -d "$ROOT/lib/web" ]]; then
  mkdir -p "$LIB_DIR/web"
  cp -a "$ROOT/lib/web/." "$LIB_DIR/web/"
fi
if [[ -n "$PRESERVE_RUNNER" ]]; then
  cp -f "$PRESERVE_RUNNER" "$LIB_DIR/core/runner.sh"
  rm -f "$PRESERVE_RUNNER"
  echo "  restored: Codex runner.sh"
fi

cp -f "$ROOT/VERSION" "$DATA_ROOT/VERSION"
install -m 0755 "$ROOT/bin/agentbox5" "$BIN_DIR/agentbox5"
install -m 0755 "$ROOT/bin/agentboxd" "$BIN_DIR/agentboxd"
ln -sfn "$BIN_DIR/agentbox5" "$BIN_DIR/agent5"
if [[ -f "$ROOT/bin/agentbox-deploy-guard" ]]; then
  install -m 0755 "$ROOT/bin/agentbox-deploy-guard" "$BIN_DIR/agentbox-deploy-guard"
fi

# configs
for f in policies.toml budgets.toml agentbox.toml providers.toml memory.toml agents.toml policies.ini web.ini; do
  if [[ -f "$ROOT/config/$f" ]]; then
    cp -f "$ROOT/config/$f" "$DATA_ROOT/config/$f"
    echo "  config: refreshed $f"
  fi
done
if [[ -f "$ROOT/config/web.ini" ]]; then
  cp -f "$ROOT/config/web.ini" "${HOME}/.config/agentbox-v5/web.ini"
fi
if [[ -f "$ROOT/config/policies.ini" ]]; then
  cp -f "$ROOT/config/policies.ini" "${HOME}/.config/agentbox-v5/policies.ini"
fi

# venv + deps
if [[ ! -x "$VENV/bin/python" ]]; then
  python3 -m venv "$VENV"
fi
"$VENV/bin/pip" install -q --upgrade pip
"$VENV/bin/pip" install -q fastapi 'uvicorn[standard]' pydantic python-multipart jinja2 psutil websockets itsdangerous
echo "  venv: $VENV"

export AGENTBOX_V5_HOME="$DATA_ROOT"
export AGENTBOX_V5_DB="$DATA_ROOT/data/agentbox.db"
export AGENTBOX_V5_LIB="$LIB_DIR"
export AGENTBOX_AUTO_APPROVE="${AGENTBOX_AUTO_APPROVE:-1}"
python3 "$LIB_DIR/storage/db.py" init >/dev/null
echo "  db: $AGENTBOX_V5_DB (rc1 web tables)"

# seed
python3 "$LIB_DIR/agents/registry.py" seed >/dev/null 2>&1 || true
python3 "$LIB_DIR/policy/policies.py" seed >/dev/null 2>&1 || true
python3 "$LIB_DIR/policy/budgets.py" seed >/dev/null 2>&1 || true

# admin token
python3 - <<'PY'
import sys
sys.path.insert(0, __import__("os").environ["AGENTBOX_V5_LIB"])
from api.auth import ensure_admin_token
tok = ensure_admin_token()
print("  admin token: ~/.config/agentbox-v5/secrets/admin.token (chmod 600)")
PY

echo
echo "Installed AgentBox ${VER}"
echo "  $BIN_DIR/agent5 -> agentbox5"
echo "  backup: $BACKUP"
echo "Next: agent5 web start && agent5 selftest"
