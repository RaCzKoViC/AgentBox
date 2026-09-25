#!/usr/bin/env python3
"""Shared utilities for skill-creator scripts."""
from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import tempfile
import time
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

try:
    import yaml
except ImportError:  # pragma: no cover
    yaml = None

MAX_SKILL_NAME_LENGTH = 64
MAX_DESCRIPTION_LENGTH = 1024
NAME_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
GENERIC_DESCRIPTIONS = {
    "helps with development.",
    "helps with development",
    "a helpful skill.",
    "a helpful skill",
    "utility skill",
    "general purpose skill",
    "does things",
}

SECRET_PATTERNS = [
    (re.compile(r"(?i)(api[_-]?key|apikey)\s*[:=]\s*['\"]?[A-Za-z0-9_\-]{16,}"), "api_key_assignment"),
    (re.compile(r"(?i)(secret|password|passwd|token)\s*[:=]\s*['\"][^'\"]{8,}['\"]"), "credential_assignment"),
    (re.compile(r"-----BEGIN (?:RSA |OPENSSH |EC )?PRIVATE KEY-----"), "private_key_pem"),
    (re.compile(r"(?i)Bearer\s+[A-Za-z0-9\-_\.]{20,}"), "bearer_token"),
    (re.compile(r"ghp_[A-Za-z0-9]{20,}"), "github_pat"),
    (re.compile(r"sk-[A-Za-z0-9]{20,}"), "openai_like_key"),
]

DANGEROUS_CMD_PATTERNS = [
    # Require command-like usage to avoid flagging security documentation.
    (re.compile(r"(?m)(?:^|[;&|`]|\bos\.system\(|subprocess\.[a-z]+\([^\n]*)\s*sudo\s+"), "sudo"),
    (re.compile(r"(?m)(?:^|[;&|`])\s*rm\s+-rf\s+/(?:\s|$)"), "rm_rf_rootish"),
    (re.compile(r"git\s+push\s+[^\n]*--force"), "force_push"),
    (re.compile(r"curl\s+[^\n|]*\|\s*(?:ba)?sh"), "curl_pipe_shell"),
]

BACKUP_ROOT = Path.home() / ".local" / "share" / "agentbox" / "skill-backups"
AUDIT_LOG = Path.home() / ".local" / "share" / "agentbox" / "skill-creator-audit.jsonl"


@dataclass
class Finding:
    level: str  # PASS WARN FAIL INFO
    code: str
    message: str
    path: str = ""


@dataclass
class ValidationResult:
    status: str  # PASS WARN FAIL
    findings: list[Finding] = field(default_factory=list)
    meta: dict[str, Any] = field(default_factory=dict)

    def add(self, level: str, code: str, message: str, path: str = "") -> None:
        self.findings.append(Finding(level, code, message, path))

    def finalize(self) -> "ValidationResult":
        levels = {f.level for f in self.findings}
        if "FAIL" in levels:
            self.status = "FAIL"
        elif "WARN" in levels:
            self.status = "WARN"
        else:
            self.status = "PASS"
        return self

    def exit_code(self) -> int:
        return 0 if self.status in ("PASS", "WARN") else 1

    def to_dict(self) -> dict:
        return {
            "status": self.status,
            "findings": [asdict(f) for f in self.findings],
            "meta": self.meta,
        }


def now_iso() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def scope_paths(repo_root: Optional[Path] = None) -> dict[str, Path]:
    home = Path.home()
    repo = Path(repo_root) if repo_root else Path.cwd()
    return {
        "USER": home / ".agents" / "skills",
        "REPO": repo / ".agents" / "skills",
        "ADMIN": Path("/etc/codex/skills"),
        "SYSTEM": home / ".codex" / "skills" / ".system",
    }


def resolve_scope_dir(scope: str, repo_root: Optional[Path] = None) -> Path:
    scope = scope.upper()
    paths = scope_paths(repo_root)
    if scope not in paths:
        raise ValueError(f"Unknown scope: {scope}")
    if scope == "SYSTEM":
        raise PermissionError("SYSTEM/bundled skills must not be modified by skill-creator")
    if scope == "ADMIN":
        target = paths["ADMIN"]
        if not os.access(target.parent if not target.exists() else target, os.W_OK):
            raise PermissionError(f"ADMIN scope not writable: {target}")
    return paths[scope]


def normalize_skill_name(name: str) -> str:
    normalized = name.strip().lower()
    normalized = re.sub(r"[^a-z0-9]+", "-", normalized)
    normalized = re.sub(r"-{2,}", "-", normalized).strip("-")
    return normalized


def validate_skill_name(name: str) -> tuple[bool, str]:
    if not name or not isinstance(name, str):
        return False, "Name is required"
    name = name.strip()
    if len(name) > MAX_SKILL_NAME_LENGTH:
        return False, f"Name too long ({len(name)} > {MAX_SKILL_NAME_LENGTH})"
    if not NAME_RE.match(name):
        return False, (
            "Name must be kebab-case: lowercase letters, digits, single hyphens; "
            "no leading/trailing/consecutive hyphens"
        )
    if name != normalize_skill_name(name):
        return False, f"Name should be normalized as '{normalize_skill_name(name)}'"
    return True, "ok"


