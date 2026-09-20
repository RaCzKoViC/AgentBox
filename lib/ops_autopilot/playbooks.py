"""Self-healing playbooks — low-risk auto, high-risk needs approval."""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Any, Callable, Optional

_HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(_HERE.parent))

from storage import db as dbmod  # noqa: E402
from ops_autopilot import store  # noqa: E402

PlaybookFn = Callable[[bool], dict[str, Any]]

# Risk: LOW = auto-eligible; HIGH = requires approval
PLAYBOOKS: dict[str, dict[str, Any]] = {}


def _register(pid: str, *, title: str, risk: str, description: str, fn: PlaybookFn) -> None:
    PLAYBOOKS[pid] = {
        "id": pid,
        "title": title,
        "risk_level": risk,
        "description": description,
        "fn": fn,
    }


def _pb_clear_stale_pids(dry_run: bool = True) -> dict[str, Any]:
    from ops.recovery import scan_stale_pids
    from pathlib import Path as _P

    findings = scan_stale_pids()
    if dry_run:
        return {
            "ok": True,
            "dry_run": True,
            "stale_pids": findings,
            "count": len(findings),
            "action": "would_remove_stale_pid_files",
        }
    cleared = []
    for item in findings:
        path = item.get("path") or item.get("file") or item.get("pid_file")
        if path:
            _P(path).unlink(missing_ok=True)
            cleared.append(path)
        elif item.get("pid_file"):
            _P(item["pid_file"]).unlink(missing_ok=True)
            cleared.append(item["pid_file"])
    # re-scan to confirm
    remaining = scan_stale_pids()
    return {
        "ok": True,
        "dry_run": False,
        "stale_before": len(findings),
        "cleared": cleared,
        "remaining": len(remaining),
    }


def _pb_prune_old_logs(dry_run: bool = True) -> dict[str, Any]:
    from ops.retention import prune
    from ops.paths import logs_dir
    from datetime import datetime, timedelta, timezone

    # Prefer short-lived log files (>7d) for autopilot; fall back to retention config
    removed = []
    cutoff = (datetime.now(timezone.utc) - timedelta(days=7)).timestamp()
    for f in logs_dir().rglob("*"):
        if f.is_file() and f.stat().st_mtime < cutoff:
            removed.append(str(f))
            if not dry_run:
                f.unlink(missing_ok=True)
    # Also run retention prune for DB events/metrics (respects config days)
    ret = prune(dry_run=dry_run)
    return {
        "ok": True,
        "dry_run": dry_run,
        "logs_pruned": removed if dry_run else len(removed),
        "logs_count": len(removed),
        "retention": ret,
    }


def _pb_smart_backup(dry_run: bool = True) -> dict[str, Any]:
    from ops_autopilot.backup_schedule import should_backup, create_smart_backup

    decision = should_backup()
    if dry_run:
        return {"ok": True, "dry_run": True, "decision": decision, "action": "would_backup" if decision.get("needed") else "skip"}
    if not decision.get("needed"):
        return {"ok": True, "dry_run": False, "skipped": True, "decision": decision}
    b = create_smart_backup(note="ops-autopilot smart_backup")
    return {"ok": True, "dry_run": False, "decision": decision, "backup": b}


def _pb_restart_web_if_down(dry_run: bool = True) -> dict[str, Any]:
    from ops.lifecycle import web_status, restart

    st = web_status()
    running = bool(st.get("running"))
    if running:
        return {"ok": True, "dry_run": dry_run, "web_running": True, "action": "none", "status": st}
    if dry_run:
        return {"ok": True, "dry_run": True, "web_running": False, "action": "would_restart_web", "status": st}
    result = restart(components=["web"])
    after = web_status()
    return {
        "ok": bool(after.get("running")),
        "dry_run": False,
        "web_running_before": False,
        "action": "restart_web",
        "restart": result,
        "status_after": after,
    }


def _pb_detect_config_drift(dry_run: bool = True) -> dict[str, Any]:
    from ops_autopilot.drift import detect_all

    report = detect_all(persist=not dry_run)
    return {
        "ok": True,
        "dry_run": dry_run,
        "drifted": report.get("drifted", False),
        "scopes": report.get("scopes", {}),
        "snapshot_ids": report.get("snapshot_ids", []),
    }


def _pb_quarantine_worker(dry_run: bool = True, worker_id: str = "") -> dict[str, Any]:
    """HIGH risk — never auto-applies without approval path."""
    return {
        "ok": True,
        "dry_run": dry_run,
        "risk_level": "HIGH",
        "requires_approval": True,
        "worker_id": worker_id,
        "action": "would_quarantine" if dry_run else "blocked_without_approval",
        "message": "Use remediate with approval for quarantine_worker",
    }


def _pb_restore_backup(dry_run: bool = True, backup_id: str = "") -> dict[str, Any]:
    """HIGH risk — never auto-applies without approval."""
    return {
        "ok": True,
        "dry_run": dry_run,
        "risk_level": "HIGH",
        "requires_approval": True,
        "backup_id": backup_id,
        "action": "would_restore" if dry_run else "blocked_without_approval",
        "message": "Use remediate with approval for restore_backup",
    }


