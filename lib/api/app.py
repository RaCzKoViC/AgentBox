"""AgentBox v5.5 Control Plane FastAPI application."""
from __future__ import annotations

import secrets
import sys
import time
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

LIB_ROOT = Path(__file__).resolve().parent.parent
if str(LIB_ROOT) not in sys.path:
    sys.path.insert(0, str(LIB_ROOT))

from api.deps import is_tailscale_addr, load_web_config, version_str
from api.errors import APIError, handle_api_error, handle_unhandled
from api.websocket import router as ws_router

WEB_ROOT = Path(__file__).resolve().parent.parent / "web"
if not (WEB_ROOT / "templates").is_dir():
    alt = Path(__file__).resolve().parent.parent.parent / "web"
    if (alt / "templates").is_dir():
        WEB_ROOT = alt


def create_app() -> FastAPI:
    cfg = load_web_config()
    docs = cfg.getboolean("security", "docs_enabled", fallback=False)
    app = FastAPI(
        title="AgentBox Control Plane",
        version=version_str(),
        docs_url="/docs" if docs else None,
        redoc_url=None,
        openapi_url="/openapi.json" if docs else None,
    )
    app.add_exception_handler(APIError, handle_api_error)
    app.add_exception_handler(Exception, handle_unhandled)

    @app.middleware("http")
    async def security_middleware(request: Request, call_next):
        request.state.request_id = "req_" + secrets.token_hex(6)
        request.state.start = time.time()
        response = await call_next(request)
        response.headers["X-Request-Id"] = getattr(request.state, "request_id", "")
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "same-origin"
        return response

    from api.routes import (
        health, status, tasks, runs, agents, handoffs, approvals,
        policies, budgets, risk, artifacts, memory, metrics, logs,
        providers, projects, settings, auth_routes, workers, intelligence, planning, tools, eval, ops,
    )
    for mod in (
        health, status, tasks, runs, agents, handoffs, approvals,
        policies, budgets, risk, artifacts, memory, metrics, logs,
        providers, projects, settings, auth_routes, workers, intelligence, planning, tools, eval, ops,
    ):
        app.include_router(mod.router)

    app.include_router(ws_router)

    static_dir = WEB_ROOT / "static"
    templates_dir = WEB_ROOT / "templates"
    static_dir.mkdir(parents=True, exist_ok=True)
    templates_dir.mkdir(parents=True, exist_ok=True)
    app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")
    templates = Jinja2Templates(directory=str(templates_dir))

    @app.get("/", response_class=HTMLResponse)
    async def index(request: Request):
        return templates.TemplateResponse(
            request,
            "index.html",
            {
                "title": cfg.get("ui", "title", fallback="AgentBox"),
                "version": version_str(),
            },
        )

    @app.get("/login", response_class=HTMLResponse)
    async def login_page(request: Request):
        return templates.TemplateResponse(
            request,
            "login.html",
            {"title": "Login — AgentBox", "version": version_str()},
        )

    return app


app = create_app()
