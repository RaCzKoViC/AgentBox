"""Threshold anomaly detector → incidents (v5.6.2)."""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

_HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(_HERE.parent))

from storage import db as dbmod  # noqa: E402
from ops_autopilot import store  # noqa: E402
from ops_autopilot.incidents import open_incident  # noqa: E402

DISK_WARN, DISK_CRIT = 80.0, 90.0
MEM_WARN, MEM_CRIT = 85.0, 95.0
CPU_WARN = 90.0
DB_WARN_MB, DB_CRIT_MB = 512.0, 2048.0
LOGS_WARN_MB = 256.0
BACKUP_STALE_H = 48.0


def _sev(level: str) -> str:
    return {"critical": "SEV1", "crit": "SEV1", "error": "SEV2", "warn": "SEV3", "info": "SEV4"}.get(
        (level or "").lower(), "SEV3"
    )


def detect(*, persist: bool = True, raise_incidents: bool = True) -> dict[str, Any]:
    from ops.diagnostics import doctor
    from ops_autopilot.forecast import forecast

    doc = doctor()
    fc = forecast()
    try:
        from api.deps import system_stats
        stats = system_stats() or {}
    except Exception:
        stats = {}

    found: list[dict[str, Any]] = []

    def add(kind: str, severity: str, component: str, metric: str, value: Any, threshold: Any, title: str):
        found.append(
            {
                "kind": kind,
                "severity": severity,
                "component": component,
                "metric": metric,
                "value": value if isinstance(value, dict) else {"value": value},
                "threshold": threshold if isinstance(threshold, dict) else {"limit": threshold},
                "title": title,
            }
        )

    for name in doc.get("failed") or []:
        add("doctor_check", "SEV2", name, "doctor", {"ok": False}, {"expected": True}, f"Doctor check failed: {name}")

    for chk in doc.get("checks") or []:
        if chk.get("ok"):
            continue
        n = chk.get("name") or "unknown"
        if n in (doc.get("failed") or []):
            continue
        add("doctor_check", "SEV2", n, "doctor", {"detail": chk.get("detail")}, {"expected": True}, f"Doctor check failed: {n}")

    res = fc.get("resources") or {}
    disk = float(res.get("disk_percent") or stats.get("disk_percent") or 0)
    if disk >= DISK_CRIT:
        add("disk_pressure", "SEV1", "disk", "disk_percent", disk, DISK_CRIT, f"Disk critical {disk:.1f}%")
    elif disk >= DISK_WARN:
        add("disk_pressure", "SEV3", "disk", "disk_percent", disk, DISK_WARN, f"Disk warning {disk:.1f}%")

    db_mb = float(res.get("db_mb") or 0)
    if db_mb >= DB_CRIT_MB:
        add("db_growth", "SEV2", "sqlite", "db_mb", db_mb, DB_CRIT_MB, f"DB size critical {db_mb:.1f}MB")
    elif db_mb >= DB_WARN_MB:
        add("db_growth", "SEV3", "sqlite", "db_mb", db_mb, DB_WARN_MB, f"DB size warning {db_mb:.1f}MB")

    logs_mb = float(res.get("logs_mb") or 0)
    if logs_mb >= LOGS_WARN_MB:
        add("log_growth", "SEV3", "logs", "logs_mb", logs_mb, LOGS_WARN_MB, f"Logs volume {logs_mb:.1f}MB")

    age_h = res.get("backup_age_hours")
    if age_h is not None and float(age_h) >= BACKUP_STALE_H:
        add("backup_stale", "SEV3", "backups", "backup_age_hours", float(age_h), BACKUP_STALE_H, f"Backup stale ({float(age_h):.1f}h)")

    mem = float(stats.get("memory_percent") or 0)
    if mem >= MEM_CRIT:
        add("memory_pressure", "SEV1", "memory", "memory_percent", mem, MEM_CRIT, f"Memory critical {mem:.1f}%")
    elif mem >= MEM_WARN:
        add("memory_pressure", "SEV3", "memory", "memory_percent", mem, MEM_WARN, f"Memory warning {mem:.1f}%")

    cpu = float(stats.get("cpu_percent") or 0)
    if cpu >= CPU_WARN:
        add("cpu_pressure", "SEV3", "cpu", "cpu_percent", cpu, CPU_WARN, f"CPU high {cpu:.1f}%")

    for sig in fc.get("signals") or []:
        code = sig.get("code") or "signal"
        if any(code in a["kind"] or a["kind"] in code for a in found):
            continue
        add(code, _sev(sig.get("level")), "forecast", code, sig.get("metric"), {"level": sig.get("level")}, sig.get("message") or code)

    recorded = []
    touched = 0
    for a in found:
        incident_id = None
        if raise_incidents and a["severity"] in ("SEV1", "SEV2", "SEV3"):
            inc = open_incident(
                title=a["title"],
                severity=a["severity"],
                component=a["component"],
                source="anomaly",
                kind=a["kind"],
                symptoms=[a["title"]],
                evidence={"metric": a["metric"], "value": a["value"], "threshold": a["threshold"]},
                suspected_causes=[f"threshold:{a['kind']}"],
            )
            incident_id = inc.get("id")
            touched += 1
        if persist:
            aid = dbmod.new_id("anom_")
            with dbmod.connect() as conn:
                store.ensure_schema(conn)
                store.insert_anomaly(
                    conn,
                    {
                        "id": aid,
                        "kind": a["kind"],
                        "severity": a["severity"],
                        "component": a["component"],
                        "metric": a["metric"],
                        "value": a["value"],
                        "threshold": a["threshold"],
                        "incident_id": incident_id,
                        "status": "open",
                    },
                )
                conn.commit()
            recorded.append({**a, "id": aid, "incident_id": incident_id})
        else:
            recorded.append({**a, "incident_id": incident_id})

    return {
        "ok": True,
        "count": len(recorded),
        "anomalies": recorded,
        "incidents_touched": touched,
        "doctor_health": doc.get("health"),
        "forecast_level": fc.get("level"),
    }
