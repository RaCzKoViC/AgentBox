#!/usr/bin/env python3
"""AgentBox v5 — sandbox manager (worktree|docker|direct) alpha3."""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any, Optional

_HERE = Path(__file__).resolve().parent
for _c in (_HERE.parent / "storage", _HERE.parent.parent / "lib" / "storage"):
    if (_c / "db.py").is_file():
        sys.path.insert(0, str(_c))
        break

import db  # noqa: E402

MODES = frozenset({"worktree", "docker", "direct"})


def data_root() -> Path:
    return Path(os.environ.get("AGENTBOX_V5_HOME", Path.home() / ".local/share/agentbox/v5"))


def sandbox_base(task_id: str) -> Path:
    return data_root() / "data" / "tasks" / task_id


def _meta(task: dict) -> dict:
    raw = task.get("meta_json") or "{}"
    if isinstance(raw, dict):
        return dict(raw)
    try:
        return json.loads(raw)
    except Exception:
        return {}


def _save_meta(task_id: str, meta: dict, sandbox_mode: Optional[str] = None,
               db_path: Optional[str] = None) -> dict:
    now = db.utc_now()
    with db.connect(db_path) as conn:
        if sandbox_mode:
            conn.execute(
                "UPDATE tasks SET meta_json = ?, sandbox_mode = ?, updated_at = ? WHERE id = ?",
                (json.dumps(meta), sandbox_mode, now, task_id),
            )
        else:
            conn.execute(
                "UPDATE tasks SET meta_json = ?, updated_at = ? WHERE id = ?",
                (json.dumps(meta), now, task_id),
            )
        conn.commit()
    return db.get_task(task_id, db_path)


def _is_git_repo(path: Path) -> bool:
    return (path / ".git").exists() or subprocess.run(
        ["git", "-C", str(path), "rev-parse", "--is-inside-work-tree"],
        capture_output=True, text=True,
    ).returncode == 0


def _docker_available() -> bool:
    try:
        r = subprocess.run(["docker", "info"], capture_output=True, text=True, timeout=5)
        return r.returncode == 0
    except Exception:
        return False


def create_sandbox(
    task_id: str,
    mode: Optional[str] = None,
    db_path: Optional[str] = None,
) -> dict:
    task = db.get_task(task_id, db_path)
    if not task:
        raise KeyError(f"task not found: {task_id}")
    mode = (mode or task.get("sandbox_mode") or "worktree").strip().lower()
    if mode not in MODES:
        raise ValueError(f"invalid sandbox mode: {mode}; allowed: {sorted(MODES)}")

    project = Path(task["project_id"]).expanduser().resolve()
    base = sandbox_base(task_id)
    base.mkdir(parents=True, exist_ok=True)
    info: dict[str, Any] = {
        "mode": mode,
        "task_id": task_id,
        "project_id": str(project),
        "base": str(base),
        "path": None,
        "status": "created",
        "warnings": [],
    }

    if mode == "direct":
        info["path"] = str(project)
        info["note"] = "direct mode — working in project path (no isolation)"
    elif mode == "worktree":
        wt = base / "worktree"
        if wt.exists():
            info["path"] = str(wt)
            info["note"] = "worktree already exists"
        elif project.is_dir() and _is_git_repo(project):
            branch = f"agentbox/{task_id}"
            # Prefer existing HEAD
            r = subprocess.run(
                ["git", "-C", str(project), "worktree", "add", "-b", branch, str(wt)],
                capture_output=True, text=True,
            )
            if r.returncode != 0:
                # Branch may exist — try without -b
                r2 = subprocess.run(
                    ["git", "-C", str(project), "worktree", "add", str(wt), branch],
                    capture_output=True, text=True,
                )
                if r2.returncode != 0:
                    # Fallback: worktree from HEAD detached
                    r3 = subprocess.run(
                        ["git", "-C", str(project), "worktree", "add", "--detach", str(wt)],
                        capture_output=True, text=True,
                    )
                    if r3.returncode != 0:
                        raise RuntimeError(
                            f"git worktree failed: {r.stderr or r2.stderr or r3.stderr}"
                        )
                    info["branch"] = None
                    info["detached"] = True
                else:
                    info["branch"] = branch
            else:
                info["branch"] = branch
            info["path"] = str(wt)
        else:
            # Non-git: copy or symlink project into worktree dir
            wt.mkdir(parents=True, exist_ok=True)
            info["path"] = str(wt)
            info["warnings"].append(
                "WARN: project is not a git repo — created empty worktree dir (no git worktree)"
            )
            if project.is_dir():
                # lightweight: copy tree excluding .git if any
                for item in project.iterdir():
                    dest = wt / item.name
                    if item.name == ".git":
                        continue
                    if not dest.exists():
                        if item.is_dir():
                            shutil.copytree(item, dest, dirs_exist_ok=True)
                        else:
                            shutil.copy2(item, dest)
                info["note"] = "copied project files into sandbox (non-git)"
    elif mode == "docker":
        if not _docker_available():
            info["status"] = "skipped"
            info["warnings"].append(
                "WARN: docker daemon not available — sandbox skipped"
            )
            info["path"] = None
        else:
            name = f"agentbox-{task_id}"
            # Record intent; alpha3 does not start a long-lived container by default
            info["container_name"] = name
            info["path"] = str(project)
            info["note"] = "docker mode recorded (daemon available); no container started in alpha3 stub"
            info["docker_available"] = True

    meta = _meta(task)
    meta["sandbox"] = info
    _save_meta(task_id, meta, sandbox_mode=mode, db_path=db_path)
    db.emit_event(
        kind="sandbox.created",
        message=f"sandbox mode={mode} status={info['status']}",
        task_id=task_id,
        payload=info,
        db_path=db_path,
    )
    return info


