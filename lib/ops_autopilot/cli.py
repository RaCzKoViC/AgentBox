#!/usr/bin/env python3
"""CLI: agent5 ops status|scan|remediate|playbook|drift|forecast|cleanup|backup-schedule|readiness|plan"""
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


def cmd_status(_args: argparse.Namespace) -> int:
    from ops_autopilot.remediation import status
    _print(status())
    return 0


def cmd_scan(args: argparse.Namespace) -> int:
    from ops_autopilot.remediation import scan
    _print(scan(dry_run=not args.apply))
    return 0


def cmd_remediate(args: argparse.Namespace) -> int:
    from ops_autopilot.remediation import remediate
    dry = not args.apply
    result = remediate(
        dry_run=dry,
        auto_low_risk=not args.no_auto,
        playbook_id=args.playbook,
        approval_id=args.approval,
        allow_high_risk=bool(args.approval) or args.allow_high_risk,
    )
    _print(result)
    return 0 if result.get("ok", True) else 1


def cmd_playbook_list(_args: argparse.Namespace) -> int:
    from ops_autopilot.playbooks import list_playbooks
    items = list_playbooks()
    _print({"playbooks": items, "count": len(items)})
    return 0


def cmd_playbook_run(args: argparse.Namespace) -> int:
    from ops_autopilot.playbooks import run_playbook
    dry = not args.apply
    result = run_playbook(
        args.playbook_id,
        dry_run=dry,
        triggered_by="cli",
        allow_high_risk=args.allow_high_risk,
    )
    _print(result)
    return 0 if result.get("status") in ("passed", "awaiting_approval") else 1


def cmd_playbook_show(args: argparse.Namespace) -> int:
    from ops_autopilot.playbooks import get_playbook
    from ops_autopilot.store import list_playbook_runs
    p = get_playbook(args.playbook_id)
    if not p:
        _print({"error": "not found", "id": args.playbook_id})
        return 1
    runs = list_playbook_runs(playbook_id=args.playbook_id, limit=10)
    _print({"playbook": p, "recent_runs": runs})
    return 0


def cmd_drift(args: argparse.Namespace) -> int:
    from ops_autopilot.drift import detect_all, reset_baseline, list_drift
    from ops_autopilot import store
    if args.reset_baseline:
        _print(reset_baseline())
        return 0
    if args.history:
        _print({"snapshots": store.list_drift(limit=args.limit)})
        return 0
    _print(detect_all(persist=not args.no_persist))
    return 0


def cmd_forecast(_args: argparse.Namespace) -> int:
    from ops_autopilot.forecast import forecast
    _print(forecast())
    return 0


def cmd_cleanup(args: argparse.Namespace) -> int:
    from ops_autopilot.cleanup import cleanup
    _print(cleanup(dry_run=not args.apply))
    return 0


def cmd_backup_schedule(_args: argparse.Namespace) -> int:
    from ops_autopilot.backup_schedule import schedule_status, should_backup, create_smart_backup
    st = schedule_status()
    _print(st)
    return 0


def cmd_backup_schedule_run(args: argparse.Namespace) -> int:
    from ops_autopilot.backup_schedule import should_backup, create_smart_backup
    dec = should_backup()
    if args.apply and dec.get("needed"):
        b = create_smart_backup()
        _print({"decision": dec, "backup": b})
    else:
        _print({"decision": dec, "dry_run": not args.apply})
    return 0


def cmd_readiness(args: argparse.Namespace) -> int:
    from ops_autopilot.readiness import upgrade_readiness
    r = upgrade_readiness(target_version=args.target)
    _print(r)
    return 0 if r.get("ready") else 1


def cmd_plan(args: argparse.Namespace) -> int:
    from ops_autopilot.readiness import plan_maintenance
    from ops_autopilot.store import list_maintenance_plans
    if args.list:
        plans = list_maintenance_plans(limit=args.limit)
        _print({"plans": plans, "count": len(plans)})
        return 0
    _print(plan_maintenance(title=args.title))
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="agent5 ops")
    sub = p.add_subparsers(dest="cmd", required=True)

    sub.add_parser("status")

    sc = sub.add_parser("scan")
    sc.add_argument("--apply", action="store_true", help="unused for scan; scan is always propose")

    rem = sub.add_parser("remediate")
    rem.add_argument("--apply", action="store_true", help="apply low-risk (default dry-run)")
    rem.add_argument("--dry-run", action="store_true", default=True, help="default")
    rem.add_argument("--no-auto", action="store_true")
    rem.add_argument("--playbook", default=None)
    rem.add_argument("--approval", default=None)
    rem.add_argument("--allow-high-risk", action="store_true")

    pb = sub.add_parser("playbook")
    pb_sub = pb.add_subparsers(dest="pb_cmd", required=True)
    pb_sub.add_parser("list")
    pbr = pb_sub.add_parser("run")
    pbr.add_argument("playbook_id")
    pbr.add_argument("--apply", action="store_true")
    pbr.add_argument("--allow-high-risk", action="store_true")
    pbs = pb_sub.add_parser("show")
    pbs.add_argument("playbook_id")

    dr = sub.add_parser("drift")
    dr.add_argument("--reset-baseline", action="store_true")
    dr.add_argument("--history", action="store_true")
    dr.add_argument("--no-persist", action="store_true")
    dr.add_argument("--limit", type=int, default=20)

    sub.add_parser("forecast")

    cl = sub.add_parser("cleanup")
    cl.add_argument("--apply", action="store_true")

    bs = sub.add_parser("backup-schedule")
    bs.add_argument("--apply", action="store_true", help="create backup if needed")

    rd = sub.add_parser("readiness")
    rd.add_argument("--target", default=None)

    pl = sub.add_parser("plan")
    pl.add_argument("--list", action="store_true")
    pl.add_argument("--title", default=None)
    pl.add_argument("--limit", type=int, default=20)

    return p


def main(argv: list[str] | None = None) -> int:
    argv = list(argv) if argv is not None else sys.argv[1:]
    # allow `ops --dry-run remediate` style from wrapper: strip global --dry-run into remediate
    global_dry = False
    if "--dry-run" in argv and argv[0] not in ("remediate", "cleanup", "playbook", "scan"):
        # e.g. agent5 ops --dry-run remediate
        argv = [a for a in argv if a != "--dry-run"]
        global_dry = True

    parser = build_parser()
    args = parser.parse_args(argv)

    if args.cmd == "status":
        return cmd_status(args)
    if args.cmd == "scan":
        return cmd_scan(args)
    if args.cmd == "remediate":
        if global_dry:
            args.apply = False
        return cmd_remediate(args)
    if args.cmd == "playbook":
        if args.pb_cmd == "list":
            return cmd_playbook_list(args)
        if args.pb_cmd == "run":
            return cmd_playbook_run(args)
        if args.pb_cmd == "show":
            return cmd_playbook_show(args)
    if args.cmd == "drift":
        return cmd_drift(args)
    if args.cmd == "forecast":
        return cmd_forecast(args)
    if args.cmd == "cleanup":
        return cmd_cleanup(args)
    if args.cmd == "backup-schedule":
        return cmd_backup_schedule_run(args) if getattr(args, "apply", False) else cmd_backup_schedule(args)
    if args.cmd == "readiness":
        return cmd_readiness(args)
    if args.cmd == "plan":
        return cmd_plan(args)
    parser.print_help()
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
