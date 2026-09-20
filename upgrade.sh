#!/usr/bin/env bash
# Upgrade to AgentBox v5.0-beta3
set -Eeuo pipefail
command -v agentbox-deploy-guard >/dev/null 2>&1 || { echo "[ERR] guard missing"; exit 1; }
agentbox-deploy-guard
ROOT="/workspace/agentbox-v5"
cd "$ROOT"
agent5 daemon stop 2>/dev/null || true
exec "$ROOT/install.sh"
