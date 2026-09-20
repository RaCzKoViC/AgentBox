#!/usr/bin/env python3
"""CLI: agent5 intelligence status|index|search|router|memory ..."""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Optional

_HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(_HERE.parent))


def _out(obj) -> None:
    print(json.dumps(obj, indent=2, ensure_ascii=False, default=str))


def cmd_status(argv: list[str]) -> int:
    from intelligence.embeddings import model_info
    from intelligence.semantic_index import status as idx_status
    from intelligence.model_router import list_models, ensure_registry
    from intelligence.experience_memory import list_memories, list_experience
    from intelligence.quality_signals import summary as qsum

    ensure_registry()
    st = idx_status()
    mems = list_memories(limit=5)
    _out({
        "version": "5.2.0",
        "embedding": model_info(),
        "index": st,
        "models": [{"provider": m["provider"], "model": m["model"], "local": m.get("local")} for m in list_models()],
        "vector_memories": len(mems),
        "experience_count": len(list_experience(limit=1000)),
        "quality": qsum(),
    })
    return 0


def cmd_index(argv: list[str]) -> int:
    from intelligence.semantic_index import index_project

    if not argv:
        print("usage: intelligence index PROJECT_PATH [--force]", file=sys.stderr)
        return 2
    force = "--force" in argv
    path = next(a for a in argv if not a.startswith("-"))
    _out(index_project(path, force=force))
    return 0


def cmd_search(argv: list[str]) -> int:
    from intelligence.retrieval import retrieve_context
    from intelligence.semantic_index import project_id_from_path
    from pathlib import Path as P

    if not argv:
        print("usage: intelligence search QUERY [--project PATH|ID] [--top-k N]", file=sys.stderr)
        return 2
    top_k = 10
    project_id = None
    args = list(argv)
    if "--project" in args:
        i = args.index("--project")
        proj = args[i + 1]
        del args[i : i + 2]
        p = P(proj)
        project_id = project_id_from_path(p) if p.exists() else proj
    if "--top-k" in args:
        i = args.index("--top-k")
        top_k = int(args[i + 1])
        del args[i : i + 2]
    q = " ".join(args)
    pack = retrieve_context(q, project_id=project_id, top_k=top_k)
    _out(pack)
    return 0


def cmd_router(argv: list[str]) -> int:
    from intelligence.model_router import route

    if not argv:
        print("usage: intelligence router TASK_TEXT|TYPE [--privacy MODE]", file=sys.stderr)
        return 2
    privacy = "ANY_APPROVED"
    args = list(argv)
    if "--privacy" in args:
        i = args.index("--privacy")
        privacy = args[i + 1]
        del args[i : i + 2]
    task = " ".join(args)
    known = {
        "coding", "bugfix", "refactor", "research", "security", "performance",
        "documentation", "testing", "architecture", "deployment", "data_analysis",
    }
    if task.strip() in known:
        _out(route(task.strip(), title=task, privacy=privacy))
    else:
        _out(route(None, title=task, description=task, privacy=privacy))
    return 0


def cmd_memory(argv: list[str]) -> int:
    from intelligence.experience_memory import list_memories, write_memory, list_experience

    sub = argv[0] if argv else "list"
    rest = argv[1:] if argv else []
    if sub == "list":
        _out({"memories": list_memories(limit=50), "experience": list_experience(limit=20)})
        return 0
    if sub == "write":
        content = " ".join(rest) if rest else ""
        if not content:
            print("need content", file=sys.stderr)
            return 2
        _out(write_memory(
            content,
            memory_type="lesson",
            provenance={"source": "cli", "manual": True},
            importance=0.7,
        ))
        return 0
    print("usage: intelligence memory list|write TEXT", file=sys.stderr)
    return 2


def main(argv: Optional[list[str]] = None) -> int:
    argv = list(argv if argv is not None else sys.argv[1:])
    if not argv or argv[0] in ("-h", "--help"):
        print(
            "usage: intelligence status|index PROJECT|search Q|router TASK|memory list|write",
            file=sys.stderr,
        )
        return 2
    cmd = argv[0]
    rest = argv[1:]
    if cmd == "status":
        return cmd_status(rest)
    if cmd == "index":
        return cmd_index(rest)
    if cmd in ("search",):
        return cmd_search(rest)
    if cmd in ("router", "route"):
        return cmd_router(rest)
    if cmd == "memory":
        return cmd_memory(rest)
    print(f"unknown: {cmd}", file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
