#!/usr/bin/env python3
"""Crash recovery — orphan PIDs, stuck tasks, orphan worktrees."""
from __future__ import annotations

import json
import os
import shutil
import sys
from pathlib import Path
from typing import Any, Optional

_HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(_HERE.parent))

from ops.paths import (  # noqa: E402
    data_home,
    load_ini,
    locks_dir,
    pid_alive,
    pids_dir,
)
from storage import db as dbmod  # noqa: E402

# Ensure interrupted status is allowed
if hasattr(dbmod, "ALLOWED_STATUSES"):
    # frozenset — rebuild if needed at apply time via raw SQL
    pass


def _cfg() -> dict[str, Any]:
    cp = load_ini("recovery.ini")
    return {
        "auto_recover_tasks": cp.getboolean("recovery", "auto_recover_tasks", fallback=True),
        "auto_recover_runs": cp.getboolean("recovery", "auto_recover_runs", fallback=True),
        "auto_cleanup_stale_pids": cp.getboolean("recovery", "auto_cleanup_stale_pids", fallback=True),
        "auto_cleanup_orphan_worktrees": cp.getboolean(
            "recovery", "auto_cleanup_orphan_worktrees", fallback=False
        ),
        "max_recovery_attempts": cp.getint("recovery", "max_recovery_attempts", fallback=2),
    }


def scan_stale_pids() -> list[dict[str, Any]]:
    orphans = []
    pd = pids_dir()
    for f in list(pd.glob("*.pid")) + list((pd / "workers").glob("*.pid") if (pd / "workers").is_dir() else []):
        try:
            pid = int(f.read_text(encoding="utf-8").strip() or "0")
        except ValueError:
            pid = 0
        alive = pid_alive(pid) if pid else False
        if not alive:
            orphans.append({
                "type": "stale_pid",
                "path": str(f),
                "pid": pid,
                "alive": False,
                "action": "remove_pid_file",
            })
    return orphans


def scan_stuck_tasks() -> list[dict[str, Any]]:
    out = []
    with dbmod.connect() as conn:
        rows = conn.execute(
            "SELECT id, status, title FROM tasks WHERE status IN ('running','recovering')"
        ).fetchall()
        for r in rows:
            tid = r["id"]
            # check if any live worker claims it
            worker_pid_files = list((pids_dir() / "workers").glob(f"*{tid}*.pid")) if (pids_dir() / "workers").is_dir() else []
            live = any(
                pid_alive(int(p.read_text().strip() or "0"))
                for p in worker_pid_files
                if p.is_file()
            )
            if not live:
                out.append({
                    "type": "stuck_task",
                    "task_id": tid,
                    "status": r["status"],
                    "title": r["title"],
                    "action": "mark_interrupted",
                })
        run_rows = conn.execute(
            "SELECT id, task_id, status, worker_id FROM runs WHERE status='running'"
        ).fetchall()
        for r in run_rows:
            out.append({
                "type": "stuck_run",
                "run_id": r["id"],
                "task_id": r["task_id"],
                "worker_id": r["worker_id"],
                "action": "mark_interrupted",
            })
        # handoffs
        try:
            hf = conn.execute(
                "SELECT id, task_id, status FROM agent_handoffs WHERE status='running'"
            ).fetchall()
            for r in hf:
                out.append({
                    "type": "stuck_handoff",
                    "handoff_id": r["id"],
                    "task_id": r["task_id"],
                    "action": "mark_interrupted",
                })
        except Exception:
            pass
    return out


def scan_orphan_worktrees() -> list[dict[str, Any]]:
    out = []
    tasks_root = data_home() / "data" / "tasks"
    if not tasks_root.is_dir():
        return out
    # active task ids
    with dbmod.connect() as conn:
        active = {
            r[0]
            for r in conn.execute(
                "SELECT id FROM tasks WHERE status IN ('running','queued','scheduled','paused','awaiting_approval','blocked','created','planned','ready')"
            ).fetchall()
        }
    for d in tasks_root.iterdir():
        if not d.is_dir():
            continue
        wt = d / "worktree"
        if not wt.exists():
            continue
        tid = d.name
        category = "active" if tid in active else "orphaned"
        has_changes = False
        if (wt / ".git").exists() or (d / "worktree").is_dir():
            # cheap dirty check
            try:
                import subprocess
                r = subprocess.run(
                    ["git", "-C", str(wt), "status", "--porcelain"],
                    capture_output=True, text=True, timeout=5,
                )
                has_changes = bool(r.stdout.strip())
            except Exception:
                pass
        if category == "orphaned":
            safe = not has_changes
            out.append({
                "type": "orphan_worktree",
                "task_id": tid,
                "path": str(wt),
                "category": "safe_to_remove" if safe else "manual_review",
                "has_uncommitted_changes": has_changes,
                "action": "remove" if safe else "manual_review",
            })
    return out


