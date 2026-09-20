#!/usr/bin/env python3
"""Safe read-only tool discovery (PATH binaries, docker, MCP stubs)."""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any, Optional

_HERE = Path(__file__).resolve().parent

SAFE_BINARIES = (
    "git", "docker", "rsync", "ssh", "scp", "sftp", "tailscale",
    "curl", "wget", "python3", "node", "npm", "pip", "cargo", "go",
    "make", "cmake", "pytest",
)


def _ensure_path() -> None:
    lib = str(_HERE.parent)
    if lib not in sys.path:
        sys.path.insert(0, lib)


def _which(name: str) -> Optional[str]:
    return shutil.which(name)


def discover_binaries() -> list[dict[str, Any]]:
    found = []
    for name in SAFE_BINARIES:
        path = _which(name)
        if not path:
            continue
        version = ""
        try:
            # read-only version probes only
            if name == "git":
                r = subprocess.run([path, "--version"], capture_output=True, text=True, timeout=5)
                version = (r.stdout or r.stderr or "").strip()
            elif name == "docker":
                r = subprocess.run([path, "--version"], capture_output=True, text=True, timeout=5)
                version = (r.stdout or "").strip()
            elif name == "ssh":
                r = subprocess.run([path, "-V"], capture_output=True, text=True, timeout=5)
                version = (r.stderr or r.stdout or "").strip()
            else:
                r = subprocess.run([path, "--version"], capture_output=True, text=True, timeout=5)
                version = ((r.stdout or r.stderr or "").splitlines() or [""])[0].strip()
        except Exception as exc:
            version = f"probe_error:{exc}"
        found.append({
            "binary": name,
            "path": path,
            "version": version,
            "source": "PATH",
        })
    return found


def discover_adapters() -> list[dict[str, Any]]:
    _ensure_path()
    from tools.registry import manifests_dir, load_manifest_file
    out = []
    mdir = manifests_dir()
    if not mdir.is_dir():
        return out
    for path in sorted(mdir.glob("*.json")):
        try:
            man = load_manifest_file(path)
            out.append({
                "id": man.get("id"),
                "category": man.get("category"),
                "source": "adapter",
                "path": str(path),
                "capabilities": man.get("capabilities") or [],
            })
        except Exception as exc:
            out.append({"path": str(path), "error": str(exc), "source": "adapter"})
    return out


def discover_docker_present() -> bool:
    return _which("docker") is not None


def discover(register: bool = True, db_path: Optional[str] = None) -> dict[str, Any]:
    """Run safe discovery. Never installs packages. Optionally registers builtins."""
    _ensure_path()
    from tools import registry
    binaries = discover_binaries()
    adapters = discover_adapters()
    registered = []
    if register:
        registered = registry.ensure_builtins(db_path=db_path)
        # mark docker.ps health based on presence
        if discover_docker_present():
            registry.set_health("docker.ps", "healthy", db_path=db_path)
        else:
            # keep registered but unavailable
            try:
                registry.set_health("docker.ps", "unavailable", db_path=db_path)
            except Exception:
                pass
        for b in binaries:
            if b["binary"] == "git":
                registry.set_health("git.status", "healthy", db_path=db_path)
                registry.set_health("git.diff", "healthy", db_path=db_path)
    try:
        from storage import db as dbmod
        dbmod.emit_event(
            kind="tool.discovered",
            message=f"discovered {len(binaries)} binaries, {len(adapters)} adapters",
            payload={"binaries": [b["binary"] for b in binaries]},
            db_path=db_path,
        )
    except Exception:
        pass
    return {
        "binaries": binaries,
        "adapters": adapters,
        "registered": [
            (r.get("id") if isinstance(r, dict) else None) for r in registered if isinstance(r, dict)
        ],
        "docker_present": discover_docker_present(),
        "mcp": [],  # filled by mcp_client if available
    }


def health_check_tool(tool_id: str, db_path: Optional[str] = None) -> dict[str, Any]:
    _ensure_path()
    from tools import registry
    tool = registry.get_tool(tool_id, db_path=db_path)
    if not tool:
        return {"tool_id": tool_id, "status": "unavailable", "error": "not registered"}
    status = "healthy"
    details: dict[str, Any] = {}
    try:
        if tool_id.startswith("git."):
            path = _which("git")
            if not path:
                status = "unavailable"
            else:
                r = subprocess.run([path, "--version"], capture_output=True, text=True, timeout=5)
                details["version"] = (r.stdout or "").strip()
        elif tool_id.startswith("docker."):
            path = _which("docker")
            if not path:
                status = "unavailable"
            else:
                r = subprocess.run([path, "info"], capture_output=True, text=True, timeout=10)
                status = "healthy" if r.returncode == 0 else "degraded"
                details["exit_code"] = r.returncode
        elif tool_id.startswith("http."):
            status = "healthy"
        elif tool_id.startswith("file.") or tool_id.startswith("shell."):
            status = "healthy"
        else:
            status = tool.get("health_status") or "unknown"
    except Exception as exc:
        status = "degraded"
        details["error"] = str(exc)
    registry.set_health(tool_id, status, db_path=db_path)
    return {"tool_id": tool_id, "status": status, "details": details}


def health_all(db_path: Optional[str] = None) -> list[dict[str, Any]]:
    _ensure_path()
    from tools import registry
    registry.ensure_builtins(db_path=db_path)
    return [health_check_tool(t["id"], db_path=db_path) for t in registry.list_tools(db_path=db_path)]
