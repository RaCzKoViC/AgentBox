#!/usr/bin/env bash
# Install AgentBox v5.0-beta3 (Policy, Budget & Risk Engine)
set -Eeuo pipefail

command -v agentbox-deploy-guard >/dev/null 2>&1 || {
    echo "[ERR] Deployment guard missing."
    exit 1
}
agentbox-deploy-guard

ROOT="/workspace/agentbox-v5"
[[ -d "$ROOT" ]] || { echo "[ERR] AgentBox v5 root missing: $ROOT"; exit 1; }
cd "$ROOT"
exec "$ROOT/install.sh"
