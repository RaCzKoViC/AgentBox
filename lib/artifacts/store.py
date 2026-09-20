#!/usr/bin/env python3
"""AgentBox v5 artifacts — register files under ~/.local/share/agentbox/v5/artifacts/."""
from __future__ import annotations

import json
import os
import shutil
import sys
from pathlib import Path
from typing import Any, Optional


def _ensure_path() -> None:
    lib = str(Path(__file__).resolve().parent.parent)
    if lib not in sys.path:
        sys.path.insert(0, lib)


def _db():
    _ensure_path()
    from storage import db as dbmod  # type: ignore

    return dbmod


def artifacts_root() -> Path:
    home = Path(os.environ.get("AGENTBOX_V5_HOME", Path.home() / ".local/share/agentbox/v5"))
    return home / "artifacts"


def artifact_dir(task_id: str, agent_name: str = "default") -> Path:
    """Path: ~/.local/share/agentbox/v5/artifacts/<TASK_ID>/<agent_name>/"""
    d = artifacts_root() / task_id / (agent_name or "default")
    d.mkdir(parents=True, exist_ok=True)
    return d


def register_artifact(
    task_id: str,
    path: str,
    agent_name: str = "",
    kind: str = "file",
    run_id: Optional[str] = None,
    metadata: Optional[dict] = None,
    copy: bool = False,
    db_path: Optional[str] = None,
) -> dict:
    """Register an artifact; optionally copy into the artifacts tree."""
    db = _db()
    task = db.get_task(task_id, db_path=db_path)
    if not task:
        raise KeyError(f"task not found: {task_id}")

    src = Path(path).expanduser()
    agent = agent_name or "default"
    dest_dir = artifact_dir(task_id, agent)
    if copy and src.is_file():
        dest = dest_dir / src.name
        shutil.copy2(str(src), str(dest))
        stored = str(dest)
    elif src.exists():
        # If already under artifacts root, keep; else record absolute path
        stored = str(src.resolve())
        # Ensure parent dir exists for convention
        dest_dir.mkdir(parents=True, exist_ok=True)
    else:
        # Allow registering a planned path under artifacts dir
        dest = dest_dir / Path(path).name
        stored = str(dest)

    aid = db.new_id("a_")
    now = db.utc_now()
    with db.connect(db_path) as conn:
        conn.execute(
            """
            INSERT INTO artifacts (id, task_id, run_id, agent_name, kind, path, metadata_json, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (aid, task_id, run_id, agent, kind or "file", stored, json.dumps(metadata or {}), now),
        )
        conn.commit()

    db.emit_event(
        kind="artifact.registered",
        message=f"{kind}: {stored}",
        task_id=task_id,
        run_id=run_id,
        payload={"artifact_id": aid, "path": stored, "agent": agent},
        db_path=db_path,
    )
    return get_artifact(aid, db_path=db_path)  # type: ignore[return-value]


def get_artifact(artifact_id: str, db_path: Optional[str] = None) -> Optional[dict]:
    db = _db()
    with db.connect(db_path) as conn:
        row = conn.execute("SELECT * FROM artifacts WHERE id = ?", (artifact_id,)).fetchone()
        return dict(row) if row else None


def list_artifacts(
    task_id: Optional[str] = None,
    agent_name: Optional[str] = None,
    limit: int = 100,
    db_path: Optional[str] = None,
) -> list[dict]:
    db = _db()
    clauses = []
    params: list[Any] = []
    if task_id:
        clauses.append("task_id = ?")
        params.append(task_id)
    if agent_name:
        clauses.append("agent_name = ?")
        params.append(agent_name)
    where = ("WHERE " + " AND ".join(clauses)) if clauses else ""
    params.append(limit)
    with db.connect(db_path) as conn:
        rows = conn.execute(
            f"SELECT * FROM artifacts {where} ORDER BY created_at DESC LIMIT ?",
            params,
        ).fetchall()
        return [dict(r) for r in rows]


def write_text_artifact(
    task_id: str,
    agent_name: str,
    filename: str,
    content: str,
    kind: str = "text",
    metadata: Optional[dict] = None,
    db_path: Optional[str] = None,
) -> dict:
    dest_dir = artifact_dir(task_id, agent_name)
    dest = dest_dir / filename
    dest.write_text(content, encoding="utf-8")
    return register_artifact(
        task_id=task_id,
        path=str(dest),
        agent_name=agent_name,
        kind=kind,
        metadata=metadata,
        db_path=db_path,
    )


def main(argv: Optional[list[str]] = None) -> int:
    argv = list(argv if argv is not None else sys.argv[1:])
    db_path = os.environ.get("AGENTBOX_V5_DB")
    if not argv:
        print("usage: store.py register|list|show|write ...", file=sys.stderr)
        return 2
    cmd = argv[0]
    try:
        if cmd == "register":
            import argparse

            p = argparse.ArgumentParser()
            p.add_argument("task_id")
            p.add_argument("path")
            p.add_argument("--agent", default="default")
            p.add_argument("--kind", default="file")
            p.add_argument("--copy", action="store_true")
            args = p.parse_args(argv[1:])
            print(json.dumps(
                register_artifact(
                    args.task_id, args.path, agent_name=args.agent,
                    kind=args.kind, copy=args.copy, db_path=db_path,
                ),
                indent=2, default=str,
            ))
            return 0
        if cmd == "list":
            import argparse

            p = argparse.ArgumentParser()
            p.add_argument("--task", default=None)
            p.add_argument("--agent", default=None)
            args = p.parse_args(argv[1:])
            print(json.dumps(list_artifacts(task_id=args.task, agent_name=args.agent, db_path=db_path), indent=2, default=str))
            return 0
        if cmd == "show":
            row = get_artifact(argv[1], db_path=db_path)
            if not row:
                print(f"not found: {argv[1]}", file=sys.stderr)
                return 1
            print(json.dumps(row, indent=2, default=str))
            return 0
        if cmd == "write":
            import argparse

            p = argparse.ArgumentParser()
            p.add_argument("task_id")
            p.add_argument("--agent", default="default")
            p.add_argument("--name", required=True)
            p.add_argument("--content", required=True)
            p.add_argument("--kind", default="text")
            args = p.parse_args(argv[1:])
            print(json.dumps(
                write_text_artifact(args.task_id, args.agent, args.name, args.content, kind=args.kind, db_path=db_path),
                indent=2, default=str,
            ))
            return 0
        print(f"unknown: {cmd}", file=sys.stderr)
        return 2
    except Exception as e:
        print(f"error: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
