#!/usr/bin/env python3
"""Package a skill as a zip bundle and optional plugin-ready scaffold."""
from __future__ import annotations

import argparse
import json
import shutil
import sys
import zipfile
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import emit_event, parse_frontmatter, write_text  # noqa: E402
from validate_skill import validate_skill  # noqa: E402


def package_skill(
    skill_path: Path,
    output_dir: Path,
    *,
    plugin: bool = False,
    force: bool = False,
) -> dict:
    skill_path = skill_path.resolve()
    output_dir = output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    v = validate_skill(skill_path)
    if v.status == "FAIL":
        return {"status": "FAILED", "reason": "validation", "validation": v.to_dict()}

    fm, _, _ = parse_frontmatter((skill_path / "SKILL.md").read_text(encoding="utf-8"))
    name = str(fm.get("name") or skill_path.name)
    ts = datetime.now().strftime("%Y%m%dT%H%M%S")
    zip_path = output_dir / f"{name}-{ts}.skill.zip"

    if zip_path.exists() and not force:
        return {"status": "STOPPED", "reason": "exists", "path": str(zip_path)}

    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for p in skill_path.rglob("*"):
            if not p.is_file():
                continue
            if any(x in p.parts for x in ("__pycache__", ".git")):
                continue
            if p.name == "SKILL_CREATION_REPORT.md":
                continue
            arc = Path(name) / p.relative_to(skill_path)
            zf.write(p, arcname=str(arc))

    result = {
        "status": "PACKAGED",
        "name": name,
        "zip": str(zip_path),
        "validation": v.status,
        "plugin": None,
    }

    if plugin:
        plugin_dir = output_dir / f"{name}-plugin"
        if plugin_dir.exists() and force:
            shutil.rmtree(plugin_dir)
        if plugin_dir.exists():
            result["status"] = "PACKAGED_PARTIAL"
            result["plugin_error"] = f"Plugin dir exists: {plugin_dir}"
        else:
            skills_dst = plugin_dir / "skills" / name
            shutil.copytree(
                skill_path,
                skills_dst,
                ignore=shutil.ignore_patterns("__pycache__", "*.pyc", "SKILL_CREATION_REPORT.md"),
            )
            manifest = {
                "name": name,
                "version": "0.1.0",
                "description": fm.get("description"),
                "skills": [f"./skills/{name}"],
                "interface": {
                    "displayName": name.replace("-", " ").title(),
                },
            }
            write_text(
                plugin_dir / ".codex-plugin" / "plugin.json",
                json.dumps(manifest, indent=2) + "\n",
            )
            write_text(
                plugin_dir / "README.md",
                f"# {name} plugin\n\nInstall via Codex plugin/marketplace flow. "
                f"Local USER skill path alone does not guarantee ChatGPT `@` picker visibility.\n",
            )
            result["plugin"] = str(plugin_dir)
            result["plugin_manifest"] = str(plugin_dir / ".codex-plugin" / "plugin.json")

    emit_event("skill.packaged", {"name": name, "zip": str(zip_path)})
    return result


def main() -> int:
    p = argparse.ArgumentParser(description="Package an Agent Skill")
    p.add_argument("skill_path", type=Path)
    p.add_argument("-o", "--output", type=Path, default=Path("dist"))
    p.add_argument("--plugin", action="store_true", help="Also emit plugin-ready scaffold")
    p.add_argument("--force", action="store_true")
    p.add_argument("--json", action="store_true")
    args = p.parse_args()
    result = package_skill(args.skill_path, args.output, plugin=args.plugin, force=args.force)
    if args.json:
        print(json.dumps(result, indent=2))
    else:
        print(f"STATUS: {result.get('status')}")
        for k, v in result.items():
            if k != "status":
                print(f"  {k}: {v}")
    return 0 if str(result.get("status", "")).startswith("PACKAGED") else 1


if __name__ == "__main__":
    raise SystemExit(main())
