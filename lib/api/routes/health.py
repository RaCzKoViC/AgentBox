from __future__ import annotations
from fastapi import APIRouter
from ..deps import daemon_status, version_str

router = APIRouter(tags=["health"])

@router.get("/api/v1/health")
@router.get("/health")
def health():
    db_ok = "ok"
    try:
        from storage import db as dbmod
        conn = dbmod.connect()
        conn.execute("SELECT 1").fetchone()
        conn.close()
    except Exception:
        db_ok = "error"
    ws = "unknown"
    try:
        from ..websocket import HUB
        ws = "running"
        clients = HUB.count
    except Exception:
        clients = 0
    return {
        "status": "ok" if db_ok == "ok" else "degraded",
        "version": version_str(),
        "daemon": daemon_status(),
        "database": db_ok,
        "scheduler": daemon_status(),
        "websocket": ws,
        "websocket_clients": clients,
    }
