"""Golden: tool git.status — real tool call, fast."""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from typing import Any


def validate(definition=None, context=None, case_dir=None, **kwargs) -> dict[str, Any]:
    definition = definition or {}
    cwd = definition.get("cwd") or "/workspace/projects/demo-python"
    path = Path(cwd)
    path.mkdir(parents=True, exist_ok=True)
    if not (path / ".git").exists():
        subprocess.run(["git", "init"], cwd=str(path), check=True, capture_output=True)
        subprocess.run(["git", "config", "user.email", "box@agentbox.local"], cwd=str(path), capture_output=True)
        subprocess.run(["git", "config", "user.name", "box"], cwd=str(path), capture_output=True)

    # Prefer AgentBox tool runtime; fall back to raw git
    try:
        lib = Path(__file__).resolve().parents[3] / "lib"
        if str(lib) not in sys.path:
            sys.path.insert(0, str(lib))
        from tools import registry
        from tools.executor import execute_tool
        registry.ensure_builtins()
        r = execute_tool("git.status", {"cwd": str(path), "porcelain": True})
        ok = bool(r.get("ok") or r.get("status") == "completed") and r.get("decision") != "deny"
        return {
            "ok": ok,
            "success": ok,
            "scores": {"correctness": 1.0 if ok else 0.0, "safety": 1.0, "tool reliability": 1.0 if ok else 0.0},
            "metrics": {"duration_ms": r.get("duration_ms"), "exit_code": r.get("exit_code")},
            "artifacts": {"tool_status": r.get("status"), "decision": r.get("decision")},
            "error": None if ok else str(r.get("error") or r.get("status")),
        }
    except Exception as e:
        # raw fallback
        proc = subprocess.run(["git", "status", "--porcelain"], cwd=str(path), capture_output=True, text=True)
        ok = proc.returncode == 0
        return {
            "ok": ok,
            "success": ok,
            "scores": {"correctness": 1.0 if ok else 0.0},
            "metrics": {"exit_code": proc.returncode},
            "artifacts": {"fallback": "raw_git", "stdout": proc.stdout[:500]},
            "error": None if ok else (proc.stderr or str(e)),
        }
