#!/usr/bin/env bash
# Upgrade/install AgentBox v5.0-beta2
set -euo pipefail
command -v agentbox-deploy-guard >/dev/null 2>&1 || { echo "[ERR] guard missing"; exit 1; }
agentbox-deploy-guard
ROOT="/workspace/agentbox-v5"
[[ "$(pwd -P)" == "$ROOT"* ]] || cd "$ROOT"
exec "$ROOT/install.sh"
