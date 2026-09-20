#!/usr/bin/env bash
# AgentBox v5 — logging helpers
set -euo pipefail

ab5_log() {
  local level="$1"; shift
  local msg="$*"
  local ts
  ts="$(date -u '+%Y-%m-%dT%H:%M:%SZ')"
  local root="${AGENTBOX_V5_HOME:-$HOME/.local/share/agentbox/v5}"
  mkdir -p "${root}/logs"
  echo "[$ts] [$level] $msg" | tee -a "${root}/logs/agentbox5.log" >&2
}

ab5_daemon_log() {
  local msg="$*"
  local ts
  ts="$(date -u '+%Y-%m-%dT%H:%M:%SZ')"
  local root="${AGENTBOX_V5_HOME:-$HOME/.local/share/agentbox/v5}"
  mkdir -p "${root}/logs"
  echo "[$ts] $msg" >> "${root}/logs/daemon.log"
}
