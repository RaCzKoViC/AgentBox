#!/usr/bin/env python3
"""Upgrade / rollback stubs that use backups."""
from __future__ import annotations

import json
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

_HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(_HERE.parent))

from ops.backups import create as backup_create, list_backups  # noqa: E402
from ops.migrations import run as migrate_run, status as mig_status  # noqa: E402
from ops.paths import data_home, read_version  # noqa: E402

RELEASES = Path("/workspace/agentbox-releases")


def check() -> dict[str, Any]:
    return {
        "current": read_version(),
        "target": "5.0.0",
        "migrations": mig_status(),
        "upgrade_available": read_version() != "5.0.0",
    }


def plan() -> dict[str, Any]:
    return {
        "steps": [
            "preflight (deploy-guard + integrity)",
            "backup create",
            "maintenance enter",
            "migrate",
            "install release files",
            "selftest",
            "health probe",
            "maintenance exit",
        ],
        "current": read_version(),
        "note": "stub — apply runs backup + migrate only",
    }


def apply() -> dict[str, Any]:
    b = backup_create(note="pre-upgrade", label="pre_upgrade")
    m = migrate_run(backup_first=False)
    # record release pointer
    RELEASES.mkdir(parents=True, exist_ok=True)
    cur = RELEASES / "current"
    target = RELEASES / "v5.0.0"
    target.mkdir(exist_ok=True)
    (target / "VERSION").write_text("5.0.0\n", encoding="utf-8")
    (target / "manifest.json").write_text(
        json.dumps({
            "version": "5.0.0",
            "build": "stable",
            "schema_version": 12,
            "created_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "pre_backup": b["backup_id"],
        }, indent=2) + "\n",
        encoding="utf-8",
    )
    if cur.is_symlink() or cur.exists():
        cur.unlink()
    cur.symlink_to(target)
    return {"ok": m.get("ok"), "backup": b["backup_id"], "migrate": m, "release": str(target)}


def upgrade_status() -> dict[str, Any]:
    cur = RELEASES / "current"
    return {
        "version": read_version(),
        "release_link": str(cur.resolve()) if cur.exists() else None,
        "migrations": mig_status(),
    }


def rollback_plan() -> dict[str, Any]:
    backups = [b for b in list_backups() if not b.get("legacy")][:5]
    return {
        "steps": [
            "maintenance enter",
            "stop web/daemon (caller)",
            "restore from last pre_upgrade / pre_migrate backup",
            "integrity check",
            "start services",
        ],
        "candidate_backups": backups,
        "note": "DB downgrade only from compatible backup — never blind schema downgrade",
    }


def rollback_apply(backup_id: Optional[str] = None) -> dict[str, Any]:
    from ops.restore import restore
    if not backup_id:
        cands = [b for b in list_backups() if "pre_upgrade" in b.get("backup_id", "") or "pre_migrate" in b.get("backup_id", "")]
        if not cands:
            cands = [b for b in list_backups() if not b.get("legacy")]
        if not cands:
            return {"ok": False, "error": "no backup available for rollback"}
        backup_id = cands[0]["backup_id"]
    return restore(backup_id, dry_run=False)


def main(argv: Optional[list[str]] = None) -> int:
    argv = list(argv or sys.argv[1:])
    if not argv:
        print("usage: upgrade.py check|plan|apply|status | rollback plan|apply [ID]", file=sys.stderr)
        return 2
    cmd = argv[0]
    if cmd == "check":
        print(json.dumps(check(), indent=2))
    elif cmd == "plan":
        print(json.dumps(plan(), indent=2))
    elif cmd == "apply":
        print(json.dumps(apply(), indent=2))
    elif cmd == "status":
        print(json.dumps(upgrade_status(), indent=2))
    elif cmd == "rollback":
        sub = argv[1] if len(argv) > 1 else "plan"
        if sub == "plan":
            print(json.dumps(rollback_plan(), indent=2))
        elif sub == "apply":
            bid = argv[2] if len(argv) > 2 else None
            print(json.dumps(rollback_apply(bid), indent=2))
        else:
            return 2
    else:
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
