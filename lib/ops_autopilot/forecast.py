"""Predictive maintenance / resource forecasting — simple thresholds."""
from __future__ import annotations

import shutil
import sys
from pathlib import Path
from typing import Any

_HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(_HERE.parent))

from ops.paths import data_home, db_path, logs_dir, backups_dir  # noqa: E402


# Thresholds (percent or absolute)
DISK_WARN_PCT = 80.0
DISK_CRIT_PCT = 90.0
DB_WARN_MB = 512.0
DB_CRIT_MB = 2048.0
LOGS_WARN_MB = 256.0
LOGS_CRIT_MB = 1024.0
BACKUP_STALE_HOURS = 48


def _dir_size_mb(path: Path) -> float:
    total = 0
    if not path.exists():
        return 0.0
    for f in path.rglob("*"):
        if f.is_file():
            try:
                total += f.stat().st_size
            except OSError:
                pass
    return total / (1024 * 1024)


def forecast() -> dict[str, Any]:
    usage = shutil.disk_usage(str(data_home()))
    disk_pct = (usage.used / usage.total) * 100 if usage.total else 0.0
    free_gb = usage.free / (1024 ** 3)

    dbp = db_path()
    db_mb = (dbp.stat().st_size / (1024 * 1024)) if dbp.is_file() else 0.0
    logs_mb = _dir_size_mb(logs_dir())
    backups_mb = _dir_size_mb(backups_dir())

    signals = []
    capacity_hints = []

    def add(level: str, code: str, message: str, metric: Any = None):
        signals.append({"level": level, "code": code, "message": message, "metric": metric})

    if disk_pct >= DISK_CRIT_PCT:
        add("critical", "disk_crit", f"Disk {disk_pct:.1f}% used ({free_gb:.2f}G free)", disk_pct)
        capacity_hints.append("Free disk space urgently; prune logs/artifacts or expand volume")
    elif disk_pct >= DISK_WARN_PCT:
        add("warn", "disk_warn", f"Disk {disk_pct:.1f}% used ({free_gb:.2f}G free)", disk_pct)
        capacity_hints.append("Plan disk cleanup within maintenance window")

    if db_mb >= DB_CRIT_MB:
        add("critical", "db_size_crit", f"DB size {db_mb:.1f} MB", db_mb)
        capacity_hints.append("Run retention prune / vacuum; consider archival")
    elif db_mb >= DB_WARN_MB:
        add("warn", "db_size_warn", f"DB size {db_mb:.1f} MB", db_mb)

    if logs_mb >= LOGS_CRIT_MB:
        add("critical", "logs_crit", f"Logs dir {logs_mb:.1f} MB", logs_mb)
        capacity_hints.append("Run prune_old_logs playbook")
    elif logs_mb >= LOGS_WARN_MB:
        add("warn", "logs_warn", f"Logs dir {logs_mb:.1f} MB", logs_mb)

    # backup freshness
    latest_backup_age_h = None
    try:
        from ops.backups import list_backups
        backups = list_backups()
        if backups:
            # assume created_at ISO or mtime via path
            import time
            from datetime import datetime, timezone
            b0 = backups[0]
            ts = b0.get("created_at") or b0.get("timestamp")
            if ts:
                try:
                    dt = datetime.fromisoformat(str(ts).replace("Z", "+00:00"))
                    latest_backup_age_h = (datetime.now(timezone.utc) - dt).total_seconds() / 3600
                except Exception:
                    pass
            if latest_backup_age_h is None and b0.get("path"):
                p = Path(b0["path"])
                if p.exists():
                    latest_backup_age_h = (time.time() - p.stat().st_mtime) / 3600
        else:
            add("warn", "no_backups", "No backups found")
            capacity_hints.append("Run smart_backup playbook")
    except Exception as e:
        add("warn", "backup_check_error", str(e))

    if latest_backup_age_h is not None and latest_backup_age_h > BACKUP_STALE_HOURS:
        add("warn", "backup_stale", f"Latest backup age {latest_backup_age_h:.1f}h", latest_backup_age_h)
        capacity_hints.append("Schedule smart_backup soon")

    level = "ok"
    if any(s["level"] == "critical" for s in signals):
        level = "critical"
    elif any(s["level"] == "warn" for s in signals):
        level = "warn"

    return {
        "ok": level != "critical",
        "level": level,
        "resources": {
            "disk_percent": round(disk_pct, 2),
            "disk_free_gb": round(free_gb, 2),
            "db_mb": round(db_mb, 2),
            "logs_mb": round(logs_mb, 2),
            "backups_mb": round(backups_mb, 2),
            "backup_age_hours": round(latest_backup_age_h, 2) if latest_backup_age_h is not None else None,
        },
        "signals": signals,
        "capacity_hints": capacity_hints,
        "thresholds": {
            "disk_warn_pct": DISK_WARN_PCT,
            "disk_crit_pct": DISK_CRIT_PCT,
            "db_warn_mb": DB_WARN_MB,
            "logs_warn_mb": LOGS_WARN_MB,
            "backup_stale_hours": BACKUP_STALE_HOURS,
        },
    }
