#!/usr/bin/env python3
"""Environment doctor for skill-creator and skill discovery paths."""
from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import BACKUP_ROOT, scope_paths  # noqa: E402
from validate_skill import validate_skill  # noqa: E402

SKILL_ROOT = Path(__file__).resolve().parents[1]


def doctor(skill_path: Path | None = None) -> dict:
    skill_path = (skill_path or SKILL_ROOT).resolve()
    checks = []

    def add(name: str, ok: bool, detail: str = "", level: str = "PASS") -> None:
        checks.append({"name": name, "ok": ok, "detail": detail, "level": level if ok else "FAIL"})

    # Python
    add("python", sys.version_info >= (3, 10), sys.version.split()[0])
    try:
        import yaml  # noqa: F401

        add("pyyaml", True, "available")
    except ImportError:
        add("pyyaml", False, "PyYAML missing")

    # Tools
    codex_path = shutil.which("codex")
    add("codex_cli", True, codex_path or "not found (optional)", "PASS" if codex_path else "WARN")
    if not codex_path:
        checks[-1]["ok"] = True
    agent5_path = shutil.which("agent5")
    add("agent5", True, agent5_path or "not found (optional)", "PASS" if agent5_path else "WARN")
    if not agent5_path:
        checks[-1]["ok"] = True

    # Locations
    paths = scope_paths()
    for scope, base in paths.items():
        exists = base.exists()
        writable = os.access(base, os.W_OK) if exists else os.access(base.parent, os.W_OK)
        if scope == "SYSTEM":
            add(f"path_{scope}", exists, f"{base} (read-only expected)", "PASS" if exists else "WARN")
        elif scope == "ADMIN":
            add(f"path_{scope}", True, f"{base} exists={exists} writable={writable}", "WARN")
        else:
            add(f"path_{scope}", exists or scope in ("USER", "REPO"), f"{base} writable={writable}")

    # config.toml
    cfg = Path.home() / ".codex" / "config.toml"
    add("codex_config", True, str(cfg) + (" (present)" if cfg.exists() else " (missing)"), "PASS" if cfg.exists() else "WARN")
    if not cfg.exists():
        checks[-1]["ok"] = True

    # Backup dir
    try:
        BACKUP_ROOT.mkdir(parents=True, exist_ok=True)
        add("backup_dir", True, str(BACKUP_ROOT))
    except OSError as exc:
        add("backup_dir", False, str(exc))

    # Self skill validation
    v = validate_skill(skill_path)
    add("self_validate", v.status != "FAIL", f"status={v.status}")

    # Required layout
    required = [
        "SKILL.md",
        "README.md",
        "agents/openai.yaml",
        "scripts/create_skill.py",
        "scripts/validate_skill.py",
        "scripts/inspect_skill.py",
        "scripts/test_skill.py",
        "scripts/package_skill.py",
        "scripts/doctor.py",
        "schemas/skill.schema.json",
        "schemas/openai-yaml.schema.json",
    ]
    for rel in required:
        p = skill_path / rel
        add(f"file:{rel}", p.exists(), str(p))

    # Duplicate name awareness
    system = paths["SYSTEM"] / "skill-creator"
    user = paths["USER"] / "skill-creator"
    if system.exists() and user.exists() and system.resolve() != user.resolve():
        add(
            "duplicate_skill_creator",
            True,
            f"SYSTEM and USER both present; do not overwrite SYSTEM ({system})",
            "WARN",
        )
        checks[-1]["ok"] = True
        checks[-1]["level"] = "WARN"

    # Plugin tooling optional
    plugin_creator = paths["SYSTEM"] / "plugin-creator"
    add(
        "plugin_creator_available",
        plugin_creator.exists(),
        str(plugin_creator) if plugin_creator.exists() else "not found (optional)",
        "WARN",
    )
    if not plugin_creator.exists():
        checks[-1]["ok"] = True  # optional
        checks[-1]["level"] = "WARN"

    # Broken skills in USER
    broken = []
    user_root = paths["USER"]
    if user_root.exists():
        for d in user_root.iterdir():
            if d.is_dir() and not d.name.startswith("."):
                if not (d / "SKILL.md").exists() and d.name != "canvas":
                    # canvas may be sdk-only
                    if not any(d.rglob("SKILL.md")):
                        broken.append(str(d))
    add("no_broken_user_skills", len(broken) == 0, ",".join(broken) or "ok", "WARN")
    if broken:
        checks[-1]["ok"] = True
        checks[-1]["level"] = "WARN"

    hard_fails = [c for c in checks if not c["ok"] and c["level"] == "FAIL"]
    status = "FAIL" if hard_fails else "PASS"
    # If any required file missing -> already FAIL via ok=False
    return {
        "status": status,
        "skill_path": str(skill_path),
        "checks": checks,
        "notes": [
            "Codex discovery: $skill-creator and /skills when skill is on a scanned path.",
            "ChatGPT @ picker: may require plugin install — not verified by file presence alone.",
            "Never modify SYSTEM/bundled skills.",
        ],
    }


def main() -> int:
    p = argparse.ArgumentParser(description="Doctor for skill-creator")
    p.add_argument("--skill-path", type=Path, default=None)
    p.add_argument("--json", action="store_true")
    args = p.parse_args()
    report = doctor(args.skill_path)
    if args.json:
        print(json.dumps(report, indent=2))
    else:
        print(f"STATUS: {report['status']}")
        print(f"Skill:  {report['skill_path']}")
        for c in report["checks"]:
            mark = c["level"] if c["ok"] or c["level"] != "FAIL" else "FAIL"
            if c["ok"] and c["level"] == "WARN":
                mark = "WARN"
            elif c["ok"]:
                mark = "PASS"
            else:
                mark = "FAIL"
            print(f"  [{mark}] {c['name']}: {c['detail']}")
        for n in report["notes"]:
            print(f"  NOTE: {n}")
    return 0 if report["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
