"""Restore drills — create backup, verify, dry-restore; never destructive (v5.6.2)."""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Any, Optional

_HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(_HERE.parent))

from storage import db as dbmod  # noqa: E402
from ops_autopilot import store  # noqa: E402


def run_restore_drill(
    *,
    backup_id: Optional[str] = None,
    approve_destructive: bool = False,
    note: str = "ops restore-drill",
) -> dict[str, Any]:
    from ops.backups import create, verify, list_backups

    steps: list[dict[str, Any]] = []
    created = None
    if not backup_id:
        created = create(note=note, label="restore_drill")
        backup_id = created.get("backup_id") or created.get("id")
        steps.append({"step": "create_backup", "ok": bool(backup_id), "backup": created})
    else:
        steps.append({"step": "reuse_backup", "ok": True, "backup_id": backup_id})

    if not backup_id:
        out = {
            "ok": False,
            "result": "FAIL",
            "backup_id": None,
            "steps": steps,
            "notes": "backup create failed",
            "destructive": False,
            "verify": {},
            "dry_restore": {},
        }
        _persist(out)
        return out

    v = verify(backup_id)
    steps.append({"step": "verify_backup", "ok": bool(v.get("ok")), "verify": v})

    dry_restore: dict[str, Any]
    try:
        from ops.restore import restore as restore_fn

        dry_restore = restore_fn(backup_id, dry_run=True)
        steps.append({"step": "dry_restore", "ok": bool(dry_restore.get("ok", True)), "result": dry_restore})
    except Exception as e:
        dry_restore = {"ok": False, "error": str(e), "dry_run": True}
        steps.append({"step": "dry_restore", "ok": False, "error": str(e)})

    destructive_result = None
    if approve_destructive:
        destructive_result = {
            "ok": False,
            "blocked": True,
            "message": "Destructive restore requires remediate restore_backup with approval; drill refuses overwrite",
        }
        steps.append({"step": "destructive_restore", "ok": False, "blocked": True})

    verify_ok = bool(v.get("ok"))
    dry_ok = bool(dry_restore.get("ok", True))
    if verify_ok and dry_ok:
        result = "PASS"
    elif verify_ok or dry_ok:
        result = "WARN"
    else:
        result = "FAIL"

    out = {
        "ok": result in ("PASS", "WARN"),
        "result": result,
        "backup_id": backup_id,
        "verify": v,
        "dry_restore": dry_restore,
        "destructive": False,
        "destructive_result": destructive_result,
        "steps": steps,
        "notes": note,
        "backup_count": len(list_backups()),
    }
    _persist(out)
    return out


def _persist(out: dict[str, Any]) -> None:
    rid = dbmod.new_id("drill_")
    with dbmod.connect() as conn:
        store.ensure_schema(conn)
        store.insert_restore_drill(
            conn,
            {
                "id": rid,
                "backup_id": out.get("backup_id"),
                "result": out.get("result", "FAIL"),
                "verify": out.get("verify") or {},
                "dry_restore": out.get("dry_restore") or {},
                "notes": out.get("notes", ""),
                "destructive": bool(out.get("destructive")),
            },
        )
        conn.commit()
    out["drill_id"] = rid


def list_drills(limit: int = 20) -> list[dict[str, Any]]:
    return store.list_restore_drills(limit=limit)
