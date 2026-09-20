"""Auto cleanup — logs, old artifacts, orphan PIDs (dry-run default)."""
from __future__ import annotations

import sys
from typing import Any

_HERE = __import__("pathlib").Path(__file__).resolve().parent
sys.path.insert(0, str(_HERE.parent))


def cleanup(*, dry_run: bool = True, include_pids: bool = True, include_logs: bool = True) -> dict[str, Any]:
    from ops_autopilot.playbooks import run_playbook

    results = {}
    if include_pids:
        results["clear_stale_pids"] = run_playbook(
            "clear_stale_pids", dry_run=dry_run, triggered_by="cleanup"
        )
    if include_logs:
        results["prune_old_logs"] = run_playbook(
            "prune_old_logs", dry_run=dry_run, triggered_by="cleanup"
        )
    ok = all(r.get("status") in ("passed", "awaiting_approval") for r in results.values())
    return {"ok": ok, "dry_run": dry_run, "results": results}
