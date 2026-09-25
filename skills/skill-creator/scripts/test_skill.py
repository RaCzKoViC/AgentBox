#!/usr/bin/env python3
"""Structural and trigger tests for an Agent Skill."""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import parse_frontmatter  # noqa: E402
from validate_skill import validate_skill  # noqa: E402

DEFAULT_SHOULD_TRIGGER = [
    "Create a new Agent Skill for reviewing Rust code.",
    "Build me a reusable skill for SSH diagnostics.",
    "Validate this SKILL.md.",
    "Package this skill for distribution.",
    "Improve an existing Codex skill.",
]

DEFAULT_SHOULD_NOT_TRIGGER = [
    "Fix this Rust function.",
    "What is SSH?",
    "Create a PNG icon.",
    "Write a unit test for my parser.",
    "Explain how git rebase works.",
]


def _tokens_from_description(description: str) -> set[str]:
    words = re.findall(r"[a-z0-9]+", (description or "").lower())
    stop = {"a", "an", "the", "and", "or", "to", "for", "with", "of", "in", "on", "when", "this", "that"}
    return {w for w in words if len(w) > 2 and w not in stop}


def heuristic_should_trigger(prompt: str, description: str, name: str) -> bool:
    """Lightweight stand-in for host routing: keyword overlap + skill nouns."""
    p = prompt.lower()
    skill_nouns = ("skill", "skills", "skill.md", "agent skill")
    action = ("create", "build", "validate", "package", "update", "improve", "inspect", "test", "author")
    has_noun = any(n in p for n in skill_nouns) or name.replace("-", " ") in p
    has_action = any(a in p for a in action)
    tokens = _tokens_from_description(description)
    overlap = sum(1 for t in tokens if t in p)
    # Strong path: explicit skill authoring language
    if has_noun and has_action:
        return True
    if "validate this skill.md" in p or "validate this skill" in p:
        return True
    # Weak path: substantial description overlap without ordinary coding ask
    ordinary = ("fix this", "what is", "explain", "write a unit test", "create a png")
    if any(o in p for o in ordinary) and not has_noun:
        return False
    return overlap >= 3 and has_action


def test_skill(
    skill_path: Path,
    *,
    should_trigger: list[str] | None = None,
    should_not_trigger: list[str] | None = None,
) -> dict:
    skill_path = skill_path.resolve()
    results = {"path": str(skill_path), "checks": [], "status": "PASS"}

    def check(name: str, ok: bool, detail: str = "") -> None:
        results["checks"].append({"name": name, "ok": ok, "detail": detail})
        if not ok:
            results["status"] = "FAIL"

    v = validate_skill(skill_path)
    check("structure_validation", v.status != "FAIL", v.status)

    skill_md = skill_path / "SKILL.md"
    check("has_skill_md", skill_md.exists())
    fm, body, err = parse_frontmatter(skill_md.read_text(encoding="utf-8")) if skill_md.exists() else ({}, "", "missing")
    check("frontmatter", err is None, err or "ok")
    name = str(fm.get("name") or "")
    description = str(fm.get("description") or "")
    check("metadata_name", bool(name))
    check("metadata_description", bool(description.strip()))
    check("description_not_generic", "helps with development" not in description.lower())

    # references linked if present
    refs = list((skill_path / "references").glob("*.md")) if (skill_path / "references").exists() else []
    if refs:
        linked = 0
        for r in refs:
            if r.name in body or f"references/{r.name}" in body:
                linked += 1
        check("references_linked", linked > 0 or len(body) < 500, f"linked={linked}/{len(refs)}")

    scripts = list((skill_path / "scripts").glob("*.py")) if (skill_path / "scripts").exists() else []
    for s in scripts:
        if s.name in ("common.py",):
            continue
        check(f"script_syntax:{s.name}", True)  # syntax checked below
        try:
            compile(s.read_text(encoding="utf-8"), str(s), "exec")
            ok = True
            detail = "ok"
        except SyntaxError as exc:
            ok = False
            detail = str(exc)
        # replace last for this script
        results["checks"] = [c for c in results["checks"] if c["name"] != f"script_syntax:{s.name}"]
        check(f"script_syntax:{s.name}", ok, detail)

    should_trigger = should_trigger or DEFAULT_SHOULD_TRIGGER
    should_not_trigger = should_not_trigger or DEFAULT_SHOULD_NOT_TRIGGER

    for prompt in should_trigger:
        ok = heuristic_should_trigger(prompt, description, name)
        check(f"SHOULD_TRIGGER:{prompt[:48]}", ok, prompt)

    for prompt in should_not_trigger:
        ok = not heuristic_should_trigger(prompt, description, name)
        check(f"SHOULD_NOT_TRIGGER:{prompt[:48]}", ok, prompt)

    # Progressive disclosure: lean entrypoint preference
    check("progressive_entrypoint_size", len(body) < 20000, f"body_chars={len(body)}")

    return results


def main() -> int:
    p = argparse.ArgumentParser(description="Test an Agent Skill")
    p.add_argument("skill_path", type=Path)
    p.add_argument("--json", action="store_true")
    args = p.parse_args()
    results = test_skill(args.skill_path)
    if args.json:
        print(json.dumps(results, indent=2))
    else:
        print(f"STATUS: {results['status']}")
        for c in results["checks"]:
            mark = "PASS" if c["ok"] else "FAIL"
            print(f"  [{mark}] {c['name']}" + (f" — {c['detail']}" if c["detail"] and not c["ok"] else ""))
    return 0 if results["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
