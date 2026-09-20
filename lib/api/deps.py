from __future__ import annotations

import configparser
import os
import sys
from pathlib import Path
from typing import Any, Optional

from fastapi import Cookie, Depends, Header, Request

from .auth import (
    COOKIE_NAME,
    ensure_admin_token,
    lookup_session,
    role_allows,
    verify_admin_token,
)
from .errors import APIError

LIB_ROOT = Path(__file__).resolve().parent.parent
if str(LIB_ROOT) not in sys.path:
    sys.path.insert(0, str(LIB_ROOT))

DATA_ROOT = Path(os.environ.get("AGENTBOX_V5_HOME", Path.home() / ".local/share/agentbox/v5"))
CONFIG_USER = Path.home() / ".config" / "agentbox-v5" / "web.ini"
CONFIG_DEFAULT = Path(__file__).resolve().parent.parent.parent / "config" / "web.ini"
CONFIG_SHARE = DATA_ROOT / "config" / "web.ini"


def load_web_config() -> configparser.ConfigParser:
    cfg = configparser.ConfigParser()
    for path in (CONFIG_DEFAULT, CONFIG_SHARE, CONFIG_USER):
        if path.is_file():
            cfg.read(str(path))
    for sec, defaults in {
        "server": {"host": "100.123.66.15", "port": "8787", "fallback_host": "127.0.0.1"},
        "security": {
            "tailscale_only": "true",
            "require_auth": "true",
            "session_timeout_minutes": "120",
            "health_public": "true", "docs_enabled": "false", "session_timeout_minutes": "120",
        },
        "websocket": {"enabled": "true", "heartbeat_seconds": "20", "max_connections": "32"},
        "ui": {"enabled": "true", "title": "AgentBox", "refresh_interval_seconds": "3"},
    }.items():
        if not cfg.has_section(sec):
            cfg.add_section(sec)
        for k, v in defaults.items():
            if not cfg.has_option(sec, k):
                cfg.set(sec, k, v)
    return cfg


def db_connect():
    from storage import db as dbmod
    return dbmod.connect()


def version_str() -> str:
    for pth in (DATA_ROOT / "VERSION", Path(__file__).resolve().parent.parent.parent / "VERSION"):
        if pth.is_file():
            return pth.read_text().strip()
    return "5.3.0"


def daemon_status() -> str:
    for pid_file in (
        DATA_ROOT / "runtime" / "pids" / "agentboxd.pid",
        Path.home() / ".local/share/agentbox-v5/runtime/pids/agentboxd.pid",
    ):
        if not pid_file.is_file():
            continue
        try:
            os.kill(int(pid_file.read_text().strip()), 0)
            return "running"
        except Exception:
            continue
    return "stopped"


def is_tailscale_addr(addr: Optional[str]) -> bool:
    if not addr:
        return False
    if addr in ("127.0.0.1", "::1"):
        return True
    parts = addr.split(".")
    if len(parts) != 4:
        return False
    try:
        a, b = int(parts[0]), int(parts[1])
    except ValueError:
        return False
    return a == 100 and 64 <= b <= 127


class Actor:
    def __init__(
        self,
        role: str,
        actor: str,
        session_id: Optional[str] = None,
        worker_id: Optional[str] = None,
    ):
        self.role = role
        self.actor = actor
        self.session_id = session_id
        self.worker_id = worker_id


async def get_actor(
    request: Request,
    authorization: Optional[str] = Header(default=None),
    agentbox_session: Optional[str] = Cookie(default=None, alias=COOKIE_NAME),
) -> Actor:
    cfg = load_web_config()
    require_auth = cfg.getboolean("security", "require_auth", fallback=True)
    health_public = cfg.getboolean("security", "health_public", fallback=True)
    path = request.url.path

    if health_public and path in ("/api/v1/health", "/health"):
        return Actor("viewer", "anonymous")
    if path.startswith("/static/") or path in ("/login", "/favicon.ico"):
        return Actor("viewer", "anonymous")
    if path == "/" or path.startswith("/app"):
        return Actor("viewer", "anonymous")
    # Enrollment is token-gated in the route itself (one-time enroll token)
    if path == "/api/v1/workers/enroll" and request.method == "POST":
        return Actor("enroll", "enrollment")

    if not require_auth:
        return Actor("admin", "local")

    if authorization and authorization.lower().startswith("bearer "):
        raw = authorization[7:].strip()
        if verify_admin_token(raw):
            return Actor("admin", "bearer")
        # Worker session token
        try:
            from distributed import enrollment as enrollmod
            wses = enrollmod.verify_worker_session(raw)
            if wses:
                return Actor("worker", "worker:" + wses["worker_id"], worker_id=wses["worker_id"])
        except Exception:
            pass

    if agentbox_session:
        conn = db_connect()
        try:
            ses = lookup_session(conn, agentbox_session)
            if ses:
                return Actor(ses["user_role"], "session:" + ses["id"], ses["id"])
        finally:
            conn.close()

    qtok = request.query_params.get("token")
    if qtok and verify_admin_token(qtok):
        return Actor("admin", "query-token")

    raise APIError("UNAUTHENTICATED", "Authentication required", status_code=401)


def require_role(needed: str):
    async def _dep(actor: Actor = Depends(get_actor)) -> Actor:
        if not role_allows(actor.role, needed):
            raise APIError("FORBIDDEN", f"Role '{actor.role}' cannot perform this action", status_code=403)
        return actor
    return _dep


async def require_worker(actor: Actor = Depends(get_actor)) -> Actor:
    """Accept worker session OR admin (for debugging)."""
    if actor.role == "worker" and actor.worker_id:
        return actor
    if actor.role == "admin":
        # admin calling worker endpoints must pass worker_id via path; leave worker_id unset
        return actor
    raise APIError("FORBIDDEN", "Worker session required", status_code=403)


def audit(
    method: str,
    path: str,
    actor: Optional[Actor],
    status: int,
    remote: str = "",
    task_id: str = "",
) -> None:
    try:
        conn = db_connect()
        conn.execute(
            "INSERT INTO api_audit (method, path, actor, role, status_code, task_id, remote_addr) VALUES (?,?,?,?,?,?,?)",
            (
                method,
                path,
                actor.actor if actor else None,
                actor.role if actor else None,
                status,
                task_id or None,
                remote,
            ),
        )
        conn.commit()
        conn.close()
    except Exception:
        pass


def system_stats() -> dict[str, Any]:
    out: dict[str, Any] = {"cpu_percent": 0.0, "memory_percent": 0.0, "disk_percent": 0.0}
    try:
        import psutil
        out["cpu_percent"] = float(psutil.cpu_percent(interval=0.05))
        out["memory_percent"] = float(psutil.virtual_memory().percent)
        out["disk_percent"] = float(psutil.disk_usage(str(DATA_ROOT)).percent)
        vm = psutil.virtual_memory()
        out["memory_used_gb"] = round(vm.used / (1024**3), 2)
        out["memory_total_gb"] = round(vm.total / (1024**3), 2)
    except Exception:
        pass
    return out


try:
    ensure_admin_token()
except Exception:
    pass
