"""Worker runtime loop: heartbeat + assignment poll + execute."""
from __future__ import annotations

import json
import os
import signal
import sys
import time
from pathlib import Path
from typing import Any, Optional

_HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(_HERE.parent))

from distributed.transport import http_json  # noqa: E402
from distributed.capabilities import probe_local  # noqa: E402
from worker import local_store, health, executor  # noqa: E402
from worker import VERSION  # noqa: E402

STOP = False


def _handle_sig(signum, frame):
    global STOP
    STOP = True


def enroll(url: str, token: str, name: str = "") -> dict[str, Any]:
    import platform
    caps = probe_local()
    body = {
        "token": token,
        "name": name or (platform.node() + "-worker"),
        "hostname": platform.node(),
        "tailscale_ip": _guess_tailscale_ip(),
        "platform": platform.system().lower(),
        "architecture": platform.machine(),
        "version": VERSION,
        "capabilities": caps,
        "labels": ["linux", "local", "loopback"],
        "max_parallel_tasks": 2,
        "protocol_version": 1,
    }
    base = url.rstrip("/")
    result = http_json("POST", f"{base}/api/v1/workers/enroll", body=body)
    st = {
        "control_plane": base,
        "worker_id": result["worker_id"],
        "session_token": result["session_token"],
        "session_id": result.get("session_id"),
        "status": result.get("status"),
        "enrolled_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "name": body["name"],
    }
    local_store.save_state(st)
    # write config.ini snippet
    cfg = local_store.config_ini_path()
    cfg.write_text(
        f"[worker]\nname = {body['name']}\ncontrol_plane = {base}\n"
        f"heartbeat_seconds = 5\nmax_parallel_tasks = 2\n"
        f"worker_id = {result['worker_id']}\n\n"
        f"[security]\ntailscale_only = true\n"
    )
    return result


def _guess_tailscale_ip() -> str:
    try:
        import socket
        # prefer known control-plane style 100.x if present on this host
        import subprocess
        out = subprocess.check_output(["hostname", "-I"], text=True, timeout=2)
        for ip in out.split():
            parts = ip.split(".")
            if len(parts) == 4 and parts[0] == "100" and 64 <= int(parts[1]) <= 127:
                return ip
    except Exception:
        pass
    return "127.0.0.1"


def send_heartbeat(once: bool = False) -> dict[str, Any]:
    st = local_store.load_state()
    if not st.get("session_token") or not st.get("control_plane"):
        raise RuntimeError("worker not enrolled — run: agent5-worker enroll --url ... --token ...")
    snap = health.snapshot()
    body = {
        "cpu_percent": snap["cpu_percent"],
        "memory_percent": snap["memory_percent"],
        "disk_percent": snap["disk_percent"],
        "load1": snap["load1"],
        "active_tasks": snap["active_tasks"],
        "version": VERSION,
        "health": snap["health"],
    }
    url = f"{st['control_plane'].rstrip('/')}/api/v1/workers/heartbeat"
    result = http_json("POST", url, body=body, token=st["session_token"])
    st["status"] = result.get("status", st.get("status"))
    st["last_heartbeat"] = result.get("server_time")
    local_store.save_state(st)
    return result


def poll_and_run_once() -> Optional[dict[str, Any]]:
    st = local_store.load_state()
    wid = st.get("worker_id")
    base = st.get("control_plane", "").rstrip("/")
    tok = st.get("session_token")
    if not (wid and base and tok):
        return None
    data = http_json("GET", f"{base}/api/v1/workers/{wid}/assignment", token=tok)
    asgn = data.get("assignment")
    if not asgn:
        return None
    aid = asgn["id"]
    http_json("POST", f"{base}/api/v1/workers/{wid}/assignment/{aid}/accept", body={}, token=tok)
    st["active_tasks"] = int(st.get("active_tasks") or 0) + 1
    local_store.save_state(st)
    result = executor.execute_assignment(asgn, use_stub=True)
    http_json(
        "POST",
        f"{base}/api/v1/workers/{wid}/assignment/{aid}/result",
        body={"ok": bool(result.get("ok")), "result": result, "error": result.get("error", "")},
        token=tok,
    )
    st["active_tasks"] = max(0, int(st.get("active_tasks") or 1) - 1)
    local_store.save_state(st)
    return result


def start_loop(poll_assignments: bool = True) -> None:
    global STOP
    STOP = False
    signal.signal(signal.SIGTERM, _handle_sig)
    signal.signal(signal.SIGINT, _handle_sig)
    local_store.ensure_dirs()
    pidp = local_store.pid_path()
    pidp.write_text(str(os.getpid()) + "\n")
    log = local_store.log_path()
    interval = 5
    with open(log, "a") as lf:
        lf.write(f"\n=== worker start pid={os.getpid()} ===\n")
        lf.flush()
        while not STOP:
            try:
                hb = send_heartbeat()
                lf.write(f"heartbeat ok status={hb.get('status')}\n")
                if poll_assignments:
                    r = poll_and_run_once()
                    if r:
                        lf.write(f"assignment result={json.dumps(r)[:200]}\n")
                lf.flush()
            except Exception as e:
                lf.write(f"error: {e}\n")
                lf.flush()
            for _ in range(interval * 10):
                if STOP:
                    break
                time.sleep(0.1)
        lf.write("=== worker stop ===\n")
    try:
        pidp.unlink(missing_ok=True)
    except Exception:
        pass


def stop() -> bool:
    pidp = local_store.pid_path()
    if not pidp.is_file():
        return False
    try:
        pid = int(pidp.read_text().strip())
        os.kill(pid, signal.SIGTERM)
        return True
    except Exception:
        try:
            pidp.unlink(missing_ok=True)
        except Exception:
            pass
        return False


def status() -> dict[str, Any]:
    st = local_store.load_state()
    running = False
    pid = None
    pidp = local_store.pid_path()
    if pidp.is_file():
        try:
            pid = int(pidp.read_text().strip())
            os.kill(pid, 0)
            running = True
        except Exception:
            running = False
    return {
        "running": running,
        "pid": pid,
        "worker_id": st.get("worker_id"),
        "status": st.get("status"),
        "control_plane": st.get("control_plane"),
        "last_heartbeat": st.get("last_heartbeat"),
        "health": health.snapshot(),
    }
