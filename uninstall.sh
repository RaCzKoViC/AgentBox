#!/usr/bin/env bash
# Uninstall AgentBox v5 only (leaves v4.9 alone)
set -euo pipefail

BIN_DIR="${HOME}/.local/bin"
LIB_DIR="${HOME}/.local/lib/agentbox5"
DATA_ROOT="${HOME}/.local/share/agentbox/v5"

echo "== AgentBox v5 uninstall =="

# Stop daemon if running
if [[ -x "$BIN_DIR/agentboxd" ]]; then
  "$BIN_DIR/agentboxd" stop 2>/dev/null || true
fi

rm -f "$BIN_DIR/agentbox5" "$BIN_DIR/agentboxd"
rm -rf "$LIB_DIR"

KEEP_DATA="${1:-}"
if [[ "$KEEP_DATA" == "--keep-data" ]]; then
  echo "Kept data: $DATA_ROOT"
else
  read -r -p "Remove data $DATA_ROOT ? [y/N] " ans || true
  if [[ "${ans:-}" =~ ^[Yy]$ ]]; then
    rm -rf "$DATA_ROOT"
    echo "Removed data"
  else
    echo "Kept data: $DATA_ROOT"
  fi
fi

# Never touch v4.9
if [[ -e "$BIN_DIR/agentbox" ]]; then
  echo "v4.9 launcher untouched: $BIN_DIR/agentbox"
fi
echo "Done."
