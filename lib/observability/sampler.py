#!/usr/bin/env python3
"""AgentBox v5 resource sampler — CPU/RAM/load/disk/queue (beta2). Soft-fail without psutil."""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any, Optional


def _ensure_path() -> None:
    lib = str(Path(__file__).resolve().parent.parent)
    if lib not in sys.path:
        sys.path.insert(0, lib)


def _cpu_pct_proc() -> float:
    """Best-effort CPU% from /proc/stat (two-sample)."""
    import time

    def read():
        with open("/proc/stat") as f:
            parts = f.readline().split()
        vals = [int(x) for x in parts[1:8]]
        idle = vals[3] + (vals[4] if len(vals) > 4 else 0)
        total = sum(vals)
        return idle, total

    try:
        i1, t1 = read()
        time.sleep(0.05)
        i2, t2 = read()
        di, dt = i2 - i1, t2 - t1
        if dt <= 0:
            return 0.0
        return max(0.0, min(100.0, (1.0 - di / dt) * 100.0))
    except OSError:
        return 0.0


def _ram_pct_proc() -> float:
    try:
        info = {}
        with open("/proc/meminfo") as f:
            for line in f:
                if ":" in line:
                    k, v = line.split(":", 1)
                    info[k.strip()] = v.strip()
        total = int(info.get("MemTotal", "0").split()[0])
        avail = int(info.get("MemAvailable", info.get("MemFree", "0")).split()[0])
        if total <= 0:
            return 0.0
        return max(0.0, min(100.0, (1.0 - avail / total) * 100.0))
    except (OSError, ValueError, IndexError):
        return 0.0


def _loadavg() -> float:
    try:
        with open("/proc/loadavg") as f:
            return float(f.read().split()[0])
    except (OSError, ValueError, IndexError):
        try:
            return float(os.getloadavg()[0])
        except (OSError, AttributeError):
            return 0.0


def _disk_pct(path: str = "/") -> float:
    try:
        st = os.statvfs(path)
        total = st.f_blocks * st.f_frsize
        free = st.f_bavail * st.f_frsize
        if total <= 0:
            return 0.0
        return max(0.0, min(100.0, (1.0 - free / total) * 100.0))
    except OSError:
        return 0.0


def collect_resources(db_path: Optional[str] = None) -> dict[str, float]:
    """Collect resource gauges. Prefer psutil; fall back to /proc."""
    out: dict[str, float] = {}
    used_psutil = False
    try:
        import psutil  # type: ignore

        out["cpu_pct"] = float(psutil.cpu_percent(interval=0.05))
        out["ram_pct"] = float(psutil.virtual_memory().percent)
        out["loadavg"] = float(os.getloadavg()[0]) if hasattr(os, "getloadavg") else 0.0
        out["disk_pct"] = float(psutil.disk_usage("/").percent)
        used_psutil = True
    except Exception:
        out["cpu_pct"] = _cpu_pct_proc()
        out["ram_pct"] = _ram_pct_proc()
        out["loadavg"] = _loadavg()
        out["disk_pct"] = _disk_pct("/")

    out["_psutil"] = 1.0 if used_psutil else 0.0

    # Queue / running from DB
    queue_depth = 0.0
    running_tasks = 0.0
    running_agents = 0.0
    try:
        _ensure_path()
        from storage import db as dbmod  # type: ignore

        stats = dbmod.queue_stats(db_path=db_path)
        queue_depth = float(stats.get("queued", 0) or 0)
        running_tasks = float(stats.get("running", 0) or 0)
        with dbmod.connect(db_path) as conn:
            row = conn.execute(
                "SELECT COUNT(*) AS c FROM agents WHERE status IN ('busy','active')"
            ).fetchone()
            # Prefer busy count if column populated
            busy = conn.execute(
                "SELECT COUNT(*) AS c FROM agents WHERE status = 'busy'"
            ).fetchone()
            running_agents = float((busy["c"] if busy else 0) or 0)
            if running_agents == 0:
                # Fall back to running agent_runs
                ar = conn.execute(
                    "SELECT COUNT(*) AS c FROM agent_runs WHERE status = 'running'"
                ).fetchone()
                running_agents = float((ar["c"] if ar else 0) or 0)
    except Exception:
        pass

    out["queue_depth"] = queue_depth
    out["running_tasks"] = running_tasks
    out["running_agents"] = running_agents
    return out


def sample_resources(db_path: Optional[str] = None) -> dict[str, Any]:
    """Sample and persist metrics rows. Soft-fails."""
    _ensure_path()
    from observability.metrics import MetricNames, record_metric  # type: ignore

    data = collect_resources(db_path=db_path)
    mapping = [
        (MetricNames.RES_CPU_PCT, "cpu_pct"),
        (MetricNames.RES_RAM_PCT, "ram_pct"),
        (MetricNames.RES_LOADAVG, "loadavg"),
        (MetricNames.RES_DISK_PCT, "disk_pct"),
        (MetricNames.RES_QUEUE_DEPTH, "queue_depth"),
        (MetricNames.RES_RUNNING_AGENTS, "running_agents"),
        (MetricNames.RES_RUNNING_TASKS, "running_tasks"),
        (MetricNames.QUEUE_DEPTH, "queue_depth"),
    ]
    written = []
    for mname, key in mapping:
        try:
            mid = record_metric(mname, float(data.get(key, 0)), labels={"source": "sampler"}, db_path=db_path)
            written.append(mid)
        except Exception:
            pass
    return {"sample": data, "written": written}


def main(argv: Optional[list[str]] = None) -> int:
    argv = list(argv if argv is not None else sys.argv[1:])
    db_path = os.environ.get("AGENTBOX_V5_DB")
    if argv and argv[0] == "collect":
        print(json.dumps(collect_resources(db_path=db_path), indent=2))
        return 0
    result = sample_resources(db_path=db_path)
    print(json.dumps(result, indent=2, default=str))
    return 0


if __name__ == "__main__":
    sys.exit(main())
