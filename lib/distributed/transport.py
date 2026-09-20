"""HTTP transport helpers (Control Plane <-> Worker)."""
from __future__ import annotations

import json
import urllib.error
import urllib.request
from typing import Any, Optional


def http_json(
    method: str,
    url: str,
    body: Optional[dict] = None,
    token: Optional[str] = None,
    timeout: float = 15.0,
) -> dict[str, Any]:
    data = None
    headers = {"Accept": "application/json", "User-Agent": "agentbox-worker/5.1"}
    if body is not None:
        data = json.dumps(body).encode("utf-8")
        headers["Content-Type"] = "application/json"
    if token:
        headers["Authorization"] = f"Bearer {token}"
    req = urllib.request.Request(url, data=data, headers=headers, method=method.upper())
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8") or "{}"
            return json.loads(raw)
    except urllib.error.HTTPError as e:
        err_body = e.read().decode("utf-8", errors="replace")
        try:
            parsed = json.loads(err_body)
        except Exception:
            parsed = {"error": {"message": err_body or str(e)}}
        parsed["_http_status"] = e.code
        raise RuntimeError(json.dumps(parsed)) from e
