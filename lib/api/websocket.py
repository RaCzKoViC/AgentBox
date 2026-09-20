"""WebSocket hub — event fan-out + heartbeat."""
from __future__ import annotations

import asyncio
import json
import time
from datetime import datetime, timezone
from typing import Any, Optional, Set

from fastapi import APIRouter, Query, WebSocket, WebSocketDisconnect

from .auth import COOKIE_NAME, lookup_session, verify_admin_token
from .deps import db_connect, load_web_config

router = APIRouter()


def _ts() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


class Hub:
    def __init__(self) -> None:
        self.clients: Set[WebSocket] = set()
        self.subs: dict[WebSocket, set[str]] = {}
        self.task_filters: dict[WebSocket, Optional[str]] = {}
        self._lock = asyncio.Lock()

    @property
    def count(self) -> int:
        return len(self.clients)

    async def connect(self, ws: WebSocket) -> None:
        await ws.accept()
        async with self._lock:
            self.clients.add(ws)
            self.subs[ws] = {"system", "tasks", "agents", "handoffs", "approvals", "metrics"}
            self.task_filters[ws] = None

    async def disconnect(self, ws: WebSocket) -> None:
        async with self._lock:
            self.clients.discard(ws)
            self.subs.pop(ws, None)
            self.task_filters.pop(ws, None)

    async def broadcast(self, event: dict[str, Any]) -> None:
        dead = []
        data = json.dumps(event, default=str)
        async with self._lock:
            clients = list(self.clients)
            subs = dict(self.subs)
            tfilters = dict(self.task_filters)
        for ws in clients:
            topics = subs.get(ws, set())
            et = event.get("type", "")
            topic_ok = True
            if et.startswith("task.") and "tasks" not in topics and "system" not in topics:
                topic_ok = False
            if et.startswith("approval.") and "approvals" not in topics:
                topic_ok = False
            tf = tfilters.get(ws)
            if tf and event.get("task_id") and event.get("task_id") != tf:
                topic_ok = False
            if not topic_ok:
                continue
            try:
                await ws.send_text(data)
            except Exception:
                dead.append(ws)
        for ws in dead:
            await self.disconnect(ws)


HUB = Hub()


def _auth_ws(ws: WebSocket, token: Optional[str]) -> bool:
    if token and verify_admin_token(token):
        return True
    cookie = ws.cookies.get(COOKIE_NAME)
    if cookie:
        conn = db_connect()
        try:
            if lookup_session(conn, cookie):
                return True
        finally:
            conn.close()
    auth = ws.headers.get("authorization") or ""
    if auth.lower().startswith("bearer ") and verify_admin_token(auth[7:].strip()):
        return True
    cfg = load_web_config()
    if not cfg.getboolean("security", "require_auth", fallback=True):
        return True
    return False


@router.websocket("/ws")
@router.websocket("/api/v1/ws")
@router.websocket("/ws/events")
async def ws_events(
    websocket: WebSocket,
    token: Optional[str] = Query(default=None),
    task_id: Optional[str] = Query(default=None),
):
    cfg = load_web_config()
    if not cfg.getboolean("websocket", "enabled", fallback=True):
        await websocket.close(code=1013)
        return
    max_c = cfg.getint("websocket", "max_connections", fallback=32)
    if HUB.count >= max_c:
        await websocket.close(code=1013)
        return
    if not _auth_ws(websocket, token):
        await websocket.close(code=1008)
        return

    await HUB.connect(websocket)
    if task_id:
        HUB.task_filters[websocket] = task_id

    hb = cfg.getint("websocket", "heartbeat_seconds", fallback=20)
    await websocket.send_text(
        json.dumps({"type": "system.hello", "timestamp": _ts(), "payload": {"version": "5.0.0-rc1"}})
    )
    try:
        from storage import db as dbmod
        events = dbmod.list_events(limit=20)
        for ev in reversed(events):
            await websocket.send_text(
                json.dumps(
                    {
                        "type": ev.get("kind") or ev.get("type") or "event",
                        "timestamp": ev.get("created_at") or ev.get("ts") or _ts(),
                        "task_id": ev.get("task_id"),
                        "payload": ev.get("payload") or {"message": ev.get("message")},
                    },
                    default=str,
                )
            )
    except Exception:
        pass

    last_hb = time.monotonic()
    try:
        while True:
            try:
                msg = await asyncio.wait_for(websocket.receive_text(), timeout=1.0)
                try:
                    data = json.loads(msg)
                    if "subscribe" in data and isinstance(data["subscribe"], list):
                        HUB.subs[websocket] = set(str(x) for x in data["subscribe"])
                    if data.get("task_id"):
                        HUB.task_filters[websocket] = data["task_id"]
                    if data.get("type") == "ping":
                        await websocket.send_text(json.dumps({"type": "pong", "timestamp": _ts()}))
                except Exception:
                    pass
            except asyncio.TimeoutError:
                pass
            if time.monotonic() - last_hb >= hb:
                await websocket.send_text(
                    json.dumps({"type": "daemon.health", "timestamp": _ts(), "payload": {"heartbeat": True}})
                )
                last_hb = time.monotonic()
    except WebSocketDisconnect:
        pass
    except Exception:
        pass
    finally:
        await HUB.disconnect(websocket)
