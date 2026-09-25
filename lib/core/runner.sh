#!/usr/bin/env bash
# AgentBox v5 — real Codex runner (+ stub fallback)
# beta1: injects memory/context pack before each Codex stage
# Uses: codex exec --approve-for-me (write) / --sandbox read-only (review)
set -euo pipefail

# shellcheck source=state.sh
source "$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")" && pwd)/state.sh"

ab5_runner_backend() {
  local cfg="${AGENTBOX_V5_HOME}/config/agentbox.toml"
  local backend="codex"
  if [[ -f "$cfg" ]]; then
    backend="$("${AGENTBOX_V5_PYTHON:-python3}" - "$cfg" <<'PY'
import re, sys
from pathlib import Path
t = Path(sys.argv[1]).read_text()
m = re.search(r"\[runner\]([^\[]*)", t)
b = "codex"
if m:
    for line in m.group(1).splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("backend") or line.startswith("mode"):
            b = line.split("=", 1)[1].strip().strip("\"'")
            break
print(b)
PY
)"
  fi
  echo "${AGENTBOX_V5_RUNNER:-$backend}"
}

ab5_task_field() {
  local tid="$1" field="$2"
  "${AGENTBOX_V5_PYTHON:-python3}" - "$tid" "$field" <<'PY'
import sqlite3, sys, os
tid, field = sys.argv[1], sys.argv[2]
con = sqlite3.connect(os.environ["AGENTBOX_V5_DB"])
con.row_factory = sqlite3.Row
r = con.execute("select * from tasks where id=?", (tid,)).fetchone()
print("" if not r else ("" if r[field] is None else str(r[field])))
PY
}


ab5_build_memory_context() {
  # Compact context pack from memory layers + task + events (beta1)
  local tid="$1"
  local max_tokens="${2:-2000}"
  if [[ -f "${AGENTBOX_V5_LIB}/memory/context.py" ]]; then
    "${AGENTBOX_V5_PYTHON:-python3}" "${AGENTBOX_V5_LIB}/memory/context.py" build "$tid" --max-tokens "$max_tokens" --text-only 2>/dev/null \
      || true
  fi
}

ab5_prepare_worktree() {
  local tid="$1" project="$2"
  local root="${AGENTBOX_V5_HOME}/sandboxes/worktrees/${tid}"
  mkdir -p "$(dirname "$root")"
  if [[ -d "$root/.git" || -f "$root/.git" ]]; then
    echo "$root"
    return 0
  fi
  if git -C "$project" rev-parse --is-inside-work-tree >/dev/null 2>&1; then
    local proj_root branch
    proj_root="$(git -C "$project" rev-parse --show-toplevel)"
    branch="agentbox5/${tid}"
    git -C "$proj_root" worktree prune >/dev/null 2>&1 || true
    if git -C "$proj_root" show-ref --verify --quiet "refs/heads/$branch"; then
      git -C "$proj_root" worktree add "$root" "$branch" >/dev/null
    else
      git -C "$proj_root" worktree add -b "$branch" "$root" HEAD >/dev/null
    fi
  else
    mkdir -p "$root"
    cp -a "$project"/. "$root"/
    git -C "$root" init >/dev/null 2>&1 || true
  fi
  echo "$root"
}

ab5_codex_exec() {
  local sandbox_mode="$1" cwd="$2" prompt="$3" logfile="$4"
  mkdir -p "$(dirname "$logfile")"
  export PATH="${HOME}/.local/bin:/usr/local/bin:$PATH"
  if [[ "$sandbox_mode" == "read-only" ]]; then
    timeout 20m codex exec --sandbox read-only -C "$cwd" -o "${logfile}.last" "$prompt" \
      >"$logfile" 2>&1
  else
    timeout 25m codex exec --approve-for-me -C "$cwd" -o "${logfile}.last" "$prompt" \
      >"$logfile" 2>&1
  fi
}