def inspect_sandbox(task_id: str, db_path: Optional[str] = None) -> dict:
    task = db.get_task(task_id, db_path)
    if not task:
        raise KeyError(f"task not found: {task_id}")
    meta = _meta(task)
    info = meta.get("sandbox") or {}
    base = sandbox_base(task_id)
    path = Path(info["path"]) if info.get("path") else None
    return {
        "task_id": task_id,
        "sandbox_mode": task.get("sandbox_mode"),
        "recorded": info,
        "base_exists": base.is_dir(),
        "path_exists": bool(path and path.exists()),
        "base": str(base),
    }


def destroy_sandbox(task_id: str, db_path: Optional[str] = None) -> dict:
    task = db.get_task(task_id, db_path)
    if not task:
        raise KeyError(f"task not found: {task_id}")
    meta = _meta(task)
    info = meta.get("sandbox") or {}
    mode = info.get("mode") or task.get("sandbox_mode") or "worktree"
    project = Path(task["project_id"]).expanduser().resolve()
    base = sandbox_base(task_id)
    removed = []

    if mode == "worktree":
        wt = base / "worktree"
        if project.is_dir() and _is_git_repo(project) and wt.exists():
            subprocess.run(
                ["git", "-C", str(project), "worktree", "remove", "--force", str(wt)],
                capture_output=True, text=True,
            )
            removed.append(str(wt))
            # prune
            subprocess.run(
                ["git", "-C", str(project), "worktree", "prune"],
                capture_output=True, text=True,
            )
        elif wt.exists():
            shutil.rmtree(wt, ignore_errors=True)
            removed.append(str(wt))
    elif mode == "docker":
        name = info.get("container_name") or f"agentbox-{task_id}"
        if _docker_available():
            subprocess.run(["docker", "rm", "-f", name], capture_output=True, text=True)
            removed.append(name)
        else:
            info.setdefault("warnings", []).append("WARN: docker not available on destroy")

    if base.exists():
        shutil.rmtree(base, ignore_errors=True)
        removed.append(str(base))

    meta["sandbox"] = {"mode": mode, "status": "destroyed", "removed": removed}
    _save_meta(task_id, meta, db_path=db_path)
    db.emit_event(
        kind="sandbox.destroyed",
        message=f"sandbox destroyed mode={mode}",
        task_id=task_id,
        payload={"removed": removed, "mode": mode},
        db_path=db_path,
    )
    return {"task_id": task_id, "mode": mode, "removed": removed, "status": "destroyed"}


def _print(obj: Any) -> None:
    print(json.dumps(obj, indent=2, ensure_ascii=False, default=str))


def main(argv: Optional[list[str]] = None) -> int:
    argv = list(argv if argv is not None else sys.argv[1:])
    db_path = os.environ.get("AGENTBOX_V5_DB")
    if not argv:
        print("usage: manager.py create TASK [--mode worktree|docker|direct]|inspect TASK|destroy TASK",
              file=sys.stderr)
        return 2
    cmd = argv[0]
    try:
        if cmd == "create":
            if len(argv) < 2:
                print("create TASK [--mode M]", file=sys.stderr)
                return 2
            mode = None
            if "--mode" in argv:
                i = argv.index("--mode")
                mode = argv[i + 1] if i + 1 < len(argv) else None
            _print(create_sandbox(argv[1], mode=mode, db_path=db_path))
            return 0
        if cmd == "inspect":
            if len(argv) < 2:
                print("inspect TASK", file=sys.stderr)
                return 2
            _print(inspect_sandbox(argv[1], db_path=db_path))
            return 0
        if cmd == "destroy":
            if len(argv) < 2:
                print("destroy TASK", file=sys.stderr)
                return 2
            _print(destroy_sandbox(argv[1], db_path=db_path))
            return 0
        print(f"unknown: {cmd}", file=sys.stderr)
        return 2
    except Exception as e:
        print(f"error: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
