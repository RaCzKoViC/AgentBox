#!/usr/bin/env python3
"""AgentBox v5.2 context builder — memory + task + events + vector intelligence."""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any, Optional

DEFAULT_MAX_TOKENS = 4000
DEFAULT_CHARS_PER_TOKEN = 4


def _lib_root() -> Path:
    return Path(__file__).resolve().parent.parent


def _ensure_path() -> None:
    lib = str(_lib_root())
    if lib not in sys.path:
        sys.path.insert(0, lib)


def _load_config() -> dict:
    """Load memory.toml context section (best-effort)."""
    home = Path(os.environ.get("AGENTBOX_V5_HOME", Path.home() / ".local/share/agentbox/v5"))
    candidates = [
        home / "config" / "memory.toml",
        _lib_root().parent / "config" / "memory.toml",
    ]
    cfg: dict[str, Any] = {
        "max_tokens": DEFAULT_MAX_TOKENS,
        "max_tokens_user": 800,
        "max_tokens_project": 800,
        "max_tokens_agent": 600,
        "max_tokens_task": 800,
        "max_tokens_events": 1000,
        "max_events": 20,
        "chars_per_token": DEFAULT_CHARS_PER_TOKEN,
    }
    path = next((c for c in candidates if c.is_file()), None)
    if not path:
        return cfg
    try:
        text = path.read_text(encoding="utf-8")
        # Minimal TOML parse for [context] flat keys
        in_ctx = False
        for line in text.splitlines():
            s = line.strip()
            if not s or s.startswith("#"):
                continue
            if s.startswith("["):
                in_ctx = s.strip("[]").strip() == "context"
                continue
            if not in_ctx or "=" not in s:
                continue
            k, v = s.split("=", 1)
            k = k.strip()
            v = v.strip().strip('"').strip("'")
            if k in cfg:
                try:
                    cfg[k] = int(v) if "." not in v else float(v)
                except ValueError:
                    cfg[k] = v
    except OSError:
        pass
    return cfg


