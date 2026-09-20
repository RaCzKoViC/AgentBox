"""Upgrade readiness analysis + maintenance planning."""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Any, Optional

_HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(_HERE.parent))

from storage import db as dbmod  # noqa: E402
from ops_autopilot import store  # noqa: E402
from ops.paths import read_version  # noqa: E402


def upgrade_readiness(target_version: Optional[str] = None) -> dict[str, Any]:
    from ops.diagnostics import doctor
    from ops_autopilot.forecast import forecast
    from ops_autopilot.drift import detect_all
    from ops.migrations import status as mig_status
    from ops.lifecycle import status as life_status
    from ops.backups import list_backups

    current = read_version()
    target = target_version or "5.6.0"
    doc = doctor()
    fc = forecast()
    drift = detect_all(persist=False)
    mig = mig_status()
    life = life_status()
    backups = []
    try:
        backups = list_backups()
    except Exception:
        pass

    checks = []

    def add(name: str, ok: bool, detail: Any = None):
        checks.append({"name": name, "ok": ok, "detail": detail})

    add("doctor_healthy", doc.get("ok", False), doc.get("health"))
    add("no_critical_forecast", fc.get("level") != "critical", fc.get("level"))
    add("no_pending_migrations", len(mig.get("pending") or []) == 0, mig.get("pending"))
    add("has_backup", len(backups) > 0, len(backups))
    add("web_running", bool((life.get("web") or {}).get("running")), life.get("web"))
    add("no_config_drift", not drift.get("drifted"), {"drifted": drift.get("drifted")})

    blockers = [c for c in checks if not c["ok"]]
    ready = len(blockers) == 0
    return {
        "ok": ready,
        "ready": ready,
        "current_version": current,
        "target_version": target,
        "checks": checks,
        "blockers": [c["name"] for c in blockers],
        "recommendation": "ready_to_upgrade" if ready else "resolve_blockers_first",
    }


def plan_maintenance(*, title: Optional[str] = None) -> dict[str, Any]:
    from ops_autopilot.forecast import forecast
    from ops_autopilot.remediation import scan

    fc = forecast()
    sc = scan(dry_run=True)
    actions = []
    for p in sc.get("proposals") or []:
        actions.append({
            "playbook_id": p["playbook_id"],
            "risk_level": p.get("risk_level"),
            "reason": p.get("reason"),
            "auto": p.get("auto", False),
        })
    for hint in fc.get("capacity_hints") or []:
        actions.append({"type": "capacity_hint", "message": hint, "risk_level": "LOW"})

    priority = "low"
    if fc.get("level") == "critical":
        priority = "high"
    elif fc.get("level") == "warn" or actions:
        priority = "medium"

    plan_id = dbmod.new_id("mplan_")
    now = dbmod.utc_now()
    row = {
        "id": plan_id,
        "title": title or f"Maintenance plan {now}",
        "status": "draft",
        "priority": priority,
        "actions": actions,
        "forecast": {
            "level": fc.get("level"),
            "resources": fc.get("resources"),
            "signals": fc.get("signals"),
        },
        "created_at": now,
        "updated_at": now,
    }
    with dbmod.connect() as conn:
        store.ensure_schema(conn)
        store.insert_maintenance_plan(conn, row)
        conn.commit()
    return {"ok": True, "plan": {**row, "id": plan_id}}
