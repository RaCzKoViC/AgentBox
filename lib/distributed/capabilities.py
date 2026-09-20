"""Capability discovery and matching for workers."""
from __future__ import annotations

import json
import os
import platform
import shutil
from typing import Any, Optional


def probe_local() -> dict[str, Any]:
    """Probe this host's capabilities (used by loopback worker)."""
    cpu = os.cpu_count() or 1
    mem_gb = 0.0
    disk_free_gb = 0.0
    try:
        import psutil
        mem_gb = round(psutil.virtual_memory().total / (1024**3), 2)
        disk_free_gb = round(psutil.disk_usage("/").free / (1024**3), 2)
    except Exception:
        pass
    providers = []
    if shutil.which("codex"):
        providers.append("codex")
    providers.append("stub")
    return {
        "cpu": cpu,
        "cpu_count": cpu,
        "memory_gb": mem_gb,
        "memory_total": mem_gb,
        "disk_free": disk_free_gb,
        "architecture": platform.machine(),
        "platform": platform.system().lower(),
        "docker": bool(shutil.which("docker")),
        "git": bool(shutil.which("git")),
        "python": True,
        "node": bool(shutil.which("node")),
        "rust": bool(shutil.which("rustc")),
        "go": bool(shutil.which("go")),
        "gpu": False,
        "cuda": False,
        "providers": providers,
    }


def parse_caps(raw: Any) -> dict[str, Any]:
    if raw is None:
        return {}
    if isinstance(raw, dict):
        return raw
    if isinstance(raw, str):
        try:
            return json.loads(raw) or {}
        except Exception:
            return {}
    return {}


def matches(caps: dict[str, Any], requirements: Optional[dict[str, Any]]) -> tuple[bool, list[str]]:
    """Return (ok, reasons). requirements may include requires_* flags and required_labels."""
    req = requirements or {}
    reasons: list[str] = []
    checks = [
        ("requires_gpu", "gpu"),
        ("requires_docker", "docker"),
        ("requires_rust", "rust"),
        ("requires_node", "node"),
        ("requires_git", "git"),
    ]
    for flag, key in checks:
        if req.get(flag):
            if not caps.get(key):
                return False, [f"missing capability: {key}"]
            reasons.append(f"{key} capability")
    min_mem = req.get("min_memory_gb")
    if min_mem is not None:
        have = float(caps.get("memory_gb") or caps.get("memory_total") or 0)
        if have < float(min_mem):
            return False, [f"memory {have}GB < required {min_mem}GB"]
        reasons.append(f"memory>={min_mem}GB")
    pref = req.get("preferred_provider")
    if pref:
        providers = caps.get("providers") or []
        if pref not in providers and pref != "stub":
            return False, [f"provider {pref} unavailable"]
        reasons.append(f"provider {pref}")
    return True, reasons or ["basic match"]