def parse_frontmatter(text: str) -> tuple[dict, str, Optional[str]]:
    """Return (frontmatter_dict, body, error)."""
    if not text.startswith("---"):
        return {}, text, "No YAML frontmatter found"
    match = re.match(r"^---\s*\n(.*?)\n---\s*\n?", text, re.DOTALL)
    if not match:
        return {}, text, "Invalid frontmatter format"
    raw = match.group(1)
    body = text[match.end():]
    if yaml is None:
        return {}, body, "PyYAML is required to parse frontmatter"
    try:
        data = yaml.safe_load(raw)
    except Exception as exc:  # noqa: BLE001
        return {}, body, f"Invalid YAML in frontmatter: {exc}"
    if data is None:
        data = {}
    if not isinstance(data, dict):
        return {}, body, "Frontmatter must be a YAML mapping"
    return data, body, None


def description_quality_warnings(description: str) -> list[str]:
    warns = []
    d = (description or "").strip()
    if not d:
        return warns
    if d.lower() in GENERIC_DESCRIPTIONS:
        warns.append("Description is too generic; front-load triggers and boundaries")
    if len(d) < 40:
        warns.append("Description is very short; include when to use and when not to")
    if "when" not in d.lower() and "use" not in d.lower():
        warns.append("Description should explain when the skill should activate")
    trigger_words = ("create", "validate", "skill", "package", "test", "inspect", "update")
    if not any(w in d.lower() for w in trigger_words):
        warns.append("Consider front-loading capability keywords for discovery")
    return warns


def file_sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def dir_fingerprint(path: Path) -> str:
    h = hashlib.sha256()
    if not path.exists():
        return h.hexdigest()
    for p in sorted(path.rglob("*")):
        if p.is_file() and "__pycache__" not in p.parts and not p.name.endswith(".pyc"):
            rel = str(p.relative_to(path)).encode()
            h.update(rel)
            h.update(file_sha256(p).encode())
    return h.hexdigest()


def audit(operation: str, skill: str, scope: str, result: str, summary: str = "") -> None:
    AUDIT_LOG.parent.mkdir(parents=True, exist_ok=True)
    entry = {
        "timestamp": now_iso(),
        "operation": operation,
        "skill": skill,
        "scope": scope,
        "result": result,
        "summary": summary,
    }
    with AUDIT_LOG.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\n")


def emit_event(name: str, payload: Optional[dict] = None) -> None:
    """Best-effort AgentBox event bus hook; no-op if unavailable."""
    try:
        from agentbox_events import emit  # type: ignore

        emit(name, payload or {})
    except Exception:
        pass


def backup_skill(skill_dir: Path, reason: str = "update") -> Optional[Path]:
    if not skill_dir.exists():
        return None
    BACKUP_ROOT.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%dT%H%M%S")
    name = skill_dir.name
    dest = BACKUP_ROOT / f"{name}-{ts}-{reason}"
    shutil.copytree(skill_dir, dest, ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
    meta = {
        "timestamp": now_iso(),
        "source": str(skill_dir),
        "reason": reason,
        "sha256": dir_fingerprint(dest),
        "summary": f"Backup of {name} before {reason}",
    }
    (dest / ".backup-meta.json").write_text(json.dumps(meta, indent=2) + "\n", encoding="utf-8")
    return dest


def restore_backup(backup_dir: Path, target_dir: Path) -> None:
    if target_dir.exists():
        shutil.rmtree(target_dir)
    shutil.copytree(
        backup_dir,
        target_dir,
        ignore=shutil.ignore_patterns(".backup-meta.json"),
    )


def atomic_install(src_dir: Path, dest_dir: Path) -> None:
    dest_dir.parent.mkdir(parents=True, exist_ok=True)
    tmp_parent = dest_dir.parent
    with tempfile.TemporaryDirectory(dir=tmp_parent) as td:
        staging = Path(td) / dest_dir.name
        shutil.copytree(src_dir, staging)
        if dest_dir.exists():
            bak = dest_dir.with_name(dest_dir.name + f".old-{int(time.time())}")
            dest_dir.rename(bak)
            try:
                staging.rename(dest_dir)
            except Exception:
                bak.rename(dest_dir)
                raise
            shutil.rmtree(bak, ignore_errors=True)
        else:
            staging.rename(dest_dir)


def scan_secrets(text: str) -> list[str]:
    hits = []
    for pat, label in SECRET_PATTERNS:
        if pat.search(text):
            hits.append(label)
    return hits


def scan_dangerous_commands(text: str) -> list[str]:
    hits = []
    for pat, label in DANGEROUS_CMD_PATTERNS:
        if pat.search(text):
            hits.append(label)
    return hits


def title_case(name: str) -> str:
    return " ".join(w.capitalize() for w in name.split("-"))


def find_skill_collisions(name: str, repo_root: Optional[Path] = None) -> list[dict]:
    found = []
    for scope, base in scope_paths(repo_root).items():
        candidate = base / name
        if candidate.exists() and (candidate / "SKILL.md").exists():
            found.append({"scope": scope, "path": str(candidate)})
    return found


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
