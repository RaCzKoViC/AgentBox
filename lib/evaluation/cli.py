#!/usr/bin/env python3
"""CLI: agent5 eval|benchmark|propose|baseline"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

_HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(_HERE.parent))


def _print(obj: Any) -> None:
    print(json.dumps(obj, indent=2, ensure_ascii=False, default=str))


def cmd_eval_list(_args: argparse.Namespace) -> int:
    from evaluation.suites import list_suites
    suites = list_suites(sync=True)
    _print({
        "suites": [
            {"id": s["id"], "name": s.get("name"), "version": s.get("version"),
             "cases": s.get("case_count"), "description": s.get("description")}
            for s in suites
        ],
        "count": len(suites),
    })
    return 0


def cmd_eval_run(args: argparse.Namespace) -> int:
    from evaluation.harness import run_suite
    result = run_suite(
        args.suite,
        subject_type=args.subject_type,
        subject_id=args.subject_id,
        set_as_baseline=args.set_baseline,
        threshold=args.threshold,
    )
    _print({
        "run_id": result["run_id"],
        "suite_id": result["suite_id"],
        "status": result["status"],
        "score": result["score"],
        "gate": result["gate"],
        "summary": result["summary"],
        "results": [
            {"case_id": r["case_id"], "success": r["success"], "error": r.get("error")}
            for r in result["results"]
        ],
        "regressions": {
            "has_regression": result["regressions"].get("has_regression"),
            "events": result["regressions"].get("events"),
        },
    })
    return 0 if result["status"] == "passed" else 1


def cmd_eval_show(args: argparse.Namespace) -> int:
    from evaluation.store import get_run
    run = get_run(args.run_id)
    if not run:
        _print({"error": "not found", "run_id": args.run_id})
        return 1
    _print(run)
    return 0


def cmd_benchmark_list(_args: argparse.Namespace) -> int:
    from benchmarks.registry import list_benchmarks
    items = list_benchmarks()
    _print({"benchmarks": items, "count": len(items)})
    return 0


def cmd_propose_list(args: argparse.Namespace) -> int:
    from evaluation.proposals import list_proposals
    items = list_proposals(status=args.status)
    _print({"proposals": items, "count": len(items)})
    return 0


def cmd_propose_show(args: argparse.Namespace) -> int:
    from evaluation.proposals import get_proposal
    p = get_proposal(args.proposal_id)
    if not p:
        _print({"error": "not found", "id": args.proposal_id})
        return 1
    _print(p)
    return 0


def cmd_propose_approve(args: argparse.Namespace) -> int:
    from evaluation.proposals import approve
    p = approve(args.proposal_id, apply=args.apply)
    _print(p)
    return 0


def cmd_propose_reject(args: argparse.Namespace) -> int:
    from evaluation.proposals import reject
    p = reject(args.proposal_id, reason=args.reason or "")
    _print(p)
    return 0


def cmd_propose_mine(_args: argparse.Namespace) -> int:
    from evaluation.failure_mining import propose_from_failures, mine_failures
    mined = mine_failures()
    created = propose_from_failures(min_count=1)
    _print({"mined": mined, "proposals_created": created, "count": len(created)})
    return 0


def cmd_baseline_show(args: argparse.Namespace) -> int:
    from evaluation.baselines import get_baseline, list_baselines
    if args.suite:
        bl = get_baseline(args.suite)
        if not bl:
            _print({"error": "no baseline", "suite": args.suite})
            return 1
        _print(bl)
    else:
        _print({"baselines": list_baselines(), "count": len(list_baselines())})
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="agent5-eval")
    sub = p.add_subparsers(dest="cmd")

    # eval
    ev = sub.add_parser("eval")
    ev_sub = ev.add_subparsers(dest="eval_cmd")
    ev_sub.add_parser("list")
    ev_run = ev_sub.add_parser("run")
    ev_run.add_argument("suite")
    ev_run.add_argument("--subject-type", default="platform")
    ev_run.add_argument("--subject-id", default="agentbox")
    ev_run.add_argument("--set-baseline", action="store_true")
    ev_run.add_argument("--threshold", type=float, default=None)
    ev_show = ev_sub.add_parser("show")
    ev_show.add_argument("run_id")

    # benchmark
    bm = sub.add_parser("benchmark")
    bm_sub = bm.add_subparsers(dest="benchmark_cmd")
    bm_sub.add_parser("list")

    # propose
    pr = sub.add_parser("propose")
    pr_sub = pr.add_subparsers(dest="propose_cmd")
    pr_list = pr_sub.add_parser("list")
    pr_list.add_argument("--status", default=None)
    pr_show = pr_sub.add_parser("show")
    pr_show.add_argument("proposal_id")
    pr_ap = pr_sub.add_parser("approve")
    pr_ap.add_argument("proposal_id")
    pr_ap.add_argument("--apply", action="store_true",
                       help="Apply low-risk change if AGENTBOX_AUTO_APPROVE=1")
    pr_rj = pr_sub.add_parser("reject")
    pr_rj.add_argument("proposal_id")
    pr_rj.add_argument("--reason", default="")
    pr_sub.add_parser("mine")

    # baseline
    bl = sub.add_parser("baseline")
    bl_sub = bl.add_subparsers(dest="baseline_cmd")
    bl_show = bl_sub.add_parser("show")
    bl_show.add_argument("suite", nargs="?", default=None)

    return p


def main(argv: list[str] | None = None) -> int:
    argv = list(argv if argv is not None else sys.argv[1:])
    # allow invocation as: cli.py eval list  OR  eval list when dispatched from agentbox5
    parser = build_parser()
    # If first token is already a known top-level, fine; else wrap
    if argv and argv[0] not in ("eval", "benchmark", "propose", "baseline", "-h", "--help"):
        # agentbox5 calls: python cli.py list  with AGENTBOX_EVAL_CMD=eval etc — handle flat
        pass
    args = parser.parse_args(argv)
    if args.cmd == "eval":
        if args.eval_cmd == "list":
            return cmd_eval_list(args)
        if args.eval_cmd == "run":
            return cmd_eval_run(args)
        if args.eval_cmd == "show":
            return cmd_eval_show(args)
        parser.parse_args(["eval", "-h"])
        return 2
    if args.cmd == "benchmark":
        if args.benchmark_cmd == "list":
            return cmd_benchmark_list(args)
        return 2
    if args.cmd == "propose":
        if args.propose_cmd == "list":
            return cmd_propose_list(args)
        if args.propose_cmd == "show":
            return cmd_propose_show(args)
        if args.propose_cmd == "approve":
            return cmd_propose_approve(args)
        if args.propose_cmd == "reject":
            return cmd_propose_reject(args)
        if args.propose_cmd == "mine":
            return cmd_propose_mine(args)
        return 2
    if args.cmd == "baseline":
        if args.baseline_cmd == "show":
            return cmd_baseline_show(args)
        return 2
    parser.print_help()
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
