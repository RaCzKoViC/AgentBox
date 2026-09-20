"""Worker-local config + state store (not source of truth)."""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Optional

DEFAULT_ROOT = Path.home() / ".local" / "share" / "agentbox-worker"
CONFIG_DIR = Path.home() / ".config" / "agentbox-worker"


def root() -> Path:
    env = os.environ.get("AGENTBOX_WORKER_HOME")
    return Path(env) if env else DEFAULT_ROOT


def ensure_dirs() -> Path:
    r = root()
    for sub in ("state", "cache", "artifacts", "logs", "runtime"):
        (r / sub).mkdir(parents=True, exist_ok=True)
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    return r


def state_path() -> Path:
    ensure_dirs()
    return root() / "state" / "worker.json"


def load_state() -> dict[str, Any]:
    p = state_path()
    if not p.is_file():
        return {}
    try:
        return json.loads(p.read_text())
    except Exception:
        return {}


def save_state(data: dict[str, Any]) -> None:
    p = state_path()
    p.write_text(json.dumps(data, indent=2) + "\n")
    os.chmod(p, 0o600)


def pid_path() -> Path:
    ensure_dirs()
    return root() / "runtime" / "worker.pid"


def log_path() -> Path:
    ensure_dirs()
    return root() / "logs" / "worker.log"


def config_ini_path() -> Path:
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    return CONFIG_DIR / "config.ini"