def estimate_tokens(text: str, chars_per_token: int = DEFAULT_CHARS_PER_TOKEN) -> int:
    if not text:
        return 0
    cpt = max(1, int(chars_per_token))
    return max(1, (len(text) + cpt - 1) // cpt)


def truncate_to_tokens(text: str, max_tokens: int, chars_per_token: int = DEFAULT_CHARS_PER_TOKEN) -> str:
    if max_tokens <= 0 or not text:
        return ""
    max_chars = int(max_tokens) * max(1, int(chars_per_token))
    if len(text) <= max_chars:
        return text
    cut = text[: max(0, max_chars - 20)]
    return cut.rstrip() + "\n…[truncated]"


def _format_memories(rows: list[dict], max_tokens: int, cpt: int) -> str:
    if not rows:
        return ""
    lines: list[str] = []
    budget = max_tokens
    for r in rows:
        line = f"- [{r.get('kind', 'note')}] {r.get('content', '')}"
        cost = estimate_tokens(line, cpt)
        if cost > budget:
            rem = truncate_to_tokens(line, budget, cpt)
            if rem:
                lines.append(rem)
            break
        lines.append(line)
        budget -= cost
        if budget <= 0:
            break
    return "\n".join(lines)


def build_context(
    task_id: str,
    max_tokens: Optional[int] = None,
    agent_id: Optional[str] = None,
    project_path: Optional[str] = None,
    db_path: Optional[str] = None,
) -> dict:
    """Assemble a compact context pack for a task.

    Returns dict with keys: text, sections, tokens_est, task_id.
    """
    _ensure_path()
    from storage import db as dbmod  # type: ignore
    from memory.store import list_memories, project_key  # type: ignore

    cfg = _load_config()
    cpt = int(cfg.get("chars_per_token") or DEFAULT_CHARS_PER_TOKEN)
    total_budget = int(max_tokens if max_tokens is not None else cfg.get("max_tokens") or DEFAULT_MAX_TOKENS)

    task = dbmod.get_task(task_id, db_path=db_path)
    if not task:
        raise KeyError(f"task not found: {task_id}")

    proj = project_path or task.get("project_id") or ""
    pkey = project_key(proj) if proj else ""
    meta = {}
    try:
        meta = json.loads(task.get("meta_json") or "{}")
    except json.JSONDecodeError:
        meta = {}
    aid = agent_id or meta.get("agent_id") or meta.get("agent") or ""

    sections: dict[str, str] = {}

    # Task summary (always include, small)
    task_block = (
        f"id: {task['id']}\n"
        f"title: {task.get('title', '')}\n"
        f"status: {task.get('status', '')}\n"
        f"project: {proj}\n"
        f"description: {(task.get('description') or '')[:500]}"
    )
    sections["task"] = truncate_to_tokens(task_block, min(400, total_budget // 5), cpt)

    user_rows = list_memories(scope="user", scope_key="default", limit=50, db_path=db_path)
    sections["user"] = _format_memories(
        user_rows, int(cfg.get("max_tokens_user") or 800), cpt
    )

    project_rows = list_memories(scope="project", scope_key=pkey, limit=50, db_path=db_path) if pkey else []
    sections["project"] = _format_memories(
        project_rows, int(cfg.get("max_tokens_project") or 800), cpt
    )

    agent_rows = (
        list_memories(scope="agent", scope_key=aid, limit=50, db_path=db_path) if aid else []
    )
    sections["agent"] = _format_memories(
        agent_rows, int(cfg.get("max_tokens_agent") or 600), cpt
    )

    task_rows = list_memories(scope="task", scope_key=task_id, limit=50, db_path=db_path)
    sections["task_memory"] = _format_memories(
        task_rows, int(cfg.get("max_tokens_task") or 800), cpt
    )

    events = dbmod.list_events(task_id=task_id, limit=int(cfg.get("max_events") or 20), db_path=db_path)
    ev_lines = []
    for e in reversed(events):  # chronological
        ev_lines.append(f"- {e.get('ts', '')} [{e.get('kind', '')}] {e.get('message', '')}")
    sections["events"] = truncate_to_tokens(
        "\n".join(ev_lines), int(cfg.get("max_tokens_events") or 1000), cpt
    )

    # v5.2: inject top-k vector memory / semantic hits (best-effort; never fail build)
    try:
        from intelligence.retrieval import retrieve_context
        from intelligence.context_router import route_context, format_for_prompt
        from intelligence.context_compression import compress_package
        q = f"{task.get('title','')} {task.get('description','')}"
        pid = None
        # project_id in tasks may be a path
        if proj:
            try:
                from intelligence.semantic_index import project_id_from_path
                from pathlib import Path as _P
                pp = _P(proj)
                pid = project_id_from_path(pp) if pp.exists() else str(proj)
            except Exception:
                pid = str(proj)
        intel = retrieve_context(q, project_id=pid, task_id=task_id, agent_name=aid or None, top_k=8, db_path=db_path)
        routed = route_context(intel, aid or "coder")
        routed["constraints"] = [
            f"approval_policy={task.get('approval_policy') or 'auto'}",
            f"sandbox_mode={task.get('sandbox_mode') or 'worktree'}",
        ]
        routed = compress_package(routed, token_budget=min(1200, total_budget // 3))
        sections["intelligence"] = truncate_to_tokens(
            format_for_prompt(routed), min(1200, total_budget // 3), cpt
        )
    except Exception:
        sections["intelligence"] = ""

    # Assemble with remaining total budget (priority order)
    order = [
        ("TASK", "task"),
        ("USER MEMORY", "user"),
        ("PROJECT MEMORY", "project"),
        ("AGENT MEMORY", "agent"),
        ("TASK MEMORY", "task_memory"),
        ("INTELLIGENCE", "intelligence"),
        ("RECENT EVENTS", "events"),
    ]
    parts: list[str] = []
    used = 0
    for label, key in order:
        body = (sections.get(key) or "").strip()
        if not body:
            continue
        block = f"## {label}\n{body}"
        cost = estimate_tokens(block, cpt)
        remaining = total_budget - used
        if remaining <= 0:
            break
        if cost > remaining:
            block = truncate_to_tokens(block, remaining, cpt)
            cost = estimate_tokens(block, cpt)
        parts.append(block)
        used += cost

    text = "\n\n".join(parts).strip()
    if not text:
        text = f"## TASK\n{sections.get('task', f'id: {task_id}')}"

    return {
        "task_id": task_id,
        "text": text,
        "sections": {k: v for k, v in sections.items() if v},
        "tokens_est": estimate_tokens(text, cpt),
        "max_tokens": total_budget,
        "project_key": pkey,
        "agent_id": aid,
    }



def build_handoff_context(
    task_id: str,
    source_agent: str,
    target_agent: str,
    reason: str = "",
    db_path: Optional[str] = None,
    max_memories: int = 10,
    max_events: int = 15,
) -> dict:
    """Compact HandoffContext pack — NOT full history.

    Keys: task_goal, source_summary, memories, files, artifacts, findings, constraints.
    """
    _ensure_path()
    from storage import db as dbmod  # type: ignore
    from memory.store import list_memories  # type: ignore

    task = dbmod.get_task(task_id, db_path=db_path)
    if not task:
        raise KeyError(f"task not found: {task_id}")

    task_goal = (task.get("title") or "").strip()
    desc = (task.get("description") or "").strip()
    if desc:
        task_goal = f"{task_goal}: {desc[:300]}" if task_goal else desc[:400]

    # Source summary from recent events by source / agent
    events = dbmod.list_events(task_id=task_id, limit=max_events, db_path=db_path)
    findings: list[str] = []
    for e in reversed(events):
        kind = e.get("kind") or ""
        msg = (e.get("message") or "").strip()
        if not msg:
            continue
        if kind.startswith("handoff.") or kind.startswith("agent.") or kind.startswith("task."):
            findings.append(f"[{kind}] {msg[:200]}")
        if len(findings) >= 8:
            break

    source_summary = (
        f"{source_agent} hands off to {target_agent}"
        + (f" because: {reason}" if reason else "")
    )
    if findings:
        source_summary += f" | recent: {findings[0][:120]}"

    # Memories: task + agent (source) scopes — compact
    memories: list[dict] = []
    for scope, key in (("task", task_id), ("agent", source_agent)):
        try:
            rows = list_memories(scope=scope, scope_key=key, limit=max_memories, db_path=db_path)
        except Exception:
            rows = []
        for r in rows[:5]:
            memories.append({
                "scope": scope,
                "kind": r.get("kind"),
                "content": (r.get("content") or "")[:300],
            })

    # Artifacts paths (if table exists)
    artifacts: list[str] = []
    try:
        with dbmod.connect(db_path) as conn:
            rows = conn.execute(
                "SELECT path, agent_name, kind FROM artifacts WHERE task_id = ? ORDER BY created_at DESC LIMIT 20",
                (task_id,),
            ).fetchall()
            artifacts = [f"{r['kind']}:{r['path']}" for r in rows]
    except Exception:
        artifacts = []

    # Files: from meta or empty (no full history crawl)
    files: list[str] = []
    try:
        meta = json.loads(task.get("meta_json") or "{}")
        for f in (meta.get("files") or meta.get("touched_files") or [])[:20]:
            files.append(str(f))
    except Exception:
        pass

    constraints: list[str] = []
    if task.get("approval_policy"):
        constraints.append(f"approval_policy={task['approval_policy']}")
    if task.get("sandbox_mode"):
        constraints.append(f"sandbox_mode={task['sandbox_mode']}")
    if reason:
        constraints.append(f"handoff_reason={reason[:200]}")

    # v5.2 vector memory top-k into handoff
    try:
        from intelligence.retrieval import retrieve_context
        q = task_goal or reason or task_id
        intel = retrieve_context(q, task_id=task_id, agent_name=source_agent, top_k=5, db_path=db_path)
        for h in intel.get("hits") or []:
            if h.get("source") == "memory":
                memories.append({
                    "scope": "vector",
                    "kind": h.get("memory_type") or "vector",
                    "content": (h.get("text_preview") or h.get("content") or "")[:300],
                })
            elif len(files) < 20 and h.get("file_path"):
                files.append(str(h["file_path"]))
    except Exception:
        pass

    constraints.append("no_full_history")

    return {
        "task_goal": task_goal,
        "source_summary": source_summary,
        "source_agent": source_agent,
        "target_agent": target_agent,
        "reason": reason or "",
        "memories": memories,
        "files": files,
        "artifacts": artifacts,
        "findings": findings,
        "constraints": constraints,
    }


def main(argv: Optional[list[str]] = None) -> int:

    argv = list(argv if argv is not None else sys.argv[1:])
    if not argv or argv[0] in ("-h", "--help"):
        print("usage: context.py build TASK_ID | handoff-context TASK SRC TGT [--reason R]", file=sys.stderr)
        return 2
    cmd = argv[0]
    db_path = os.environ.get("AGENTBOX_V5_DB")
    try:
        if cmd == "build":
            import argparse

            p = argparse.ArgumentParser()
            p.add_argument("task_id")
            p.add_argument("--max-tokens", type=int, default=None)
            p.add_argument("--agent", default=None)
            p.add_argument("--text-only", action="store_true")
            args = p.parse_args(argv[1:])
            pack = build_context(
                args.task_id,
                max_tokens=args.max_tokens,
                agent_id=args.agent,
                db_path=db_path,
            )
            if args.text_only:
                print(pack["text"])
            else:
                print(json.dumps(pack, indent=2, ensure_ascii=False, default=str))
            return 0
        if cmd in ("handoff-context", "handoff_context"):
            import argparse

            p = argparse.ArgumentParser()
            p.add_argument("task_id")
            p.add_argument("source")
            p.add_argument("target")
            p.add_argument("--reason", default="")
            args = p.parse_args(argv[1:])
            pack = build_handoff_context(
                args.task_id, args.source, args.target, reason=args.reason, db_path=db_path,
            )
            print(json.dumps(pack, indent=2, ensure_ascii=False, default=str))
            return 0
        print(f"unknown: {cmd}", file=sys.stderr)
        return 2
    except Exception as e:
        print(f"error: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