ab5_run_codex() {
  local task_id="$1"
  local worker_id="${2:-agentboxd}"
  ab5_ensure_env
  export AGENTBOX_AUTO_APPROVE="${AGENTBOX_AUTO_APPROVE:-1}"
  export PATH="${HOME}/.local/bin:$PATH"

  if ! command -v codex >/dev/null 2>&1; then
    echo "codex not found" >&2
    return 1
  fi

  local project title description
  project="$(ab5_task_field "$task_id" project_id)"
  title="$(ab5_task_field "$task_id" title)"
  description="$(ab5_task_field "$task_id" description)"
  [[ -n "$project" && -d "$project" ]] || { echo "bad project=$project" >&2; return 1; }

  if [[ -f "${AGENTBOX_V5_LIB}/policy/approvals.py" ]]; then
    "${AGENTBOX_V5_PYTHON:-python3}" "${AGENTBOX_V5_LIB}/policy/approvals.py" ensure-gate "$task_id" >/dev/null 2>&1 || true
  fi

  local worktree
  worktree="$(ab5_prepare_worktree "$task_id" "$project")"

  local run_json run_id outdir
  run_json="$(ab5_db create-run "$task_id" --worker "$worker_id")"
  run_id="$("${AGENTBOX_V5_PYTHON:-python3}" -c 'import json,sys; print(json.load(sys.stdin)["id"])' <<<"$run_json")"
  outdir="${AGENTBOX_V5_HOME}/data/artifacts/${task_id}/${run_id}"
  mkdir -p "$outdir"

  ab5_db emit --kind "sandbox.ready" --message "worktree=$worktree" --task "$task_id" --run "$run_id" >/dev/null || true
  ab5_db set-status "$task_id" running >/dev/null 2>&1 || true

  # Short autonomous pipeline: coder + tester + reviewer (skip planner/architect for speed)
  local stages=(coder tester reviewer)
  local stage rc=0 context="" prompt stage_title mem_ctx=""

  for stage in "${stages[@]}"; do
    ab5_db emit --kind "stage.started" --message "$stage" --task "$task_id" --run "$run_id" >/dev/null || true
    "${AGENTBOX_V5_PYTHON:-python3}" - "$task_id" "$stage" <<'PY' 2>/dev/null || true
import os, sqlite3, sys
tid, stage = sys.argv[1], sys.argv[2]
con = sqlite3.connect(os.environ["AGENTBOX_V5_DB"])
con.execute("UPDATE tasks SET current_stage=?, updated_at=datetime('now') WHERE id=?", (stage, tid))
con.commit()
PY

    stage_title="$(echo "$stage" | awk '{print toupper(substr($0,1,1)) substr($0,2)}')"
    # beta1: inject compact memory/context pack before each stage
    mem_ctx="$(ab5_build_memory_context "$task_id" 2000)"
    prompt="Act as ${stage_title} for AgentBox v5 autonomous run.
PROJECT ORIGINAL: $project
ISOLATED WORKTREE (edit here only): $worktree
TASK: $title
DESCRIPTION: $description

MEMORY / CONTEXT PACK:
$mem_ctx

PREVIOUS STAGE CONTEXT (truncated):
$context

Rules:
- Edit files only inside the worktree.
- Keep changes minimal.
- Tester: run the project's tests and summarize.
- Reviewer: end with VERDICT: PASS or VERDICT: FAIL.
"

    local smode="write"
    [[ "$stage" == "reviewer" ]] && smode="read-only"

    set +e
    if [[ "$smode" == "read-only" ]]; then
      ab5_codex_exec read-only "$worktree" "$prompt" "$outdir/${stage}.txt"
    else
      ab5_codex_exec write "$worktree" "$prompt" "$outdir/${stage}.txt"
    fi
    rc=$?
    set -e

    ab5_db emit --kind "stage.finished" --message "$stage rc=$rc" --task "$task_id" --run "$run_id" >/dev/null || true
    context+=$'\n'"===== $stage (rc=$rc) ====="$'\n'
    context+="$(tail -c 4000 "$outdir/${stage}.txt" 2>/dev/null || true)"

    if [[ $rc -ne 0 && "$stage" == "coder" ]]; then
      ab5_db finish-run "$run_id" --status failed --exit-code "$rc" --error "coder failed" >/dev/null || true
      ab5_db set-status "$task_id" failed >/dev/null
      return "$rc"
    fi
  done

  # Optional auto-merge when autonomy.auto_merge=true
  if "${AGENTBOX_V5_PYTHON:-python3}" - <<PY 2>/dev/null
from pathlib import Path
import re, sys
t = Path("${AGENTBOX_V5_HOME}/config/agentbox.toml").read_text()
m = re.search(r"\[autonomy\]([^\[]*)", t)
sys.exit(0 if m and "auto_merge" in m.group(1) and "true" in m.group(1) else 1)
PY
  then
    if git -C "$project" rev-parse --is-inside-work-tree >/dev/null 2>&1; then
      local branch
      branch="$(git -C "$worktree" branch --show-current 2>/dev/null || true)"
      if [[ -n "$branch" && "$branch" != "main" && "$branch" != "master" ]]; then
        if [[ -n "$(git -C "$worktree" status --porcelain 2>/dev/null)" ]]; then
          git -C "$worktree" add -A
          git -C "$worktree" -c user.email=agentbox5@local -c user.name=AgentBox5 \
            commit -m "agentbox5: $title" -m "task=$task_id" >/dev/null 2>&1 || true
        fi
        if [[ -z "$(git -C "$project" status --porcelain 2>/dev/null)" ]]; then
          if git -C "$project" merge --no-ff "$branch" -m "Merge agentbox5 task $task_id: $title" >/dev/null 2>&1; then
            ab5_db emit --kind "merge.done" --message "merged $branch" --task "$task_id" --run "$run_id" >/dev/null || true
          else
            ab5_db emit --kind "merge.failed" --message "merge conflict" --task "$task_id" --run "$run_id" >/dev/null || true
          fi
        fi
      fi
    fi
  fi

  ab5_db emit --kind "runner.codex" --message "Codex pipeline finished" --task "$task_id" --run "$run_id" >/dev/null || true
  ab5_db finish-run "$run_id" --status completed --exit-code 0 >/dev/null
  ab5_db set-status "$task_id" completed >/dev/null
  return 0
}

ab5_run_stub() {
  local task_id="$1"
  local worker_id="${2:-agentboxd}"
  ab5_ensure_env
  local run_json run_id
  run_json="$(ab5_db create-run "$task_id" --worker "$worker_id")"
  run_id="$("${AGENTBOX_V5_PYTHON:-python3}" -c 'import json,sys; print(json.load(sys.stdin)["id"])' <<<"$run_json")"
  ab5_db emit --kind "plan.stub" --message "stub fallback" --task "$task_id" --run "$run_id" >/dev/null || true
  sleep 1
  ab5_db emit --kind "runner.stub" --message "Stub runner completed" --task "$task_id" --run "$run_id" >/dev/null || true
  ab5_db finish-run "$run_id" --status completed --exit-code 0
}

ab5_run_task() {
  local task_id="$1"
  local worker_id="${2:-agentboxd}"
  local backend
  backend="$(ab5_runner_backend)"
  case "$backend" in
    stub) ab5_run_stub "$task_id" "$worker_id" ;;
    codex|*) ab5_run_codex "$task_id" "$worker_id" ;;
  esac
}
