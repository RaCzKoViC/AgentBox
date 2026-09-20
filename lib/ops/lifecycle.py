#!/usr/bin/env python3
"""Unified lifecycle — start/stop/restart/status for daemon + web."""
from __future__ import annotations

import json
import os
import signal
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Optional

_HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(_HERE.parent))

from ops.paths import load_ini, pid_alive, pids_dir  # noqa: E402


def _bin(name: str) -> Optional[str]:
    home = Path.home() / ".local" / "bin" / name
    if home.is_file() and os.access(home, os.X_OK):
        return str(home)
    which = subprocess.run(["bash", "-lc", f"command -v {name}"], capture_output=True, text=True)
    p = which.stdout.strip()
    return p or None


def daemon_status() -> dict[str, Any]:
    pf = pids_dir() / "agentboxd.pid"
    if not pf.is_file():
        return {"component": "daemon", "running": False}
    try:
        pid = int(pf.read_text().strip() or "0")
    except ValueError:
        pid = 0
    return {"component": "daemon", "running": pid_alive(pid), "pid": pid, "pid_file": str(pf)}


def web_status() -> dict[str, Any]:
    lib = os.environ.get("AGENTBOX_V5_LIB", str(Path.home() / ".local/lib/agentbox5"))
    try:
        out = subprocess.check_output(
            [sys.executable, f"{lib}/api/web_runtime.py", "status"],
            text=True,
            timeout=15,
        )
        data = json.loads(out)
        data["component"] = "web"
        return data
    except Exception as e:
        return {"component": "web", "running": False, "error": str(e)}


def status() -> dict[str, Any]:
    return {"daemon": daemon_status(), "web": web_status()}


def start(components: Optional[list[str]] = None) -> dict[str, Any]:
    comps = components or ["daemon", "web"]
    results = {}
    if "daemon" in comps:
        dbin = _bin("agentboxd")
        if dbin:
            subprocess.run([dbin, "start"], check=False)
        results["daemon"] = daemon_status()
    if "web" in comps:
        lib = os.environ.get("AGENTBOX_V5_LIB", str(Path.home() / ".local/lib/agentbox5"))
        subprocess.run([sys.executable, f"{lib}/api/web_runtime.py", "start"], check=False)
        results["web"] = web_status()
    return {"ok": True, "started": results}


def graceful_stop(components: Optional[list[str]] = None, timeout: Optional[int] = None) -> dict[str, Any]:
    cfg = load_ini("recovery.ini")
    timeout = timeout if timeout is not None else cfg.getint(
        "recovery", "graceful_shutdown_timeout", fallback=30
    )
    comps = components or ["web", "daemon"]
    results = {}
    # drain: mark maintenance-like via SIGTERM to daemon
    if "daemon" in comps:
        st = daemon_status()
        if st.get("running") and st.get("pid"):
            try:
                os.kill(st["pid"], signal.SIGTERM)
                deadline = time.time() + timeout
                while time.time() < deadline and pid_alive(st["pid"]):
                    time.sleep(0.3)
                if pid_alive(st["pid"]):
                    os.kill(st["pid"], signal.SIGKILL)
                    results["daemon"] = {"forced": True, "pid": st["pid"]}
                else:
                    results["daemon"] = {"graceful": True, "pid": st["pid"]}
            except OSError as e:
                results["daemon"] = {"error": str(e)}
            (pids_dir() / "agentboxd.pid").unlink(missing_ok=True)
        else:
            dbin = _bin("agentboxd")
            if dbin:
                subprocess.run([dbin, "stop"], check=False)
            results["daemon"] = daemon_status()
    if "web" in comps:
        lib = os.environ.get("AGENTBOX_V5_LIB", str(Path.home() / ".local/lib/agentbox5"))
        subprocess.run([sys.executable, f"{lib}/api/web_runtime.py", "stop"], check=False)
        results["web"] = web_status()
    return {"ok": True, "stopped": results, "timeout": timeout}


def restart(components: Optional[list[str]] = None) -> dict[str, Any]:
    stop = graceful_stop(components)
    start_r = start(components)
    return {"ok": True, "stop": stop, "start": start_r}


def main(argv: Optional[list[str]] = None) -> int:
    argv = list(argv or sys.argv[1:])
    cmd = argv[0] if argv else "status"
    comps = None
    if "--daemon-only" in argv:
        comps = ["daemon"]
    elif "--web-only" in argv:
        comps = ["web"]
    if cmd == "status":
        print(json.dumps(status(), indent=2))
    elif cmd == "start":
        print(json.dumps(start(comps), indent=2))
    elif cmd == "stop":
        print(json.dumps(graceful_stop(comps), indent=2))
    elif cmd == "restart":
        print(json.dumps(restart(comps), indent=2))
    else:
        print("usage: lifecycle.py status|start|stop|restart [--daemon-only|--web-only]", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
