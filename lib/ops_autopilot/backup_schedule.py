"""Smart backup scheduling — threshold + interval heuristics."""
from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

_HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(_HERE.parent))

from ops.paths import load_ini  # noqa: E402

DEFAULT_INTERVAL_HOURS = 24
MIN_INTERVAL_HOURS = 6


def _latest_backup_age_hours() -> Optional[float]:
    try:
        from ops.backups import list_backups
        backups = list_backups()
    except Exception:
        return None
    if not backups:
        return None
    b0 = backups[0]
    ts = b0.get("created_at") or b0.get("timestamp")
    if ts:
        try:
            dt = datetime.fromisoformat(str(ts).replace("Z", "+00:00"))
            return (datetime.now(timezone.utc) - dt).total_seconds() / 3600
        except Exception:
            pass
    path = b0.get("path")
    if path and Path(path).exists():
        import time
        return (time.time() - Path(path).stat().st_mtime) / 3600
    return None


def should_backup() -> dict[str, Any]:
    cfg = load_ini("backup.ini")
    interval = cfg.getint("schedule", "interval_hours", fallback=DEFAULT_INTERVAL_HOURS)
    interval = max(interval, MIN_INTERVAL_HOURS)

    age = _latest_backup_age_hours()
    reasons = []
    needed = False
    if age is None:
        needed = True
        reasons.append("no_existing_backup")
    elif age >= interval:
        needed = True
        reasons.append(f"age_{age:.1f}h_gte_interval_{interval}h")

    # also backup if forecast says critical disk is NOT the issue but DB growing — skip if disk critical
    try:
        from ops_autopilot.forecast import forecast
        fc = forecast()
        if any(s["code"] == "disk_crit" for s in fc.get("signals", [])):
            # still allow if no backup at all
            if age is not None:
                needed = False
                reasons.append("suppressed_disk_crit")
        elif any(s["code"] in ("db_size_warn", "db_size_crit") for s in fc.get("signals", [])):
            if age is None or age >= MIN_INTERVAL_HOURS:
                needed = True
                reasons.append("db_growth_signal")
    except Exception:
        pass

    return {
        "needed": needed,
        "age_hours": round(age, 2) if age is not None else None,
        "interval_hours": interval,
        "reasons": reasons,
    }


def create_smart_backup(note: str = "smart_backup") -> dict[str, Any]:
    from ops.backups import create
    return create(note=note, label="ops_autopilot")


def schedule_status() -> dict[str, Any]:
    decision = should_backup()
    try:
        from ops.backups import list_backups
        backups = list_backups()
        count = len(backups)
        latest = backups[0] if backups else None
    except Exception:
        count = 0
        latest = None
    return {"decision": decision, "backup_count": count, "latest": latest}
