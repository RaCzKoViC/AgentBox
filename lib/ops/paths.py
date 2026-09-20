"""Shared path/config helpers for AgentBox ops."""
from __future__ import annotations

import configparser
import os
from pathlib import Path
from typing import Optional

DEFAULT_HOME = Path.home() / ".local" / "share" / "agentbox" / "v5"
DEFAULT_CONFIG = Path.home() / ".config" / "agentbox-v5"


def data_home() -> Path:
    return Path(os.environ.get("AGENTBOX_V5_HOME", DEFAULT_HOME))


def db_path() -> Path:
    env = os.environ.get("AGENTBOX_V5_DB")
    if env:
        return Path(env)
    return data_home() / "data" / "agentbox.db"


def backups_dir() -> Path:
    p = data_home() / "backups"
    p.mkdir(parents=True, exist_ok=True)
    return p


def runtime_dir() -> Path:
    p = data_home() / "runtime"
    p.mkdir(parents=True, exist_ok=True)
    return p


def locks_dir() -> Path:
    p = runtime_dir() / "locks"
    p.mkdir(parents=True, exist_ok=True)
    return p


def pids_dir() -> Path:
    p = runtime_dir() / "pids"
    p.mkdir(parents=True, exist_ok=True)
    return p


def logs_dir() -> Path:
    p = data_home() / "logs"
    p.mkdir(parents=True, exist_ok=True)
    return p


def config_dir() -> Path:
    p = DEFAULT_CONFIG
    p.mkdir(parents=True, exist_ok=True)
    return p


def share_config_dir() -> Path:
    return data_home() / "config"


def maintenance_flag() -> Path:
    return runtime_dir() / "maintenance.flag"


def version_file() -> Path:
    for c in (
        data_home() / "VERSION",
        Path(__file__).resolve().parents[2] / "VERSION",
    ):
        if c.is_file():
            return c
    return data_home() / "VERSION"


def read_version() -> str:
    vf = version_file()
    if vf.is_file():
        return vf.read_text(encoding="utf-8").strip()
    return "5.0.0"


def load_ini(name: str) -> configparser.ConfigParser:
    """Load ~/.config/agentbox-v5/<name> with fallback to share + project config."""
    cp = configparser.ConfigParser()
    candidates = [
        config_dir() / name,
        share_config_dir() / name,
        Path(__file__).resolve().parents[2] / "config" / name,
    ]
    for c in candidates:
        if c.is_file():
            cp.read(str(c))
            break
    return cp


def acquire_lock(name: str, operation_id: str = "") -> Path:
    """Simple lock file; raises RuntimeError if held by live PID."""
    import json
    import socket
    import time
    from datetime import datetime, timezone

    lock = locks_dir() / f"{name}.lock"
    if lock.exists():
        try:
            data = json.loads(lock.read_text(encoding="utf-8"))
            pid = int(data.get("pid") or 0)
            if pid and _pid_alive(pid):
                raise RuntimeError(f"lock {name} held by pid={pid}")
        except (json.JSONDecodeError, ValueError, KeyError):
            pass
        lock.unlink(missing_ok=True)
    payload = {
        "pid": os.getpid(),
        "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "operation_id": operation_id or name,
        "hostname": socket.gethostname(),
    }
    lock.write_text(json.dumps(payload), encoding="utf-8")
    return lock


def release_lock(name: str) -> None:
    (locks_dir() / f"{name}.lock").unlink(missing_ok=True)


def _pid_alive(pid: int) -> bool:
    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def pid_alive(pid: int) -> bool:
    return _pid_alive(pid)
