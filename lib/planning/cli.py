#!/usr/bin/env python3
"""CLI: agentbox5 goal|plan|workflow|reflect ..."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


def _out(obj):
    print(json.dumps(obj, indent=2, default=str))


def cmd_goal(args: argparse.Namespace) -> int:
    from planning import store
    from planning.planner import create_goal, generate_plan, plan_from_template
    from planning.goal_tracker import goal_progress

    if args.action == "create":
        if args.template:
            result = plan_from_template(
                args.title or "Untitled goal",
                args.description or "",
                template=args.template,
                project_id=args.project or "",
            )
            _out(result)
            return 0
        if not args.title:
            print("--title required", file=sys.stderr)
            return 2
        goal = create_goal(args.title, args.description or "", project_id=args.project or "")
        _out(goal)
        return 0
    if args.action == "list":
        _out(store.list_goals(status=args.status))
        return 0
    if args.action == "show":
        g = store.get_goal(args.goal_id)
        if not g:
            print(f"goal not found: {args.goal_id}", file=sys.stderr)
            return 1
        try:
            g["progress"] = goal_progress(args.goal_id)
        except Exception as exc:
            g["progress_error"] = str(exc)
        _out(g)
        return 0
    if args.action == "plan":
        plan = generate_plan(args.goal_id, template=args.template or None)
        _out(plan)
        return 0
    if args.action == "progress":
        _out(goal_progress(args.goal_id))
        return 0
    return 2


def cmd_plan(args: argparse.Namespace) -> int:
    from planning import store
    from planning.planner import generate_plan
    from planning.plan_revision import revise_plan
    from planning.task_graph import validate_graph, ordered_nodes, critical_path
    from planning.plan_quality import score_plan

    if args.action == "create":
        plan = generate_plan(args.goal_id, template=args.template or None)
        _out(plan)
        return 0
    if args.action == "list":
        _out(store.list_plans(goal_id=args.goal_id or None))
        return 0
    if args.action == "show":
        p = store.get_plan(args.plan_id)
        if not p:
            print(f"plan not found: {args.plan_id}", file=sys.stderr)
            return 1
        _out(p)
        return 0
    if args.action == "graph":
        p = store.get_plan(args.plan_id)
        if not p:
            print(f"plan not found: {args.plan_id}", file=sys.stderr)
            return 1
        nodes = p.get("nodes") or []
        edges = list((p.get("graph") or {}).get("edges") or [])
        if not edges:
            for n in nodes:
                for d in n.get("dependencies") or []:
                    edges.append({"from": d, "to": n["id"], "type": "hard"})
        graph = {"nodes": nodes, "edges": edges}
        try:
            order = ordered_nodes(graph)
            order_ids = [n["id"] for n in order]
            order_err = None
        except Exception as exc:
            order_ids, order_err = [], str(exc)
        try:
            cpath = critical_path(graph)
        except Exception as exc:
            cpath = {"error": str(exc)}
        _out({
            "plan_id": args.plan_id,
            "ordered_ids": order_ids,
            "order_error": order_err,
            "critical_path": cpath,
            "validation": validate_graph(graph),
            "nodes": [
                {
                    "id": n["id"], "title": n.get("title"), "agent": n.get("agent"),
                    "deps": n.get("dependencies"), "status": n.get("status"),
                }
                for n in nodes
            ],
        })
        return 0
    if args.action == "revise":
        result = revise_plan(
            args.plan_id,
            reason=args.reason or "manual revision",
            observations={"error": args.reason or "manual revision", "attempt": 1},
            insert_retry=not args.no_retry,
        )
        _out(result)
        return 0
    if args.action == "validate":
        p = store.get_plan(args.plan_id)
        if not p:
            print(f"plan not found: {args.plan_id}", file=sys.stderr)
            return 1
        nodes = p.get("nodes") or []
        edges = list((p.get("graph") or {}).get("edges") or [])
        graph = {"nodes": nodes, "edges": edges}
        _out({"validation": validate_graph(graph), "quality": score_plan(graph)})
        return 0
    return 2


def cmd_workflow(args: argparse.Namespace) -> int:
    from planning.workflow_templates import list_templates, load_template, compile_template
    from planning.planner import plan_from_template

    if args.action == "list":
        _out(list_templates())
        return 0
    if args.action == "show":
        _out(load_template(args.name))
        return 0
    if args.action == "compile":
        _out(compile_template(args.name, goal={"title": args.title or args.name}, analysis={}))
        return 0
    if args.action == "run":
        result = plan_from_template(
            args.title or f"Run workflow {args.name}",
            args.description or "",
            template=args.name,
        )
        _out(result)
        return 0
    return 2


def cmd_reflect(args: argparse.Namespace) -> int:
    from planning import store
    from planning.reflection import reflect

    if args.action == "list":
        _out(store.list_reflections(goal_id=args.goal_id or None))
        return 0
    if args.action == "run":
        result = reflect(
            goal_id=args.goal_id,
            task_id=args.task_id or "",
            plan_id=args.plan_id or "",
            run_result={
                "status": args.status or "failed",
                "error": args.error or "synthetic failure",
                "attempt": 1,
            },
        )
        _out(result)
        return 0
    return 2


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="planning")
    sub = p.add_subparsers(dest="cmd")

    g = sub.add_parser("goal")
    g.add_argument("action", choices=["create", "list", "show", "plan", "progress"])
    g.add_argument("goal_id", nargs="?")
    g.add_argument("--title", default="")
    g.add_argument("--description", default="")
    g.add_argument("--project", default="")
    g.add_argument("--template", default="")
    g.add_argument("--status", default=None)

    pl = sub.add_parser("plan")
    pl.add_argument("action", choices=["create", "list", "show", "graph", "revise", "validate"])
    pl.add_argument("id", nargs="?")
    pl.add_argument("--goal-id", dest="goal_id", default="")
    pl.add_argument("--plan-id", dest="plan_id", default="")
    pl.add_argument("--template", default="")
    pl.add_argument("--reason", default="")
    pl.add_argument("--no-retry", action="store_true")

    w = sub.add_parser("workflow")
    w.add_argument("action", choices=["list", "show", "compile", "run"])
    w.add_argument("name", nargs="?", default="")
    w.add_argument("--title", default="")
    w.add_argument("--description", default="")

    r = sub.add_parser("reflect")
    r.add_argument("action", choices=["list", "run"])
    r.add_argument("--goal-id", dest="goal_id", default="")
    r.add_argument("--task-id", dest="task_id", default="")
    r.add_argument("--plan-id", dest="plan_id", default="")
    r.add_argument("--status", default="failed")
    r.add_argument("--error", default="")
    return p


def main(argv=None) -> int:
    argv = list(argv if argv is not None else sys.argv[1:])
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.cmd == "goal":
        if args.action in ("show", "plan", "progress") and not args.goal_id:
            print("goal_id required", file=sys.stderr)
            return 2
        return cmd_goal(args)
    if args.cmd == "plan":
        if not args.plan_id and args.id:
            if args.action in ("create", "list"):
                args.goal_id = args.goal_id or args.id
            else:
                args.plan_id = args.id
        if args.action == "create" and not args.goal_id:
            print("goal_id required", file=sys.stderr)
            return 2
        if args.action in ("show", "graph", "revise", "validate") and not args.plan_id:
            print("plan_id required", file=sys.stderr)
            return 2
        return cmd_plan(args)
    if args.cmd == "workflow":
        if args.action in ("show", "compile", "run") and not args.name:
            print("template name required", file=sys.stderr)
            return 2
        return cmd_workflow(args)
    if args.cmd == "reflect":
        if not args.goal_id:
            print("--goal-id required", file=sys.stderr)
            return 2
        return cmd_reflect(args)
    parser.print_help()
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
