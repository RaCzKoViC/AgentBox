"""Execute assigned tasks — wraps stub/codex runner when available."""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Any, Optional


def execute_assignment(assignment: dict[str, Any], *, use_stub: bool = True) -> dict[str, Any]:
    """Run a smoke/stub task for an assignment. Returns result dict."""
    task_id = assignment.get("task_id") or "unknown"
    payload = assignment.get("payload") or {}
    if isinstance(payload, str):
        try:
            payload = json.loads(payload)
        except Exception:
            payload = {}
    mode = payload.get("mode") or ("stub" if use_stub else "codex")
    if mode == "stub" or use_stub:
        return {
            "ok": True,
            "mode": "stub",
            "task_id": task_id,
            "assignment_id": assignment.get("id"),
            "message": "stub execution complete",
            "output": f"smoke OK for {task_id}",
        }
    # best-effort: invoke agent5 run if present
    try:
        r = subprocess.run(
            ["agent5", "run", "list"],
            capture_output=True, text=True, timeout=30,
        )
        return {
            "ok": r.returncode == 0,
            "mode": "codex-wrap",
            "task_id": task_id,
            "stdout": (r.stdout or "")[:2000],
            "stderr": (r.stderr or "")[:500],
        }
    except Exception as e:
        return {"ok": False, "mode": "error", "error": str(e), "task_id": task_id}
