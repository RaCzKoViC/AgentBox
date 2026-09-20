"""Local worker health probe."""
from __future__ import annotations

from typing import Any

from . import local_store


def snapshot() -> dict[str, Any]:
    out: dict[str, Any] = {
        "health": "healthy",
        "cpu_percent": 0.0,
        "memory_percent": 0.0,
        "disk_percent": 0.0,
        "load1": 0.0,
        "active_tasks": 0,
    }
    try:
        import psutil
        out["cpu_percent"] = float(psutil.cpu_percent(interval=0.05))
        out["memory_percent"] = float(psutil.virtual_memory().percent)
        out["disk_percent"] = float(psutil.disk_usage(str(local_store.root())).percent)
        out["load1"] = float(psutil.getloadavg()[0]) if hasattr(psutil, "getloadavg") else 0.0
    except Exception:
        pass
    st = local_store.load_state()
    out["active_tasks"] = int(st.get("active_tasks") or 0)
    out["worker_id"] = st.get("worker_id")
    out["status"] = st.get("status", "unknown")
    return out