def scan_stale_locks() -> list[dict[str, Any]]:
    out = []
    for f in locks_dir().glob("*.lock"):
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
            pid = int(data.get("pid") or 0)
        except Exception:
            pid = 0
            data = {}
        if not pid_alive(pid):
            out.append({
                "type": "stale_lock",
                "path": str(f),
                "pid": pid,
                "action": "remove_lock",
                "meta": data,
            })
    return out


def scan() -> dict[str, Any]:
    findings = (
        scan_stale_pids()
        + scan_stuck_tasks()
        + scan_orphan_worktrees()
        + scan_stale_locks()
    )
    return {
        "ok": True,
        "count": len(findings),
        "findings": findings,
        "config": _cfg(),
    }


def apply(dry_run: bool = False) -> dict[str, Any]:
    cfg = _cfg()
    report = scan()
    actions = []
    for item in report["findings"]:
        t = item["type"]
        act = item.get("action")
        if dry_run:
            actions.append({"dry_run": True, **item})
            continue
        if t == "stale_pid" and cfg["auto_cleanup_stale_pids"]:
            Path(item["path"]).unlink(missing_ok=True)
            actions.append({"applied": "removed_pid", **item})
        elif t == "stale_lock" and cfg["auto_cleanup_stale_pids"]:
            Path(item["path"]).unlink(missing_ok=True)
            actions.append({"applied": "removed_lock", **item})
        elif t == "stuck_task" and cfg["auto_recover_tasks"]:
            with dbmod.connect() as conn:
                conn.execute(
                    "UPDATE tasks SET status='interrupted', updated_at=? WHERE id=?",
                    (dbmod.utc_now(), item["task_id"]),
                )
                conn.commit()
            try:
                dbmod.emit_event(
                    kind="recovery.task_interrupted",
                    task_id=item["task_id"],
                    message="marked interrupted by recovery",
                )
            except Exception:
                pass
            actions.append({"applied": "mark_interrupted", **item})
        elif t == "stuck_run" and cfg["auto_recover_runs"]:
            with dbmod.connect() as conn:
                conn.execute(
                    "UPDATE runs SET status='interrupted', finished_at=? WHERE id=?",
                    (dbmod.utc_now(), item["run_id"]),
                )
                conn.commit()
            actions.append({"applied": "mark_run_interrupted", **item})
        elif t == "stuck_handoff":
            with dbmod.connect() as conn:
                conn.execute(
                    "UPDATE agent_handoffs SET status='interrupted' WHERE id=?",
                    (item["handoff_id"],),
                )
                conn.commit()
            actions.append({"applied": "mark_handoff_interrupted", **item})
        elif t == "orphan_worktree":
            if cfg["auto_cleanup_orphan_worktrees"] and item.get("category") == "safe_to_remove":
                shutil.rmtree(item["path"], ignore_errors=True)
                actions.append({"applied": "removed_worktree", **item})
            else:
                actions.append({"skipped": "orphan_worktree_cleanup_disabled", **item})
        else:
            actions.append({"skipped": "policy", **item})
    return {
        "ok": True,
        "dry_run": dry_run,
        "actions": actions,
        "scanned": report["count"],
    }


def status() -> dict[str, Any]:
    s = scan()
    return {
        "recoverable": s["count"],
        "by_type": {
            t: sum(1 for f in s["findings"] if f["type"] == t)
            for t in ("stale_pid", "stuck_task", "stuck_run", "stuck_handoff", "orphan_worktree", "stale_lock")
        },
        "config": s["config"],
    }


def main(argv: Optional[list[str]] = None) -> int:
    argv = list(argv or sys.argv[1:])
    cmd = argv[0] if argv else "scan"
    dry = "--dry-run" in argv
    if cmd == "scan":
        print(json.dumps(scan(), indent=2))
    elif cmd == "status":
        print(json.dumps(status(), indent=2))
    elif cmd == "apply":
        print(json.dumps(apply(dry_run=dry), indent=2))
    elif cmd == "recover":
        # alias used by CLI: recover [--dry-run]
        print(json.dumps(apply(dry_run=dry or True) if dry else apply(dry_run=False), indent=2))
    else:
        print("usage: recovery.py scan|status|apply [--dry-run]", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
