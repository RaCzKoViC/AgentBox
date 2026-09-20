#!/usr/bin/env python3
"""Path guards, shell allowlist/denylist, sandbox profiles."""
from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any, Optional

ALLOWED_ROOTS = (
    "/workspace",
    str(Path.home() / ".local" / "share" / "agentbox-v5"),
    str(Path.home() / ".local" / "share" / "agentbox" / "v5"),
    str(Path.home() / ".config" / "agentbox-v5"),
)

# Safe allowlist prefixes for shell.run in safe mode
SHELL_ALLOWLIST = (
    "git status", "git diff", "git log", "git branch", "git show", "git rev-parse",
    "ls", "pwd", "echo", "cat ", "head ", "tail ", "wc ", "true", "false",
    "python3 -c", "python3 --version", "node --version", "npm --version",
    "docker ps", "docker images", "docker version", "docker info",
    "curl -sI", "curl --version", "which ", "command -v", "uname", "date",
    "pytest", "make test", "make check",
)

SHELL_DENY_PATTERNS = [
    r"\brm\s+(-[a-zA-Z]*f|-[a-zA-Z]*r).*",
    r"\brm\s+-rf\b",
    r"\bsudo\b",
    r"\bdd\b",
    r"\bmkfs\b",
    r"\bshutdown\b",
    r"\breboot\b",
    r"\biptables\b",
    r"\bnft\b",
    r"git\s+reset\s+--hard",
    r"git\s+clean\s+-fd",
    r"git\s+push\s+.*--force",
    r"git\s+push\s+-f\b",
    r"docker\s+system\s+prune",
    r"docker\s+run\s+.*--privileged",
    r">\s*/etc/",
    r"\bchmod\s+777\b",
    r"\bchown\b.*/",
    r"\bcurl\b.*\|\s*(ba)?sh",
    r"\bwget\b.*\|\s*(ba)?sh",
    r"\bmkfs\.",
    r":\(\)\s*\{\s*:\|:&\s*\};:",
]


def resolve_allowed_path(path: str, workspace: Optional[str] = None) -> Path:
    """Resolve path and ensure it stays under allowed roots (esp. /workspace)."""
    ws = workspace or os.environ.get("AGENTBOX_WORKSPACE") or "/workspace"
    raw = Path(path).expanduser()
    if not raw.is_absolute():
        raw = Path(ws) / raw
    resolved = raw.resolve()
    allowed = [Path(ws).resolve()] + [Path(r).resolve() for r in ALLOWED_ROOTS]
    # also allow /tmp for scratch in tests
    allowed.append(Path("/tmp").resolve())
    ok = False
    for root in allowed:
        try:
            resolved.relative_to(root)
            ok = True
            break
        except ValueError:
            continue
    if not ok:
        raise PermissionError(f"path outside allowed roots: {resolved}")
    return resolved


def shell_risk(command: str) -> dict[str, Any]:
    """Parse shell command for deny / high-risk patterns."""
    cmd = (command or "").strip()
    low = cmd.lower()
    reasons = []
    level = "LOW"
    denied = False
    for pat in SHELL_DENY_PATTERNS:
        if re.search(pat, cmd, re.IGNORECASE):
            denied = True
            level = "CRITICAL" if any(x in low for x in ("rm -rf", "mkfs", "shutdown", "reboot", "--force", "privileged")) else "HIGH"
            reasons.append(f"denylist matched: {pat}")
            break
    if denied:
        return {"level": level, "denied": True, "reasons": reasons, "allowlisted": False}

    allowlisted = False
    for prefix in SHELL_ALLOWLIST:
        if low == prefix.lower() or low.startswith(prefix.lower()):
            allowlisted = True
            break
    if not allowlisted:
        level = "HIGH"
        reasons.append("command not on allowlist → HIGH risk / approval required")
    else:
        level = "LOW"
        reasons.append("allowlisted safe command")
    return {"level": level, "denied": False, "reasons": reasons, "allowlisted": allowlisted}


def sandbox_profile_for(tool_id: str, risk_level: str = "LOW") -> str:
    if tool_id.startswith("file.read") or risk_level == "LOW":
        return "readonly"
    if tool_id.startswith("file.write"):
        return "workspace-write"
    if tool_id.startswith("http."):
        return "network-limited"
    if tool_id.startswith("docker."):
        return "docker"
    if risk_level in ("HIGH", "CRITICAL"):
        return "high-risk-isolated"
    return "workspace-write"
