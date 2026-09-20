from __future__ import annotations
from typing import Any, Optional
from fastapi import Request
from fastapi.responses import JSONResponse

class APIError(Exception):
    def __init__(self, code: str, message: str, status_code: int = 400, details: Optional[dict] = None):
        self.code = code
        self.message = message
        self.status_code = status_code
        self.details = details or {}
        super().__init__(message)

    def body(self, request_id: Optional[str] = None) -> dict[str, Any]:
        out = {"error": {"code": self.code, "message": self.message, "details": self.details}}
        if request_id:
            out["request_id"] = request_id
        return out

async def handle_api_error(request: Request, exc: APIError) -> JSONResponse:
    rid = getattr(request.state, "request_id", None)
    return JSONResponse(status_code=exc.status_code, content=exc.body(rid))

async def handle_unhandled(request: Request, exc: Exception) -> JSONResponse:
    rid = getattr(request.state, "request_id", None)
    body: dict[str, Any] = {"error": {"code": "INTERNAL_ERROR", "message": "Internal server error", "details": {}}}
    if rid:
        body["request_id"] = rid
    return JSONResponse(status_code=500, content=body)
