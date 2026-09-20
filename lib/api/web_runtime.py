"""Manage AgentBox web/API process (start/stop/status) without systemd."""
from __future__ import annotations

import json
import os
import signal
import socket
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

_LIB = Path(__file__).resolve().parent.parent
if str(_LIB) not in sys.path:
    sys.path.insert(0, str(_LIB))

from api.auth import ensure_admin_token, read_admin_token, rotate_admin_token
from api.deps import DATA_ROOT, load_web_config, version_str

PID_FILE = DATA_ROOT / "runtime" / "pids" / "web.pid"
LOG_FILE = DATA_ROOT / "logs" / "web.log"


def _pid_path() -> Path:
    PID_FILE.parent.mkdir(parents=True, exist_ok=True)
    return PID_FILE


def _log_path() -> Path:
    LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
    return LOG_FILE


def _read_pid() -> int | None:
    p = _pid_path()
    if not p.is_file():
        return None
    try:
        pid = int(p.read_text().strip())
        os.kill(pid, 0)
        return pid
    except Exception:
        try:
            p.unlink()
        except Exception:
            pass
        return None


def _can_bind(host: str) -> bool:
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        s.bind((host, 0))
        s.close()
        return True
    except OSError:
        return False


def _resolve_bind() -> tuple[str, int]:
    """Prefer Tailscale IP; fall back to 0.0.0.0 (if allowed) or localhost."""
    cfg = load_web_config()
    preferred = cfg.get("server", "preferred_host", fallback=cfg.get("server", "host", fallback="100.123.66.15"))
    host = cfg.get("server", "host", fallback=preferred)
    port = cfg.getint("server", "port", fallback=8787)
    if _can_bind(host):
        return host, port
    if preferred != host and _can_bind(preferred):
        return preferred, port
    allow_all = cfg.getboolean("server", "allow_bind_all_if_ts_unavailable", fallback=True)
    if allow_all and _can_bind("0.0.0.0"):
        # Documented fallback: Tailscale userspace has no kernel 100.x iface.
        return "0.0.0.0", port
    return cfg.get("server", "fallback_host", fallback="127.0.0.1"), port


def _public_host(bind_host: str) -> str:
    if bind_host in ("0.0.0.0", "::"):
        return "100.123.66.15"
    return bind_host


def start() -> dict:
    existing = _read_pid()
    host, port = _resolve_bind()
    pub = _public_host(host)
    if existing:
        return {
            "ok": True,
            "already_running": True,
            "running": True,
            "pid": existing,
            "host": host,
            "port": port,
            "url": f"http://{pub}:{port}",
        }

    ensure_admin_token()
    logf = _log_path()
    env = os.environ.copy()
    env["PYTHONPATH"] = str(_LIB) + os.pathsep + env.get("PYTHONPATH", "")
    env.setdefault("AGENTBOX_V5_HOME", str(DATA_ROOT))
    env.setdefault("AGENTBOX_V5_DB", str(DATA_ROOT / "data" / "agentbox.db"))
    env.setdefault("AGENTBOX_V5_LIB", str(_LIB))

    venv_python = DATA_ROOT / "venv" / "bin" / "python"
    py = str(venv_python) if venv_python.is_file() else sys.executable

    cmd = [
        py, "-m", "uvicorn",
        "api.app:app",
        "--host", host,
        "--port", str(port),
        "--app-dir", str(_LIB),
        "--log-level", "info",
    ]
    with open(logf, "a") as lf:
        lf.write(f"\n--- start {time.strftime('%Y-%m-%d %H:%M:%S')} {host}:{port} ---\n")
        proc = subprocess.Popen(
            cmd,
            stdout=lf,
            stderr=subprocess.STDOUT,
            cwd=str(_LIB),
            env=env,
            start_new_session=True,
        )
    _pid_path().write_text(str(proc.pid) + "\n")

    ok = False
    url = f"http://127.0.0.1:{port}/api/v1/health"
    for _ in range(30):
        time.sleep(0.2)
        try:
            with urllib.request.urlopen(url, timeout=1) as r:
                if r.status == 200:
                    ok = True
                    break
        except Exception:
            if proc.poll() is not None:
                break
    return {
        "ok": ok,
        "running": ok or _read_pid() is not None,
        "pid": proc.pid,
        "host": host,
        "port": port,
        "url": f"http://{pub}:{port}",
        "api": f"http://{pub}:{port}/api/v1/health",
        "ws": f"ws://{pub}:{port}/ws",
        "pid_file": str(_pid_path()),
        "log_file": str(logf),
        "version": version_str(),
        "bind_note": "TS IP not on kernel iface; bound 0.0.0.0 (allow_bind_all_if_ts_unavailable)" if host == "0.0.0.0" else "",
    }


def stop(timeout: float = 8.0) -> dict:
    pid = _read_pid()
    if not pid:
        return {"ok": True, "stopped": False, "message": "not running"}
    try:
        os.kill(pid, signal.SIGTERM)
    except ProcessLookupError:
        _pid_path().unlink(missing_ok=True)
        return {"ok": True, "stopped": True, "pid": pid}
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            os.kill(pid, 0)
            time.sleep(0.2)
        except ProcessLookupError:
            break
    else:
        try:
            os.kill(pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
    _pid_path().unlink(missing_ok=True)
    return {"ok": True, "stopped": True, "pid": pid}


def status() -> dict:
    pid = _read_pid()
    host, port = _resolve_bind()
    pub = _public_host(host)
    return {
        "running": pid is not None,
        "pid": pid,
        "host": host,
        "port": port,
        "url": f"http://{pub}:{port}",
        "api": f"http://{pub}:{port}/api/v1/health",
        "ws": f"ws://{pub}:{port}/ws",
        "pid_file": str(_pid_path()),
        "version": version_str(),
        "token_present": read_admin_token() is not None,
        "bind_note": "fallback 0.0.0.0 (TS IP not assignable on this host)" if host == "0.0.0.0" else "",
    }


def token_show() -> str:
    return ensure_admin_token()


def token_rotate() -> str:
    return rotate_admin_token()


def main(argv: list[str] | None = None) -> int:
    argv = list(argv or sys.argv[1:])
    if not argv:
        print("usage: web_runtime.py start|stop|status|token|rotate-token")
        return 2
    cmd = argv[0]
    if cmd == "start":
        print(json.dumps(start(), indent=2))
        return 0
    if cmd == "stop":
        print(json.dumps(stop(), indent=2))
        return 0
    if cmd == "status":
        print(json.dumps(status(), indent=2))
        return 0
    if cmd == "token":
        print(token_show())
        return 0
    if cmd in ("rotate-token", "token-rotate"):
        print(token_rotate())
        return 0
    print("unknown command", cmd)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
