#!/usr/bin/env python3
"""Restore manager — verify + restore with safety backup-before-restore."""
from __future__ import annotations

import json
import shutil
import sys
import tarfile
from pathlib import Path
from typing import Any, Optional

_HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(_HERE.parent))

from ops.backups import create as backup_create, inspect, list_backups, verify  # noqa: E402
from ops.integrity import integrity_check, quick_check  # noqa: E402
from ops.maintenance import enter as maint_enter, exit_maintenance  # noqa: E402
from ops.paths import (  # noqa: E402
    acquire_lock,
    backups_dir,
    config_dir,
    db_path,
    load_ini,
    release_lock,
    share_config_dir,
)


def list_restorable() -> list[dict[str, Any]]:
    return list_backups()


def verify_backup(backup_id: str) -> dict[str, Any]:
    return verify(backup_id)


def restore(backup_id: str, *, dry_run: bool = False, skip_safety: bool = False) -> dict[str, Any]:
    cfg = load_ini("backup.ini")
    before = cfg.getboolean("backup", "before_restore", fallback=True)

    acquire_lock("restore", operation_id=f"restore.{backup_id}")
    steps: list[str] = []
    try:
        v = verify(backup_id)
        steps.append("verify")
        if not v.get("ok"):
            return {"ok": False, "error": "backup verify failed", "verify": v, "steps": steps}

        info = inspect(backup_id)
        src = Path(info["path"])
        src_db = src / "agentbox.db"
        if not src_db.is_file():
            return {"ok": False, "error": "backup has no agentbox.db", "steps": steps}

        if dry_run:
            return {
                "ok": True,
                "dry_run": True,
                "backup_id": backup_id,
                "would_restore_db": str(src_db),
                "target_db": str(db_path()),
                "steps": steps + ["dry_run_ok"],
            }

        maint_enter(reason=f"restore {backup_id}", mode="recovery")
        steps.append("maintenance")

        safety = None
        if before and not skip_safety:
            safety = backup_create(note=f"pre-restore safety before {backup_id}", label="pre_restore")
            steps.append(f"safety_backup:{safety['backup_id']}")

        # stop is caller's responsibility for full sequence; here we swap files
        target = db_path()
        target.parent.mkdir(parents=True, exist_ok=True)
        # remove WAL/SHM beside live db
        for suffix in ("-wal", "-shm"):
            (Path(str(target) + suffix)).unlink(missing_ok=True)
        shutil.copy2(src_db, target)
        steps.append("db_restored")

        cfg_tar = src / "config.tar.gz"
        if cfg_tar.is_file():
            from ops.paths import data_home, config_dir as cfg_home
            # Extract into temp then copy known trees
            import tempfile
            with tempfile.TemporaryDirectory(prefix="ab5-restore-cfg-") as td:
                with tarfile.open(cfg_tar, "r:gz") as tar:
                    tar.extractall(path=td)
                td_path = Path(td)
                # share config/
                src_share = td_path / "config"
                if src_share.is_dir():
                    dest_share = data_home() / "config"
                    dest_share.mkdir(parents=True, exist_ok=True)
                    for f in src_share.iterdir():
                        if f.is_file():
                            shutil.copy2(f, dest_share / f.name)
                # ~/.config/agentbox-v5
                src_user = td_path / "agentbox-v5"
                if src_user.is_dir():
                    dest_user = cfg_home()
                    dest_user.mkdir(parents=True, exist_ok=True)
                    for f in src_user.iterdir():
                        if f.is_file() and f.name != "admin.token":
                            # do not overwrite secrets token from backup blindly if named differently
                            if f.name == "secrets":
                                continue
                            shutil.copy2(f, dest_user / f.name)
            steps.append("config_extracted")

        qc = quick_check(str(target))
        ic = integrity_check(str(target), full=True)
        steps.append("integrity")
        if not qc.get("ok") or not ic.get("ok"):
            return {
                "ok": False,
                "error": "post-restore integrity failed",
                "quick_check": qc,
                "integrity": ic,
                "safety_backup": safety,
                "steps": steps,
            }

        exit_maintenance()
        steps.append("maintenance_exit")
        return {
            "ok": True,
            "backup_id": backup_id,
            "safety_backup": safety["backup_id"] if safety else None,
            "quick_check": qc,
            "integrity": ic,
            "steps": steps,
        }
    finally:
        release_lock("restore")


def main(argv: Optional[list[str]] = None) -> int:
    argv = list(argv or sys.argv[1:])
    if not argv:
        print("usage: restore.py list|verify ID|ID [--dry-run]", file=sys.stderr)
        return 2
    cmd = argv[0]
    if cmd == "list":
        print(json.dumps(list_restorable(), indent=2))
        return 0
    if cmd == "verify":
        out = verify_backup(argv[1])
        print(json.dumps(out, indent=2))
        return 0 if out.get("ok") else 1
    # restore BACKUP_ID
    bid = cmd
    dry = "--dry-run" in argv
    out = restore(bid, dry_run=dry)
    print(json.dumps(out, indent=2))
    return 0 if out.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
