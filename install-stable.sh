#!/usr/bin/env bash
# Thin wrapper — AgentBox v5.0.0 Stable
set -euo pipefail
cd "$(dirname "$0")"
exec ./install.sh "$@"
