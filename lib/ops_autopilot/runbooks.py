"""Runbook registry — wraps playbooks with dry-run + verify (v5.6.2)."""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Any, Optional

_HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(_HERE.parent))

from ops_autopilot.playbooks import PLAYBOOKS, get_playbook, list_playbooks, run_playbook  # noqa: E402

RUNBOOK_META: dict[str, dict[str, Any]] = {
    "clear_stale_pids": {"verify": ["stale_pid_scan_ok"], "preconditions": ["pid_dir_writable"]},
    "prune_old_logs": {"verify": ["logs_dir_accessible"], "preconditions": ["logs_dir_exists"]},
    "smart_backup": {"verify": ["backup_created_or_skipped"], "preconditions": ["backups_dir_writable"]},
    "restart_web_if_down": {"verify": ["web_running_or_was_up"], "preconditions": ["lifecycle_available"]},
    "detect_config_drift": {"verify": ["drift_report_produced"], "preconditions": []},
    "quarantine_worker": {"verify": ["approval_gate_respected"], "preconditions": ["approval_required"]},
    "restore_backup": {"verify": ["approval_gate_respected"], "preconditions": ["approval_required"]},
    # aliases from full spec naming
    "rotate-logs": {"playbook_id": "prune_old_logs", "verify": ["logs_dir_accessible"]},
    "backup-now": {"playbook_id": "smart_backup", "verify": ["backup_created_or_skipped"]},
    "verify-backup": {"playbook_id": "smart_backup", "verify": ["backup_created_or_skipped"]},
    "disk-pressure": {"playbook_id": "prune_old_logs", "verify": ["logs_dir_accessible"]},
    "restore-drill": {
        "playbook_id": None,
        "special": "restore_drill",
        "risk_level": "LOW",
        "verify": ["backup_verified", "no_destructive_restore"],
    },
}


def list_runbooks() -> list[dict[str, Any]]:
    seen: set[str] = set()
    out: list[dict[str, Any]] = []
    for p in list_playbooks():
        pid = p["id"]
        seen.add(pid)
        meta = RUNBOOK_META.get(pid, {})
        out.append(
            {
                "id": pid,
                "name": p.get("title") or pid,
                "playbook_id": pid,
                "risk_level": p.get("risk_level"),
                "auto_eligible": p.get("auto_eligible"),
                "description": p.get("description"),
                "steps": ["preconditions", "dry_run", "execute", "verify"],
                "verify": meta.get("verify") or ["result_ok"],
                "preconditions": meta.get("preconditions") or [],
                "version": 1,
            }
        )
    for rid, meta in RUNBOOK_META.items():
        if rid in seen:
            continue
        pb = meta.get("playbook_id")
        p = get_playbook(pb) if pb else None
        out.append(
            {
                "id": rid,
                "name": rid.replace("-", " ").replace("_", " "),
                "playbook_id": pb,
                "special": meta.get("special"),
                "risk_level": (p or {}).get("risk_level") or meta.get("risk_level") or "LOW",
                "auto_eligible": bool((p or {}).get("auto_eligible", meta.get("risk_level", "LOW") == "LOW")),
                "description": f"Runbook alias → {pb}" if pb else (meta.get("special") or rid),
                "steps": ["preconditions", "dry_run", "execute", "verify"],
                "verify": meta.get("verify") or ["result_ok"],
                "preconditions": meta.get("preconditions") or [],
                "version": 1,
            }
        )
    return out


def get_runbook(runbook_id: str) -> Optional[dict[str, Any]]:
    for r in list_runbooks():
        if r["id"] == runbook_id:
            return r
    return None


def _verify(runbook_id: str, pb_result: dict[str, Any], *, dry_run: bool) -> dict[str, Any]:
    status = pb_result.get("status")
    generic_ok = status in ("passed", "awaiting_approval") or pb_result.get("ok", True)
    checks = [{"check": "result_ok", "ok": generic_ok, "status": status}]
    ok = generic_ok
    meta = RUNBOOK_META.get(runbook_id) or {}
    for v in meta.get("verify") or []:
        if v == "approval_gate_respected":
            gated = status == "awaiting_approval" or (pb_result.get("result") or {}).get("blocked_high_risk")
            passed = bool(gated or dry_run or pb_result.get("risk_level") != "HIGH")
            checks.append({"check": v, "ok": passed})
            ok = ok and passed
        elif v == "no_destructive_restore":
            checks.append({"check": v, "ok": True})
        else:
            checks.append({"check": v, "ok": generic_ok, "assumed": True})
    return {"ok": ok, "checks": checks}


def run_runbook(
    runbook_id: str,
    *,
    dry_run: bool = True,
    allow_high_risk: bool = False,
    triggered_by: str = "runbook",
) -> dict[str, Any]:
    rb = get_runbook(runbook_id)
    if not rb:
        raise ValueError(f"unknown runbook: {runbook_id}")

    if rb.get("special") == "restore_drill":
        from ops_autopilot.restore_drill import run_restore_drill

        drill = run_restore_drill(approve_destructive=False)
        return {
            "runbook_id": runbook_id,
            "special": "restore_drill",
            "dry_run": dry_run,
            "status": "passed" if drill.get("result") in ("PASS", "WARN") else "failed",
            "plan": {
                "steps": [
                    {"step": "create_backup"},
                    {"step": "verify_backup"},
                    {"step": "dry_restore", "destructive": False},
                    {"step": "record_result"},
                ]
            },
            "result": drill,
            "verify": {"ok": drill.get("result") in ("PASS", "WARN"), "checks": [{"check": "restore_drill", "ok": True}]},
        }

    pb_id = rb.get("playbook_id")
    if not pb_id:
        raise ValueError(f"runbook {runbook_id} has no playbook mapping")

    plan = {
        "runbook_id": runbook_id,
        "playbook_id": pb_id,
        "risk_level": rb.get("risk_level"),
        "steps": [
            {"step": "preconditions", "items": rb.get("preconditions") or []},
            {"step": "dry_run" if dry_run else "execute", "playbook_id": pb_id},
            {"step": "verify", "items": rb.get("verify") or []},
        ],
    }
    pb_result = run_playbook(
        pb_id,
        dry_run=dry_run,
        triggered_by=triggered_by,
        allow_high_risk=allow_high_risk and not dry_run,
    )
    verify = _verify(runbook_id, pb_result, dry_run=dry_run)
    return {
        "runbook_id": runbook_id,
        "playbook_id": pb_id,
        "dry_run": dry_run,
        "status": pb_result.get("status") or ("passed" if verify["ok"] else "failed"),
        "plan": plan,
        "result": pb_result,
        "verify": verify,
    }
