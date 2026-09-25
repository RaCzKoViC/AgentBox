#!/usr/bin/env python3
"""Validate an Agent Skill directory. Exit 0 for PASS/WARN, 1 for FAIL."""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

# Allow running from any cwd
sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import (  # noqa: E402
    MAX_DESCRIPTION_LENGTH,
    ValidationResult,
    description_quality_warnings,
    find_skill_collisions,
    parse_frontmatter,
    scan_dangerous_commands,
    scan_secrets,
    validate_skill_name,
)

ALLOWED_FRONTMATTER = {
    "name",
    "description",
    "license",
    "compatibility",
    "metadata",
    "allowed-tools",
}


def validate_skill(skill_path: Path, *, check_duplicates: bool = True) -> ValidationResult:
    result = ValidationResult(status="PASS")
    skill_path = skill_path.resolve()
    result.meta["path"] = str(skill_path)

    if not skill_path.exists() or not skill_path.is_dir():
        result.add("FAIL", "dir.missing", f"Skill directory not found: {skill_path}")
        return result.finalize()

    skill_md = skill_path / "SKILL.md"
    if not skill_md.exists():
        result.add("FAIL", "skillmd.missing", "SKILL.md not found", str(skill_md))
        return result.finalize()

    text = skill_md.read_text(encoding="utf-8")
    fm, body, err = parse_frontmatter(text)
    if err:
        result.add("FAIL", "frontmatter.invalid", err, str(skill_md))
        return result.finalize()

    unexpected = set(fm.keys()) - ALLOWED_FRONTMATTER
    if unexpected:
        result.add(
            "FAIL",
            "frontmatter.unexpected",
            f"Unexpected frontmatter keys: {', '.join(sorted(unexpected))}",
            str(skill_md),
        )

    name = fm.get("name")
    if not name:
        result.add("FAIL", "name.missing", "Missing required frontmatter field: name")
    else:
        ok, msg = validate_skill_name(str(name))
        if not ok:
            result.add("FAIL", "name.invalid", msg)
        elif str(name) != skill_path.name:
            result.add(
                "FAIL",
                "name.mismatch",
                f"Frontmatter name '{name}' must match directory name '{skill_path.name}'",
            )
        result.meta["name"] = str(name)

    description = fm.get("description")
    if description is None or (isinstance(description, str) and not description.strip()):
        result.add("FAIL", "description.missing", "Missing required frontmatter field: description")
    else:
        if not isinstance(description, str):
            result.add("FAIL", "description.type", "Description must be a string")
        else:
            d = description.strip()
            if d.startswith("[TODO:"):
                result.add("FAIL", "description.todo", "Description contains unfinished TODO")
            if "<" in d or ">" in d:
                result.add("FAIL", "description.brackets", "Description cannot contain < or >")
            if len(d) > MAX_DESCRIPTION_LENGTH:
                result.add(
                    "FAIL",
                    "description.length",
                    f"Description too long ({len(d)} > {MAX_DESCRIPTION_LENGTH})",
                )
            for w in description_quality_warnings(d):
                result.add("WARN", "description.quality", w)
            result.meta["description"] = d

    if re.search(r"^\s*\[TODO:", body, re.M):
        result.add("FAIL", "body.todo", "SKILL.md body contains unfinished TODO placeholder")

    # Progressive disclosure heuristic
    if len(body) > 12000 and not (skill_path / "references").exists():
        result.add(
            "WARN",
            "progressive.disclosure",
            "SKILL.md body is large; consider moving detail into references/",
        )

    # Broken relative references in markdown links
    for m in re.finditer(r"\[[^\]]*\]\(([^)]+)\)", body):
        target = m.group(1).strip()
        if target.startswith(("http://", "https://", "mailto:", "#")):
            continue
        rel = (skill_path / target).resolve()
        try:
            rel.relative_to(skill_path.resolve())
        except ValueError:
            result.add("WARN", "ref.outside", f"Link escapes skill dir: {target}")
            continue
        if not rel.exists():
            result.add("FAIL", "ref.broken", f"Broken reference: {target}", target)

    # Scripts declared vs present
    scripts_dir = skill_path / "scripts"
    if scripts_dir.exists():
        for py in scripts_dir.glob("*.py"):
            if py.name == "__init__.py":
                continue
            try:
                src = py.read_text(encoding="utf-8", errors="replace")
            except OSError as exc:
                result.add("WARN", "script.unreadable", f"Cannot read {py.name}: {exc}")
                continue
            for label in scan_dangerous_commands(src):
                result.add(
                    "WARN",
                    "script.dangerous",
                    f"Potentially dangerous pattern '{label}' in {py.name} (review required)",
                    str(py),
                )

    # openai.yaml optional check
    openai_yaml = skill_path / "agents" / "openai.yaml"
    if openai_yaml.exists():
        try:
            import yaml

            data = yaml.safe_load(openai_yaml.read_text(encoding="utf-8")) or {}
            if not isinstance(data, dict):
                result.add("FAIL", "openai_yaml.type", "agents/openai.yaml must be a mapping")
            else:
                iface = data.get("interface") or {}
                if iface and not isinstance(iface, dict):
                    result.add("FAIL", "openai_yaml.interface", "interface must be a mapping")
                for icon_key in ("icon_small", "icon_large"):
                    icon = iface.get(icon_key)
                    if icon and isinstance(icon, str) and not icon.startswith(("http://", "https://")):
                        icon_path = (skill_path / icon).resolve()
                        if not icon_path.exists():
                            result.add(
                                "WARN",
                                "openai_yaml.icon_missing",
                                f"{icon_key} path missing: {icon}",
                            )
        except Exception as exc:  # noqa: BLE001
            result.add("FAIL", "openai_yaml.parse", f"Cannot parse agents/openai.yaml: {exc}")

    # Absolute path smell: hardcoded user home paths in instructions
    for m in re.finditer(r"(?m)^(?!\s{4})(?!\|).*(/(?:home|Users)/[^\s`]+)", body):
        result.add(
            "WARN",
            "abs.path",
            "Hardcoded home path detected in instructions; prefer $HOME or relative paths",
        )
        break

    # Secret scan across text files — never print secret values
    validating_fixture = skill_path.parent.name == "fixtures"
    for path in skill_path.rglob("*"):
        if not path.is_file():
            continue
        if any(p in path.parts for p in ("__pycache__", ".git", "node_modules")):
            continue
        if path.suffix.lower() in {".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg", ".ico", ".woff", ".ttf"}:
            continue
        try:
            rel_parts = path.relative_to(skill_path).parts
        except ValueError:
            continue
        # Negative fixtures live under tests/fixtures for unit tests; skip when
        # validating the parent skill-creator package (not the fixture itself).
        if (
            not validating_fixture
            and len(rel_parts) >= 2
            and rel_parts[0] == "tests"
            and rel_parts[1] == "fixtures"
        ):
            continue
        try:
            content = path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        hits = scan_secrets(content)
        if hits:
            # FAIL for private keys / obvious tokens; WARN otherwise
            severe = {"private_key_pem", "github_pat", "openai_like_key", "bearer_token"}
            level = "FAIL" if severe.intersection(hits) else "WARN"
            result.add(
                level,
                "security.secret",
                f"Possible embedded secret pattern(s) [{', '.join(sorted(hits))}] in {path.relative_to(skill_path)} — value redacted",
                str(path.relative_to(skill_path)),
            )

    if check_duplicates and result.meta.get("name"):
        collisions = find_skill_collisions(result.meta["name"])
        # Exclude self
        collisions = [c for c in collisions if Path(c["path"]).resolve() != skill_path]
        if collisions:
            scopes = ", ".join(f"{c['scope']}:{c['path']}" for c in collisions)
            result.add(
                "WARN",
                "name.collision",
                f"Same skill name exists elsewhere ({scopes}). Host may prefer SYSTEM/USER order — do not overwrite SYSTEM.",
            )

    return result.finalize()


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate an Agent Skill")
    parser.add_argument("skill_path", type=Path, help="Path to skill directory")
    parser.add_argument("--json", action="store_true", help="Emit JSON report")
    parser.add_argument("--strict", action="store_true", help="Treat WARN as FAIL for exit code")
    parser.add_argument("--no-duplicates", action="store_true")
    args = parser.parse_args()

    result = validate_skill(args.skill_path, check_duplicates=not args.no_duplicates)
    if args.json:
        print(json.dumps(result.to_dict(), indent=2))
    else:
        print(f"STATUS: {result.status}")
        for f in result.findings:
            loc = f" ({f.path})" if f.path else ""
            print(f"  [{f.level}] {f.code}: {f.message}{loc}")
        if not result.findings:
            print("  [PASS] No issues found")
    if args.strict and result.status == "WARN":
        return 1
    return result.exit_code()


if __name__ == "__main__":
    raise SystemExit(main())
