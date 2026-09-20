from __future__ import annotations
from fastapi import APIRouter, Depends, Request, Response
from ..auth import (
    COOKIE_NAME,
    create_session,
    ensure_admin_token,
    list_sessions,
    revoke_session,
    verify_admin_token,
)
from ..deps import Actor, db_connect, get_actor, load_web_config, require_role, audit
from ..errors import APIError
from ..schemas import LoginIn

router = APIRouter(tags=["auth"])

@router.post("/api/v1/auth/login")
def login(body: LoginIn, request: Request, response: Response):
    if not verify_admin_token(body.token):
        audit("POST", "/api/v1/auth/login", None, 401, remote=request.client.host if request.client else "")
        raise APIError("AUTH_FAILED", "Invalid token", status_code=401)
    cfg = load_web_config()
    timeout = cfg.getint("security", "session_timeout_minutes", fallback=120)
    conn = db_connect()
    try:
        ensure_admin_token()
        sid, raw = create_session(conn, role="admin", timeout_minutes=timeout)
    finally:
        conn.close()
    response.set_cookie(key=COOKIE_NAME, value=raw, httponly=True, samesite="lax", max_age=timeout * 60, path="/")
    audit("POST", "/api/v1/auth/login", Actor("admin", "login"), 200, remote=request.client.host if request.client else "")
    return {"ok": True, "role": "admin", "session_id": sid}

@router.post("/api/v1/auth/logout")
def logout(response: Response, actor: Actor = Depends(get_actor)):
    if actor.session_id:
        conn = db_connect()
        try:
            revoke_session(conn, actor.session_id)
        finally:
            conn.close()
    response.delete_cookie(COOKIE_NAME, path="/")
    return {"ok": True}

@router.get("/api/v1/auth/sessions")
def sessions(actor: Actor = Depends(require_role("admin"))):
    conn = db_connect()
    try:
        return {"items": list_sessions(conn)}
    finally:
        conn.close()

@router.post("/api/v1/auth/sessions/{session_id}/revoke")
def revoke(session_id: str, actor: Actor = Depends(require_role("admin"))):
    conn = db_connect()
    try:
        ok = revoke_session(conn, session_id)
        return {"ok": ok}
    finally:
        conn.close()

@router.get("/api/v1/auth/me")
def me(actor: Actor = Depends(get_actor)):
    return {"role": actor.role, "actor": actor.actor, "session_id": actor.session_id}
