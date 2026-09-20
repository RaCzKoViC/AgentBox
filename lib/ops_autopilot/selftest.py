#!/usr/bin/env python3
"""v5.6 ops autopilot selftest."""
from __future__ import annotations

import os
import re
import sys

sys.path.insert(0, os.environ.get("AGENTBOX_V5_LIB", str(__file__.rsplit("/", 2)[0] if False else "")))
_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(_HERE))


def main() -> int:
    from ops.diagnostics import doctor
    from ops.paths import read_version
    from ops_autopilot.playbooks import list_playbooks, run_playbook
    from ops_autopilot.remediation import status, scan, remediate
    from ops_autopilot.forecast import forecast
    from ops_autopilot.drift import detect_all
    from ops_autopilot.cleanup import cleanup
    from ops_autopilot.backup_schedule import schedule_status
    from ops_autopilot.readiness import upgrade_readiness, plan_maintenance
    from ops_autopilot import store
    from storage import db as dbmod

    ver = read_version()
    assert re.match(r"^5\.\d+\.\d+", ver), ver
    doc = doctor()
    assert doc.get("ok"), doc
    assert "version" not in (doc.get("failed") or []), doc
    print("OK: doctor HEALTHY version", ver, doc.get("health"))

    pbs = list_playbooks()
    ids = {p["id"] for p in pbs}
    for need in (
        "clear_stale_pids",
        "prune_old_logs",
        "smart_backup",
        "restart_web_if_down",
        "detect_config_drift",
    ):
        assert need in ids, ids
    assert any(p["risk_level"] == "HIGH" for p in pbs)
    print("OK: playbooks", sorted(ids))

    with dbmod.connect() as conn:
        store.ensure_schema(conn)
        conn.commit()

    for pid in (
        "clear_stale_pids",
        "prune_old_logs",
        "detect_config_drift",
        "restart_web_if_down",
        "smart_backup",
    ):
        r = run_playbook(pid, dry_run=True, triggered_by="selftest")
        assert r["status"] == "passed", r
    print("OK: low-risk playbooks dry-run")

    hi = run_playbook("quarantine_worker", dry_run=False, triggered_by="selftest")
    assert hi["status"] == "awaiting_approval" or hi.get("result", {}).get("blocked_high_risk"), hi
    print("OK: high-risk blocked without approval", hi["status"])

    fc = forecast()
    assert "resources" in fc and "level" in fc, fc
    print("OK: forecast", fc["level"])

    dr = detect_all(persist=True)
    assert "scopes" in dr, dr
    print("OK: drift", "drifted" if dr.get("drifted") else "clean")

    sc = scan(dry_run=True)
    assert "proposals" in sc, sc
    print("OK: scan proposals", len(sc["proposals"]))

    rem = remediate(dry_run=True, auto_low_risk=True)
    assert rem.get("ok"), rem
    print("OK: remediate dry-run actions", len(rem.get("actions") or []))

    cl = cleanup(dry_run=True)
    assert cl.get("ok"), cl
    print("OK: cleanup dry-run")

    bs = schedule_status()
    assert "decision" in bs, bs
    print("OK: backup-schedule", bs["decision"].get("needed"))

    st = status()
    assert st.get("version") == "5.6.0", st
    print("OK: ops status")

    rd = upgrade_readiness(target_version="5.6.0")
    assert "checks" in rd, rd
    print("OK: readiness ready=", rd.get("ready"), "blockers", rd.get("blockers"))

    pl = plan_maintenance(title="selftest maintenance")
    assert pl.get("ok") and pl.get("plan", {}).get("id"), pl
    print("OK: maintenance plan", pl["plan"]["id"])

    applied = run_playbook("clear_stale_pids", dry_run=False, triggered_by="selftest")
    assert applied["status"] == "passed", applied
    print("OK: clear_stale_pids applied")

    print("RESULT: PASS")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except AssertionError as e:
        print("RESULT: FAIL", e, file=sys.stderr)
        raise
