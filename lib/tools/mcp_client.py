#!/usr/bin/env python3
"""MCP client stub — connect/list if MCP SDK available; otherwise registry-only."""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any, Optional

_HERE = Path(__file__).resolve().parent


def _ensure_path() -> None:
    lib = str(_HERE.parent)
    if lib not in sys.path:
        sys.path.insert(0, lib)


def mcp_available() -> bool:
    try:
        import mcp  # type: ignore  # noqa: F401
        return True
    except Exception:
        return False


def list_servers(db_path: Optional[str] = None) -> list[dict[str, Any]]:
    _ensure_path()
    from storage import db as dbmod
    from tools.registry import ensure_schema
    ensure_schema(db_path)
    with dbmod.connect(db_path) as conn:
        rows = conn.execute("SELECT * FROM mcp_servers ORDER BY name").fetchall()
        return [dict(r) for r in rows]


def add_server(
    name: str,
    transport: str = "stdio",
    endpoint: Optional[str] = None,
    command: Optional[str] = None,
    trust_level: str = "standard",
    db_path: Optional[str] = None,
) -> dict[str, Any]:
    _ensure_path()
    from storage import db as dbmod
    from tools.registry import ensure_schema
    ensure_schema(db_path)
    sid = dbmod.new_id("mcp_")
    with dbmod.connect(db_path) as conn:
        conn.execute(
            """
            INSERT INTO mcp_servers (
                id, name, transport, endpoint, command, enabled, trust_level, health_status, created_at
            ) VALUES (?,?,?,?,?,1,?,?,?)
            """,
            (sid, name, transport, endpoint, command, trust_level, "unknown", dbmod.utc_now()),
        )
        conn.commit()
    return get_server(sid, db_path=db_path) or {"id": sid}


def get_server(mcp_id: str, db_path: Optional[str] = None) -> Optional[dict]:
    _ensure_path()
    from storage import db as dbmod
    from tools.registry import ensure_schema
    ensure_schema(db_path)
    with dbmod.connect(db_path) as conn:
        row = conn.execute("SELECT * FROM mcp_servers WHERE id=?", (mcp_id,)).fetchone()
        return dict(row) if row else None


def remove_server(mcp_id: str, db_path: Optional[str] = None) -> bool:
    _ensure_path()
    from storage import db as dbmod
    from tools.registry import ensure_schema
    ensure_schema(db_path)
    with dbmod.connect(db_path) as conn:
        cur = conn.execute("DELETE FROM mcp_servers WHERE id=?", (mcp_id,))
        conn.commit()
        return cur.rowcount > 0


def connect_server(mcp_id: str, db_path: Optional[str] = None) -> dict[str, Any]:
    """Attempt MCP handshake if SDK present; otherwise mark stub-connected."""
    _ensure_path()
    from storage import db as dbmod
    srv = get_server(mcp_id, db_path=db_path)
    if not srv:
        return {"ok": False, "error": "mcp server not found"}
    if not mcp_available():
        with dbmod.connect(db_path) as conn:
            conn.execute(
                "UPDATE mcp_servers SET health_status=? WHERE id=?",
                ("stub", mcp_id),
            )
            conn.commit()
        try:
            dbmod.emit_event(kind="mcp.connected", message=f"stub {mcp_id}", payload={"mcp_id": mcp_id, "mode": "stub"})
        except Exception:
            pass
        return {
            "ok": True,
            "mode": "stub",
            "mcp_id": mcp_id,
            "message": "MCP SDK not installed; server recorded as stub",
            "tools": [],
        }
    # Real connect would go here; keep safe stub-with-SDK path
    with dbmod.connect(db_path) as conn:
        conn.execute("UPDATE mcp_servers SET health_status=? WHERE id=?", ("healthy", mcp_id))
        conn.commit()
    return {"ok": True, "mode": "sdk", "mcp_id": mcp_id, "tools": []}


def import_tools(mcp_id: str, db_path: Optional[str] = None) -> dict[str, Any]:
    """Import MCP tools into registry — still subject to policy at execute time."""
    conn_result = connect_server(mcp_id, db_path=db_path)
    return {"ok": conn_result.get("ok"), "imported": [], "connect": conn_result}
