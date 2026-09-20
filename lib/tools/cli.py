#!/usr/bin/env python3
"""CLI for agent5 tool ... commands."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Optional

_HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(_HERE.parent))


def _print(obj: Any) -> None:
    print(json.dumps(obj, indent=2, ensure_ascii=False, default=str))


def cmd_list(args: argparse.Namespace) -> int:
    from tools import registry
    registry.ensure_builtins()
    tools = registry.list_tools(category=args.category, query=args.query)
    if args.quiet:
        for t in tools:
            print(t["id"])
        return 0
    _print({"tools": tools, "count": len(tools)})
    return 0


def cmd_show(args: argparse.Namespace) -> int:
    from tools import registry
    t = registry.get_tool(args.tool_id)
    if not t:
        print(json.dumps({"error": "not found", "id": args.tool_id}))
        return 1
    _print(t)
    return 0


def cmd_search(args: argparse.Namespace) -> int:
    from tools.capability import find_tools
    from tools import registry
    registry.ensure_builtins()
    # search by text OR capability need
    matches = find_tools(args.query)
    if not matches:
        matches = [{"id": t["id"], **t} for t in registry.search_tools(args.query)]
    _print({"query": args.query, "matches": matches, "count": len(matches)})
    return 0


def cmd_run(args: argparse.Namespace) -> int:
    from tools.executor import execute_tool
    payload = {}
    if args.json:
        payload = json.loads(args.json)
    result = execute_tool(
        args.tool_id,
        payload,
        task_context={"task_id": args.task} if args.task else {},
        agent_context={"agent_name": args.agent} if args.agent else {},
    )
    _print(result)
    if result.get("ok"):
        return 0
    if result.get("decision") == "approval" or result.get("status") == "awaiting_approval":
        return 2
    if result.get("decision") == "deny" or result.get("denied"):
        return 1
    return 1


def cmd_health(args: argparse.Namespace) -> int:
    from tools.discovery import health_all, health_check_tool
    if args.tool_id:
        _print(health_check_tool(args.tool_id))
    else:
        _print({"health": health_all()})
    return 0


def cmd_discover(args: argparse.Namespace) -> int:
    from tools.discovery import discover
    _print(discover(register=not args.no_register))
    return 0


def cmd_enable(args: argparse.Namespace) -> int:
    from tools import registry
    t = registry.set_enabled(args.tool_id, True)
    _print(t or {"error": "not found"})
    return 0 if t else 1


def cmd_disable(args: argparse.Namespace) -> int:
    from tools import registry
    t = registry.set_enabled(args.tool_id, False)
    _print(t or {"error": "not found"})
    return 0 if t else 1


def cmd_quarantine(args: argparse.Namespace) -> int:
    from tools import registry
    t = registry.quarantine(args.tool_id, reason=args.reason or "")
    _print(t or {"error": "not found"})
    return 0 if t else 1


def cmd_find(args: argparse.Namespace) -> int:
    from tools.capability import find_tools
    constraints = {}
    if args.max_risk:
        constraints["max_risk"] = args.max_risk
    if args.category:
        constraints["category"] = args.category
    _print({"need": args.need, "matches": find_tools(args.need, constraints=constraints)})
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="agent5 tool")
    sub = p.add_subparsers(dest="cmd")

    pl = sub.add_parser("list")
    pl.add_argument("--category", default=None)
    pl.add_argument("--query", default=None)
    pl.add_argument("-q", "--quiet", action="store_true")
    pl.set_defaults(func=cmd_list)

    ps = sub.add_parser("show")
    ps.add_argument("tool_id")
    ps.set_defaults(func=cmd_show)

    psearch = sub.add_parser("search")
    psearch.add_argument("query")
    psearch.set_defaults(func=cmd_search)

    pr = sub.add_parser("run")
    pr.add_argument("tool_id")
    pr.add_argument("--json", default="{}")
    pr.add_argument("--task", default=None)
    pr.add_argument("--agent", default=None)
    pr.set_defaults(func=cmd_run)

    ph = sub.add_parser("health")
    ph.add_argument("tool_id", nargs="?", default=None)
    ph.set_defaults(func=cmd_health)

    pd = sub.add_parser("discover")
    pd.add_argument("--no-register", action="store_true")
    pd.set_defaults(func=cmd_discover)

    pe = sub.add_parser("enable")
    pe.add_argument("tool_id")
    pe.set_defaults(func=cmd_enable)

    pdis = sub.add_parser("disable")
    pdis.add_argument("tool_id")
    pdis.set_defaults(func=cmd_disable)

    pq = sub.add_parser("quarantine")
    pq.add_argument("tool_id")
    pq.add_argument("--reason", default="")
    pq.set_defaults(func=cmd_quarantine)

    pf = sub.add_parser("find")
    pf.add_argument("need")
    pf.add_argument("--max-risk", default=None)
    pf.add_argument("--category", default=None)
    pf.set_defaults(func=cmd_find)

    return p


def main(argv: Optional[list[str]] = None) -> int:
    argv = list(argv if argv is not None else sys.argv[1:])
    parser = build_parser()
    if not argv:
        parser.print_help()
        return 2
    args = parser.parse_args(argv)
    if not hasattr(args, "func"):
        parser.print_help()
        return 2
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
