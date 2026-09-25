#!/usr/bin/env python3
"""Inspect an Agent Skill and report structure, metadata, and invocation hints."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import find_skill_collisions, parse_frontmatter, scope_paths  # noqa: E402
from validate_skill import validate_skill  # noqa: E402


def detect_scope(skill_path: Path) -> str:
    skill_path = skill_path.resolve()
    for scope, base in scope_paths().items():
        try:
            skill_path.relative_to(base.resolve())
            return scope
        except Exception:
            continue
    return "UNKNOWN"


def inspect_skill(skill_path: Path) -> dict:
    skill_path = skill_path.resolve()
    report: dict = {
        "path": str(skill_path),
        "exists": skill_path.exists(),
        "scope": detect_scope(skill_path) if skill_path.exists() else None,
    }
    if not skill_path.exists():
        report["error"] = "not found"
        return report

    skill_md = skill_path / "SKILL.md"
    if skill_md.exists():
        text = skill_md.read_text(encoding="utf-8")
        fm, body, err = parse_frontmatter(text)
        report["frontmatter_error"] = err
        report["name"] = fm.get("name")
        report["description"] = fm.get("description")
        report["metadata"] = fm.get("metadata")
        report["license"] = fm.get("license")
        report["body_chars"] = len(body)
        report["body_lines"] = body.count("\n") + 1
    else:
        report["name"] = None
        report["description"] = None

    def list_files(subdir: str) -> list[str]:
        d = skill_path / subdir
        if not d.exists():
            return []
        return sorted(
            str(p.relative_to(skill_path))
            for p in d.rglob("*")
            if p.is_file() and "__pycache__" not in p.parts
        )

    report["files"] = sorted(
        str(p.relative_to(skill_path))
        for p in skill_path.rglob("*")
        if p.is_file() and "__pycache__" not in p.parts
    )
    report["scripts"] = list_files("scripts")
    report["references"] = list_files("references")
    report["assets"] = list_files("assets")
    report["templates"] = list_files("templates")
    report["schemas"] = list_files("schemas")
    report["tests"] = list_files("tests")

    openai = skill_path / "agents" / "openai.yaml"
    report["has_openai_yaml"] = openai.exists()
    if openai.exists():
        try:
            import yaml

            report["openai_yaml"] = yaml.safe_load(openai.read_text(encoding="utf-8"))
        except Exception as exc:  # noqa: BLE001
            report["openai_yaml_error"] = str(exc)

    policy = (report.get("openai_yaml") or {}).get("policy") or {}
    allow_implicit = policy.get("allow_implicit_invocation", True)
    name = report.get("name") or skill_path.name
    report["invocation"] = {
        "explicit_codex": f"${name}",
        "skills_picker": "/skills",
        "chatgpt_at": f"@{name}",
        "allow_implicit_invocation": allow_implicit,
        "notes": [
            "Codex discovers skills under ~/.agents/skills, <repo>/.agents/skills, and system paths.",
            "ChatGPT @ picker typically requires a packaged/installed plugin — local USER skill alone may not appear.",
        ],
    }

    if report.get("name"):
        report["collisions"] = find_skill_collisions(report["name"])

    v = validate_skill(skill_path)
    report["validation_status"] = v.status
    report["warnings"] = [f.message for f in v.findings if f.level == "WARN"]
    report["failures"] = [f.message for f in v.findings if f.level == "FAIL"]
    return report


def main() -> int:
    p = argparse.ArgumentParser(description="Inspect an Agent Skill")
    p.add_argument("skill_path", type=Path)
    p.add_argument("--json", action="store_true")
    args = p.parse_args()
    report = inspect_skill(args.skill_path)
    if args.json:
        print(json.dumps(report, indent=2, default=str))
    else:
        print(f"Name:        {report.get('name')}")
        print(f"Description: {report.get('description')}")
        print(f"Scope:       {report.get('scope')}")
        print(f"Path:        {report.get('path')}")
        print(f"Validation:  {report.get('validation_status')}")
        print(f"Files:       {len(report.get('files') or [])}")
        print(f"Scripts:     {len(report.get('scripts') or [])}")
        print(f"References:  {len(report.get('references') or [])}")
        print(f"Assets:      {len(report.get('assets') or [])}")
        print(f"Metadata:    {report.get('metadata')}")
        inv = report.get("invocation") or {}
        print(f"Invocation:  Codex {inv.get('explicit_codex')} | ChatGPT {inv.get('chatgpt_at')}")
        print(f"Implicit:    {inv.get('allow_implicit_invocation')}")
        for w in report.get("warnings") or []:
            print(f"  WARN: {w}")
        for f in report.get("failures") or []:
            print(f"  FAIL: {f}")
    return 0 if report.get("exists") else 1


if __name__ == "__main__":
    raise SystemExit(main())
