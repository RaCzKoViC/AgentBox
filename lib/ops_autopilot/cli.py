#!/usr/bin/env python3
"""CLI: agent5 ops status|scan|remediate|playbook|drift|forecast|cleanup|backup-schedule|readiness|plan|health|incident|runbook|restore-drill"""
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



def cmd_health(_args: argparse.Namespace) -> int:
    from ops_autopilot.health_registry import evaluate
    _print(evaluate(persist=True))
    return 0


def cmd_incident_list(args: argparse.Namespace) -> int:
    from ops_autopilot.incidents import list_incidents
    items = list_incidents(status=args.status, limit=args.limit)
    _print({"incidents": items, "count": len(items)})
    return 0


def cmd_incident_show(args: argparse.Namespace) -> int:
    from ops_autopilot.incidents import get_incident
    inc = get_incident(args.incident_id)
    if not inc:
        _print({"error": "not found", "id": args.incident_id})
        return 1
    _print(inc)
    return 0


def cmd_incident_close(args: argparse.Namespace) -> int:
    from ops_autopilot.incidents import close_incident
    try:
        out = close_incident(
            args.incident_id,
            message=args.message or "closed via CLI",
            resolution={"message": args.message or "closed via CLI", "confirmed": True},
        )
    except ValueError as e:
        _print({"error": str(e)})
        return 1
    _print(out)
    return 0


def cmd_runbook_list(_args: argparse.Namespace) -> int:
    from ops_autopilot.runbooks import list_runbooks
    items = list_runbooks()
    _print({"runbooks": items, "count": len(items)})
    return 0


def cmd_runbook_run(args: argparse.Namespace) -> int:
    from ops_autopilot.runbooks import run_runbook
    dry = not args.apply
    if getattr(args, "dry_run", False):
        dry = True
    try:
        result = run_runbook(
            args.runbook_id,
            dry_run=dry,
            allow_high_risk=args.allow_high_risk,
            triggered_by="cli",
        )
    except ValueError as e:
        _print({"error": str(e)})
        return 1
    _print(result)
    return 0 if result.get("status") in ("passed", "awaiting_approval") else 1


def cmd_restore_drill(args: argparse.Namespace) -> int:
    from ops_autopilot.restore_drill import run_restore_drill, list_drills
    if args.list:
        drills = list_drills(limit=args.limit)
        _print({"drills": drills, "count": len(drills)})
        return 0
    result = run_restore_drill(
        backup_id=args.backup_id,
        approve_destructive=bool(args.approve_destructive),
        note=args.note or "ops restore-drill",
    )
    _print(result)
    return 0 if result.get("ok") else 1


def cmd_anomaly_scan(args: argparse.Namespace) -> int:
    from ops_autopilot.anomalies import detect
    _print(detect(persist=not args.no_persist, raise_incidents=not args.no_incidents))
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

    sub.add_parser("health")

    inc = sub.add_parser("incident")
    inc_sub = inc.add_subparsers(dest="inc_cmd", required=True)
    il = inc_sub.add_parser("list")
    il.add_argument("--status", default=None)
    il.add_argument("--limit", type=int, default=50)
    ish = inc_sub.add_parser("show")
    ish.add_argument("incident_id")
    icl = inc_sub.add_parser("close")
    icl.add_argument("incident_id")
    icl.add_argument("--message", default=None)

    # also accept `ops incidents` as alias via main argv rewrite

    rb = sub.add_parser("runbook")
    rb_sub = rb.add_subparsers(dest="rb_cmd", required=True)
    rb_sub.add_parser("list")
    rbr = rb_sub.add_parser("run")
    rbr.add_argument("runbook_id")
    rbr.add_argument("--apply", action="store_true")
    rbr.add_argument("--dry-run", action="store_true")
    rbr.add_argument("--allow-high-risk", action="store_true")

    rd = sub.add_parser("restore-drill")
    rd.add_argument("--list", action="store_true")
    rd.add_argument("--backup-id", default=None)
    rd.add_argument("--approve-destructive", action="store_true")
    rd.add_argument("--note", default=None)
    rd.add_argument("--limit", type=int, default=20)

    an = sub.add_parser("anomaly-scan")
    an.add_argument("--no-persist", action="store_true")
    an.add_argument("--no-incidents", action="store_true")

    return p


def main(argv: list[str] | None = None) -> int:
    argv = list(argv) if argv is not None else sys.argv[1:]
    # aliases
    if argv and argv[0] == "incidents":
        argv = ["incident", "list", *argv[1:]]
    if argv and argv[0] == "runbooks":
        argv = ["runbook", "list", *argv[1:]]

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
    if args.cmd == "health":
        return cmd_health(args)
    if args.cmd == "incident":
        if args.inc_cmd == "list":
            return cmd_incident_list(args)
        if args.inc_cmd == "show":
            return cmd_incident_show(args)
        if args.inc_cmd == "close":
            return cmd_incident_close(args)
    if args.cmd == "runbook":
        if args.rb_cmd == "list":
            return cmd_runbook_list(args)
        if args.rb_cmd == "run":
            return cmd_runbook_run(args)
    if args.cmd == "restore-drill":
        return cmd_restore_drill(args)
    if args.cmd == "anomaly-scan":
        return cmd_anomaly_scan(args)
    parser.print_help()
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
