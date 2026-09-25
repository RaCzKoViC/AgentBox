"""Health registry + composite score (v5.6.2)."""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

_HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(_HERE.parent))

from storage import db as dbmod  # noqa: E402
from ops_autopilot import store  # noqa: E402


def evaluate(*, persist: bool = True) -> dict[str, Any]:
    from ops.diagnostics import doctor
    from ops_autopilot.forecast import forecast
    from ops.lifecycle import status as life_status

    doc = doctor()
    fc = forecast()
    life = life_status()
    active = [
        i
        for i in store.list_incidents(limit=100)
        if i.get("status") in ("open", "diagnosing", "mitigating", "monitoring", "escalated")
    ]
    try:
        from api.deps import system_stats
        stats = system_stats() or {}
    except Exception:
        stats = {}

    components: dict[str, dict[str, Any]] = {}

    def set_c(name: str, status: str, detail: Any = None, weight: float = 1.0):
        components[name] = {"status": status, "detail": detail, "weight": weight}

    web = life.get("web") or {}
    daemon = life.get("daemon") or {}
    set_c("control_plane", "healthy" if daemon.get("running") else "degraded", daemon)
    set_c("rest_api", "healthy" if web.get("running") else "failed", web, weight=1.5)

    failed = set(doc.get("failed") or [])
    set_c("sqlite", "healthy" if doc.get("ok") else "failed", {"failed": list(failed)}, weight=1.5)

    try:
        from distributed.registry import list_workers
        workers = list_workers()
        bad = [w for w in workers if w.get("status") in ("error", "unhealthy")]
        set_c("workers", "degraded" if bad else "healthy", {"bad": len(bad), "total": len(workers)})
    except Exception as e:
        set_c("workers", "unknown", {"error": str(e)})

    set_c("providers", "healthy", {"note": "no active probe"})

    res = fc.get("resources") or {}
    age = res.get("backup_age_hours")
    if age is None or float(age) >= 48:
        set_c("backups", "degraded", {"age_hours": age})
    else:
        set_c("backups", "healthy", {"age_hours": age})

    disk = float(res.get("disk_percent") or stats.get("disk_percent") or 0)
    if disk >= 90:
        set_c("disk", "failed", {"percent": disk}, weight=1.5)
    elif disk >= 80:
        set_c("disk", "degraded", {"percent": disk})
    else:
        set_c("disk", "healthy", {"percent": disk})

    mem = float(stats.get("memory_percent") or 0)
    if mem >= 95:
        set_c("memory", "failed", {"percent": mem})
    elif mem >= 85:
        set_c("memory", "degraded", {"percent": mem})
    else:
        set_c("memory", "healthy", {"percent": mem})

    cpu = float(stats.get("cpu_percent") or 0)
    set_c("cpu", "degraded" if cpu >= 95 else "healthy", {"percent": cpu})

    score = 100.0
    failed_n = degraded_n = crit = 0
    for c in components.values():
        w = float(c.get("weight") or 1.0)
        if c["status"] == "failed":
            failed_n += 1
            score -= 20 * w
        elif c["status"] == "degraded":
            degraded_n += 1
            score -= 8 * w
        elif c["status"] == "unknown":
            score -= 3 * w

    for inc in active:
        sev = inc.get("severity") or "SEV3"
        if sev == "SEV1":
            crit += 1
            score -= 25
        elif sev == "SEV2":
            score -= 12
        else:
            score -= 5

    score = max(0, min(100, int(round(score))))
    if failed_n or crit:
        status = "critical" if (crit or failed_n >= 2) else "degraded"
        if failed_n:
            score = min(score, 50)
        if crit:
            score = min(score, 40)
    elif degraded_n or (fc.get("level") in ("warn", "warning", "critical")):
        status = "degraded"
    else:
        status = "healthy"

    out = {
        "ok": status == "healthy",
        "score": score,
        "status": status,
        "summary": {
            "critical_incidents": crit,
            "failed_components": failed_n,
            "degraded_components": degraded_n,
            "open_incidents": len(active),
        },
        "components": components,
        "doctor": {"health": doc.get("health"), "ok": doc.get("ok"), "failed": doc.get("failed")},
        "forecast_level": fc.get("level"),
        "version": _platform_version(),
    }
    if persist:
        with dbmod.connect() as conn:
            store.ensure_schema(conn)
            store.insert_health_sample(conn, {"score": score, "status": status, "components": components})
            conn.commit()
    return out


def _platform_version() -> str:
    try:
        from ops.paths import read_version
        return read_version()
    except Exception:
        return "5.6.3"
