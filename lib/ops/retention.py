#!/usr/bin/env python3
"""Retention — prune old logs, metrics, events, artifacts by config."""
from __future__ import annotations

import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Optional

_HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(_HERE.parent))

from ops.paths import data_home, load_ini, logs_dir  # noqa: E402
from storage import db as dbmod  # noqa: E402


def _cutoff(days: int) -> str:
    dt = datetime.now(timezone.utc) - timedelta(days=days)
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


def prune(dry_run: bool = False) -> dict[str, Any]:
    cfg = load_ini("backup.ini")
    logs_days = cfg.getint("retention", "logs_days", fallback=30)
    metrics_days = cfg.getint("retention", "metrics_days", fallback=30)
    events_days = cfg.getint("retention", "events_days", fallback=180)
    art_days = cfg.getint("retention", "task_artifacts_days", fallback=90)

    stats: dict[str, Any] = {"dry_run": dry_run}

    # DB events / metrics
    with dbmod.connect() as conn:
        ec = conn.execute(
            "SELECT COUNT(*) c FROM events WHERE ts < ?", (_cutoff(events_days),)
        ).fetchone()["c"]
        mc = conn.execute(
            "SELECT COUNT(*) c FROM metrics WHERE created_at < ?", (_cutoff(metrics_days),)
        ).fetchone()["c"]
        stats["events_old"] = ec
        stats["metrics_old"] = mc
        if not dry_run:
            conn.execute("DELETE FROM events WHERE ts < ?", (_cutoff(events_days),))
            conn.execute("DELETE FROM metrics WHERE created_at < ?", (_cutoff(metrics_days),))
            conn.commit()

    # log files by mtime
    removed_logs = []
    cutoff_ts = (datetime.now(timezone.utc) - timedelta(days=logs_days)).timestamp()
    for f in logs_dir().rglob("*"):
        if f.is_file() and f.stat().st_mtime < cutoff_ts:
            removed_logs.append(str(f))
            if not dry_run:
                f.unlink(missing_ok=True)
    stats["logs_removed"] = removed_logs if dry_run else len(removed_logs)

    # artifacts without pinned
    art_removed = 0
    with dbmod.connect() as conn:
        rows = conn.execute(
            "SELECT id, path, metadata_json, created_at FROM artifacts WHERE created_at < ?",
            (_cutoff(art_days),),
        ).fetchall()
        for r in rows:
            try:
                meta = json.loads(r["metadata_json"] or "{}")
            except Exception:
                meta = {}
            if meta.get("pinned"):
                continue
            art_removed += 1
            if not dry_run:
                p = Path(r["path"])
                if p.is_file():
                    p.unlink(missing_ok=True)
                conn.execute("DELETE FROM artifacts WHERE id=?", (r["id"],))
        if not dry_run:
            conn.commit()
    stats["artifacts_pruned"] = art_removed
    stats["ok"] = True
    return stats


def rotate_logs() -> dict[str, Any]:
    cfg = load_ini("backup.ini")
    max_mb = cfg.getint("logs", "max_size_mb", fallback=50)
    keep = cfg.getint("logs", "keep_files", fallback=10)
    rotated = []
    for f in logs_dir().glob("*.log"):
        if f.stat().st_size > max_mb * 1024 * 1024:
            ts = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
            dest = f.with_suffix(f".log.{ts}")
            f.rename(dest)
            rotated.append(str(dest))
            f.touch()
        # prune old rotations
        siblings = sorted(logs_dir().glob(f.name + ".*"), reverse=True)
        for old in siblings[keep:]:
            old.unlink(missing_ok=True)
    return {"ok": True, "rotated": rotated}


def main(argv: Optional[list[str]] = None) -> int:
    argv = list(argv or sys.argv[1:])
    cmd = argv[0] if argv else "prune"
    dry = "--dry-run" in argv
    if cmd == "prune":
        print(json.dumps(prune(dry_run=dry), indent=2))
    elif cmd == "rotate-logs":
        print(json.dumps(rotate_logs(), indent=2))
    else:
        print("usage: retention.py prune|rotate-logs [--dry-run]", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
