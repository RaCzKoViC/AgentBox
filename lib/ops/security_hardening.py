#!/usr/bin/env python3
"""Security hardening checks — token perms, bind notes, no secrets in logs."""
from __future__ import annotations

import json
import os
import re
import stat
import sys
from pathlib import Path
from typing import Any, Optional

_HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(_HERE.parent))

from ops.paths import config_dir, data_home, logs_dir  # noqa: E402

TOKEN_PATH = Path.home() / ".config" / "agentbox-v5" / "secrets" / "admin.token"

SECRET_PATTERNS = [
    # assignment-style secrets (skip already redacted)
    re.compile(r"(?i)(api[_-]?key|password|secret)\s*[:=]\s*(?!\[REDACTED\])\S+"),
    re.compile(r"(?i)bearer\s+(?!\[REDACTED\])[A-Za-z0-9._\-]{16,}"),
    re.compile(r"(?i)[?&]token=(?!\[REDACTED\])[A-Za-z0-9._\-]{16,}"),
    re.compile(r"sk-[A-Za-z0-9]{20,}"),
    re.compile(r"ghp_[A-Za-z0-9]{20,}"),
]


def check_token_perms() -> dict[str, Any]:
    if not TOKEN_PATH.is_file():
        return {"ok": True, "present": False, "note": "admin.token not created yet"}
    mode = TOKEN_PATH.stat().st_mode & 0o777
    ok = mode == 0o600
    return {"ok": ok, "present": True, "mode": oct(mode), "path": str(TOKEN_PATH)}


def check_web_bind() -> dict[str, Any]:
    notes = []
    ok = True
    web_ini = config_dir() / "web.ini"
    share = data_home() / "config"
    # also project
    for p in (web_ini, Path("/workspace/agentbox-v5/config/web.ini")):
        if p.is_file():
            text = p.read_text(encoding="utf-8", errors="replace")
            if "0.0.0.0" in text:
                notes.append(f"{p}: binds 0.0.0.0 — prefer Tailscale CGNAT 100.x or 127.0.0.1")
            if "100." in text or "127.0.0.1" in text:
                notes.append(f"{p}: Tailscale/localhost bind configured")
    return {"ok": ok, "notes": notes or ["no web.ini found — runtime may use defaults"]}



def scrub_log_files() -> int:
    """Best-effort redact tokens already written to log files."""
    n = 0
    for f in list(logs_dir().glob("*.log"))[:20]:
        try:
            raw = f.read_text(encoding="utf-8", errors="replace")
        except Exception:
            continue
        cleaned = redact(raw)
        if cleaned != raw:
            f.write_text(cleaned, encoding="utf-8")
            n += 1
    return n


def check_logs_for_secrets(sample_lines: int = 200, *, scrub: bool = True) -> dict[str, Any]:
    if scrub:
        scrub_log_files()
    hits = []
    for f in list(logs_dir().glob("*.log"))[:10]:
        try:
            lines = f.read_text(encoding="utf-8", errors="replace").splitlines()[-sample_lines:]
        except Exception:
            continue
        for i, line in enumerate(lines):
            for pat in SECRET_PATTERNS:
                if pat.search(line):
                    hits.append({"file": str(f), "line": i, "pattern": pat.pattern[:40]})
                    break
    return {"ok": len(hits) == 0, "hits": hits[:20]}


def redact(text: str) -> str:
    out = text
    out = re.sub(r"([?&]token=)[^&\s\"]+", r"\1[REDACTED]", out, flags=re.I)
    out = re.sub(r"(?i)(Bearer\s+)\S+", r"\1[REDACTED]", out)
    for pat in SECRET_PATTERNS:
        out = pat.sub("[REDACTED]", out)
    return out


def check_security() -> dict[str, Any]:
    token = check_token_perms()
    bind = check_web_bind()
    logs = check_logs_for_secrets()
    issues = []
    if not token.get("ok"):
        issues.append(f"token perms {token.get('mode')} (want 0o600)")
    if not logs.get("ok"):
        issues.append(f"possible secrets in logs: {len(logs.get('hits', []))} hits")
    return {
        "ok": token.get("ok", False) and logs.get("ok", False),
        "token": token,
        "web_bind": bind,
        "logs": logs,
        "issues": issues,
    }


def main(argv: Optional[list[str]] = None) -> int:
    print(json.dumps(check_security(), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