_register(
    "clear_stale_pids",
    title="Clear stale PID files",
    risk="LOW",
    description="Remove PID files whose processes are dead",
    fn=_pb_clear_stale_pids,
)
_register(
    "prune_old_logs",
    title="Prune old logs",
    risk="LOW",
    description="Delete log files older than 7 days + retention prune",
    fn=_pb_prune_old_logs,
)
_register(
    "smart_backup",
    title="Smart backup",
    risk="LOW",
    description="Create backup when schedule/thresholds say so",
    fn=_pb_smart_backup,
)
_register(
    "restart_web_if_down",
    title="Restart web if down",
    risk="LOW",
    description="Restart Control Plane web UI when not running",
    fn=_pb_restart_web_if_down,
)
_register(
    "detect_config_drift",
    title="Detect configuration drift",
    risk="LOW",
    description="Compare config/worker/provider state to baselines",
    fn=_pb_detect_config_drift,
)
_register(
    "quarantine_worker",
    title="Quarantine worker",
    risk="HIGH",
    description="Quarantine a distributed worker (requires approval)",
    fn=lambda dry_run=True: _pb_quarantine_worker(dry_run=dry_run),
)
_register(
    "restore_backup",
    title="Restore backup",
    risk="HIGH",
    description="Restore from backup (requires approval)",
    fn=lambda dry_run=True: _pb_restore_backup(dry_run=dry_run),
)


def list_playbooks() -> list[dict[str, Any]]:
    return [
        {
            "id": p["id"],
            "title": p["title"],
            "risk_level": p["risk_level"],
            "description": p["description"],
            "auto_eligible": p["risk_level"] == "LOW",
        }
        for p in PLAYBOOKS.values()
    ]


def get_playbook(playbook_id: str) -> Optional[dict[str, Any]]:
    p = PLAYBOOKS.get(playbook_id)
    if not p:
        return None
    return {
        "id": p["id"],
        "title": p["title"],
        "risk_level": p["risk_level"],
        "description": p["description"],
        "auto_eligible": p["risk_level"] == "LOW",
    }


def run_playbook(
    playbook_id: str,
    *,
    dry_run: bool = True,
    triggered_by: str = "manual",
    force: bool = False,
    allow_high_risk: bool = False,
) -> dict[str, Any]:
    p = PLAYBOOKS.get(playbook_id)
    if not p:
        raise ValueError(f"unknown playbook: {playbook_id}")

    risk = p["risk_level"]
    # HIGH risk never executes for real unless explicitly allowed (approval path)
    effective_dry = dry_run
    if risk == "HIGH" and not dry_run and not allow_high_risk:
        effective_dry = True
        blocked = True
    else:
        blocked = False

    run_id = dbmod.new_id("pbrun_")
    now = dbmod.utc_now()
    with dbmod.connect() as conn:
        store.ensure_schema(conn)
        store.insert_playbook_run(
            conn,
            {
                "id": run_id,
                "playbook_id": playbook_id,
                "status": "running",
                "dry_run": effective_dry,
                "risk_level": risk,
                "triggered_by": triggered_by,
                "started_at": now,
                "created_at": now,
            },
        )
        conn.commit()

    try:
        result = p["fn"](effective_dry)
        if blocked:
            result = {**result, "blocked_high_risk": True, "message": "HIGH risk requires approval; ran as dry-run"}
        status = "passed" if result.get("ok", True) else "failed"
        if blocked:
            status = "awaiting_approval"
        with dbmod.connect() as conn:
            store.update_playbook_run(
                conn,
                run_id,
                status=status,
                finished_at=dbmod.utc_now(),
                result=result,
                dry_run=effective_dry,
            )
            # record remediation action
            aid = dbmod.new_id("rem_")
            rem_status = "applied" if (not effective_dry and status == "passed") else (
                "awaiting_approval" if blocked or risk == "HIGH" else ("proposed" if effective_dry else "applied")
            )
            store.insert_remediation(
                conn,
                {
                    "id": aid,
                    "action_type": playbook_id,
                    "risk_level": risk,
                    "status": rem_status,
                    "dry_run": effective_dry,
                    "target": playbook_id,
                    "detail": result,
                    "playbook_run_id": run_id,
                    "applied_at": dbmod.utc_now() if rem_status == "applied" else None,
                },
            )
            conn.commit()
        return {
            "run_id": run_id,
            "playbook_id": playbook_id,
            "status": status,
            "dry_run": effective_dry,
            "risk_level": risk,
            "remediation_id": aid,
            "result": result,
        }
    except Exception as e:
        with dbmod.connect() as conn:
            store.update_playbook_run(
                conn,
                run_id,
                status="failed",
                finished_at=dbmod.utc_now(),
                error=str(e),
                result={"ok": False, "error": str(e)},
            )
            conn.commit()
        return {
            "run_id": run_id,
            "playbook_id": playbook_id,
            "status": "failed",
            "dry_run": effective_dry,
            "risk_level": risk,
            "error": str(e),
        }
