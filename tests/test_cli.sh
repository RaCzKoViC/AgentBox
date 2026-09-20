#!/usr/bin/env bash
# CLI smoke test beta1 Memory/Context/Agent (isolated DATA root, autonomous)
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"; agentboxd stop >/dev/null 2>&1 || true' EXIT

export AGENTBOX_V5_HOME="$TMP/v5"
export AGENTBOX_V5_DB="$AGENTBOX_V5_HOME/data/agentbox.db"
export AGENTBOX_V5_LIB="$ROOT/lib"
export AGENTBOX_AUTO_APPROVE=1
export PATH="$ROOT/bin:$PATH"

mkdir -p "$AGENTBOX_V5_HOME"/{data,logs,runtime/pids/workers,config}
cp "$ROOT/config/"*.toml "$AGENTBOX_V5_HOME/config/"

echo "== version =="
out="$(agentbox5 version)"
echo "$out"
[[ "$out" == *beta1* ]] || { echo "FAIL version: $out"; exit 1; }

echo "== init-db =="
agentbox5 init-db

echo "== policy force_push deny / merge allow =="
dec="$(python3 -c 'import json,sys; print(json.load(sys.stdin)["decision"])' <<<"$(agentbox5 policy check git.force_push)")"
[[ "$dec" == "deny" ]] || { echo "FAIL force_push=$dec"; exit 1; }
dec="$(python3 -c 'import json,sys; print(json.load(sys.stdin)["decision"])' <<<"$(agentbox5 policy check git.merge)")"
[[ "$dec" == "allow" ]] || { echo "FAIL merge=$dec"; exit 1; }

echo "== budget pause =="
bj="$(agentbox5 task create --project /tmp/cli-demo --title budget --budget-tokens 1)"
bid="$(python3 -c 'import json,sys; print(json.load(sys.stdin)["id"])' <<<"$bj")"
agentbox5 queue add "$bid" >/dev/null
# shellcheck disable=SC1091
source "$ROOT/lib/core/runner.sh"
ab5_run_stub "$bid" "t" >/dev/null || true
st="$(python3 -c 'import json,sys; print(json.load(sys.stdin)["status"])' <<<"$(agentbox5 task show "$bid")")"
[[ "$st" == "paused_budget" ]] || { echo "FAIL status=$st"; exit 1; }

echo "== daemon dep smoke =="
aj="$(agentbox5 task create --project /tmp/cli-demo --title A --priority 10)"
bj2="$(agentbox5 task create --project /tmp/cli-demo --title B --priority 10)"
cj="$(agentbox5 task create --project /tmp/cli-demo --title C --priority 1)"
aid="$(python3 -c 'import json,sys; print(json.load(sys.stdin)["id"])' <<<"$aj")"
bid2="$(python3 -c 'import json,sys; print(json.load(sys.stdin)["id"])' <<<"$bj2")"
cid="$(python3 -c 'import json,sys; print(json.load(sys.stdin)["id"])' <<<"$cj")"
agentbox5 task depend "$cid" --on "$aid" --on "$bid2" >/dev/null
agentbox5 queue add "$aid" >/dev/null
agentbox5 queue add "$bid2" >/dev/null
agentbox5 queue add "$cid" >/dev/null
agentboxd start
for i in $(seq 1 30); do
  sa="$(python3 -c 'import json,sys; print(json.load(sys.stdin)["status"])' <<<"$(agentbox5 task show "$aid")")"
  sb="$(python3 -c 'import json,sys; print(json.load(sys.stdin)["status"])' <<<"$(agentbox5 task show "$bid2")")"
  sc="$(python3 -c 'import json,sys; print(json.load(sys.stdin)["status"])' <<<"$(agentbox5 task show "$cid")")"
  [[ "$sa" == "completed" && "$sb" == "completed" && "$sc" == "completed" ]] && break
  sleep 0.5
done
agentboxd stop || true
sa="$(python3 -c 'import json,sys; print(json.load(sys.stdin)["status"])' <<<"$(agentbox5 task show "$aid")")"
sb="$(python3 -c 'import json,sys; print(json.load(sys.stdin)["status"])' <<<"$(agentbox5 task show "$bid2")")"
sc="$(python3 -c 'import json,sys; print(json.load(sys.stdin)["status"])' <<<"$(agentbox5 task show "$cid")")"
[[ "$sa" == "completed" && "$sb" == "completed" && "$sc" == "completed" ]] || { echo "FAIL $sa $sb $sc"; exit 1; }

echo "OK test_cli.sh"
