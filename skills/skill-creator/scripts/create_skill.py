#!/usr/bin/env python3
"""Create a new Agent Skill with atomic install, backup, and validation."""
from __future__ import annotations

import argparse
import json
import shutil
import sys
import tempfile
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import (  # noqa: E402
    atomic_install,
    audit,
    backup_skill,
    emit_event,
    find_skill_collisions,
    normalize_skill_name,
    resolve_scope_dir,
    title_case,
    validate_skill_name,
    write_text,
)
from validate_skill import validate_skill  # noqa: E402

SKILL_ROOT = Path(__file__).resolve().parents[1]
TEMPLATES = SKILL_ROOT / "templates"

MODES = {
    "instruction-only": "instruction-only",
    "instruction+references": "instruction-only",  # base + references folder
    "scripted": "scripted",
    "tool-aware": "tool-aware",
    "full": "scripted",
    "plugin-ready": "plugin-ready",
}


def _load_template(mode: str) -> Path:
    key = MODES.get(mode, mode)
    path = TEMPLATES / key
    if not path.exists():
        raise FileNotFoundError(f"Template not found for mode '{mode}': {path}")
    return path


def _render(text: str, mapping: dict[str, str]) -> str:
    out = text
    for k, v in mapping.items():
        out = out.replace("{{" + k + "}}", v)
    return out


def generate_skill_tree(
    dest: Path,
    *,
    name: str,
    description: str,
    mode: str,
    display_name: str | None = None,
) -> list[str]:
    created: list[str] = []
    tpl_root = _load_template(mode)
    mapping = {
        "NAME": name,
        "TITLE": title_case(name),
        "DESCRIPTION": description,
        "DISPLAY_NAME": display_name or title_case(name),
        "DEFAULT_PROMPT": f"Use ${name} to {description.split('.')[0].lower()}.",
        "YEAR": str(datetime.now().year),
    }

    for src in tpl_root.rglob("*"):
        if src.is_dir():
            continue
        rel = src.relative_to(tpl_root)
        # Skip placeholder-only markers
        if src.name == ".gitkeep":
            continue
        target = dest / rel
        raw = src.read_text(encoding="utf-8")
        write_text(target, _render(raw, mapping))
        if target.suffix == ".py":
            target.chmod(0o755)
        created.append(str(rel))

    # Mode-specific extras
    if mode in ("instruction+references", "full"):
        ref = dest / "references" / "overview.md"
        if not ref.exists():
            write_text(
                ref,
                f"# {mapping['TITLE']} Reference\n\nTask-specific details for `{name}`.\n",
            )
            created.append("references/overview.md")

    if mode == "full":
        # Ensure scripts + references + agents
        for sub in ("scripts", "references", "agents", "assets"):
            (dest / sub).mkdir(exist_ok=True)

    # Always ensure SKILL.md exists after render
    if not (dest / "SKILL.md").exists():
        raise RuntimeError("Template did not produce SKILL.md")

    return created


def create_skill(
    *,
    name: str,
    description: str,
    scope: str = "user",
    mode: str = "scripted",
    repo_root: Path | None = None,
    force: bool = False,
    update: bool = False,
    dry_run: bool = False,
    output: Path | None = None,
    display_name: str | None = None,
) -> dict:
    ok, msg = validate_skill_name(name)
    if not ok:
        # try normalize once
        normalized = normalize_skill_name(name)
        ok2, msg2 = validate_skill_name(normalized)
        if not ok2:
            raise ValueError(msg)
        name = normalized

    emit_event("skill.creation.started", {"name": name, "scope": scope, "mode": mode})

    if output:
        dest = Path(output) / name if (Path(output).name != name) else Path(output)
        if dest.name != name:
            dest = Path(output) / name
    else:
        base = resolve_scope_dir(scope, repo_root)
        dest = base / name

    collisions = find_skill_collisions(name, repo_root)
    system_hits = [c for c in collisions if c["scope"] == "SYSTEM"]
    if system_hits and scope.upper() != "USER" and not output:
        # Creating REPO with same name as SYSTEM is ok; creating ADMIN against SYSTEM is risky
        pass

    existing = dest.exists() and (dest / "SKILL.md").exists()
    if existing and not (force or update):
        audit("CREATE", name, scope, "STOPPED", "collision without force/update")
        return {
            "status": "STOPPED",
            "reason": "collision",
            "path": str(dest),
            "message": (
                f"Skill already exists at {dest}. Use --update (with backup) or --force. "
                "Refusing to overwrite."
            ),
            "collisions": collisions,
        }

    if dry_run:
        return {
            "status": "DRY_RUN",
            "name": name,
            "path": str(dest),
            "scope": scope.upper(),
            "mode": mode,
            "would_backup": existing,
            "collisions": collisions,
        }

    backup_path = None
    if existing and (force or update):
        backup_path = backup_skill(dest, reason="update" if update else "force")

    with tempfile.TemporaryDirectory(prefix="skill-creator-") as td:
        staging = Path(td) / name
        staging.mkdir()
        files = generate_skill_tree(
            staging,
            name=name,
            description=description,
            mode=mode,
            display_name=display_name,
        )
        # Validate staging before install
        v = validate_skill(staging, check_duplicates=False)
        if v.status == "FAIL":
            if backup_path and existing:
                # nothing installed yet
                pass
            audit("CREATE", name, scope, "FAILED", "validation failed pre-install")
            emit_event("skill.validation.failed", {"name": name})
            return {
                "status": "FAILED",
                "phase": "validation",
                "validation": v.to_dict(),
                "path": str(dest),
            }

        try:
            if existing:
                shutil.rmtree(dest)
            atomic_install(staging, dest)
        except Exception as exc:  # noqa: BLE001
            if backup_path:
                from common import restore_backup

                restore_backup(backup_path, dest)
            audit("CREATE", name, scope, "FAILED", f"install error: {exc}")
            return {"status": "FAILED", "phase": "install", "error": str(exc), "rollback": str(backup_path)}

    # Post-install validate
    v2 = validate_skill(dest, check_duplicates=True)
    emit_event("skill.validation.passed" if v2.status != "FAIL" else "skill.validation.failed", {"name": name})
    emit_event("skill.created" if not existing else "skill.updated", {"name": name, "path": str(dest)})
    audit("UPDATE" if existing else "CREATE", name, scope, v2.status, str(dest))

    report = {
        "status": "CREATED" if not existing else "UPDATED",
        "name": name,
        "scope": scope.upper(),
        "mode": mode,
        "path": str(dest),
        "files": files,
        "validation": v2.to_dict(),
        "backup": str(backup_path) if backup_path else None,
        "collisions": collisions,
        "quality_gate": "VALID" if v2.status != "FAIL" else "FAILED",
    }

    # Write creation report next to skill when possible
    report_path = dest / "SKILL_CREATION_REPORT.md"
    report_md = _format_report(report)
    write_text(report_path, report_md)
    report["report_path"] = str(report_path)
    return report


def _format_report(report: dict) -> str:
    lines = [
        "# Skill Creation Report",
        "",
        f"- **Name:** `{report.get('name')}`",
        f"- **Scope:** {report.get('scope')}",
        f"- **Mode:** {report.get('mode')}",
        f"- **Path:** `{report.get('path')}`",
        f"- **Status:** {report.get('status')}",
        f"- **Quality gate:** {report.get('quality_gate')}",
        f"- **Backup:** `{report.get('backup')}`",
        "",
        "## Validation",
        f"Status: **{report.get('validation', {}).get('status')}**",
        "",
    ]
    for f in report.get("validation", {}).get("findings", []):
        lines.append(f"- [{f['level']}] {f['code']}: {f['message']}")
    lines.extend(["", "## Files", ""])
    for f in report.get("files", []):
        lines.append(f"- `{f}`")
    lines.append("")
    return "\n".join(lines)


def main() -> int:
    p = argparse.ArgumentParser(description="Create a new Agent Skill")
    p.add_argument("--name", required=True)
    p.add_argument("--description", required=True)
    p.add_argument("--scope", default="user", choices=["user", "repo", "admin", "USER", "REPO", "ADMIN"])
    p.add_argument(
        "--mode",
        default="scripted",
        choices=list(MODES.keys()),
    )
    p.add_argument("--repo-root", type=Path, default=None)
    p.add_argument("--output", type=Path, default=None, help="Explicit parent or skill path")
    p.add_argument("--display-name", default=None)
    p.add_argument("--force", action="store_true")
    p.add_argument("--update", action="store_true")
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--json", action="store_true")
    args = p.parse_args()

    try:
        report = create_skill(
            name=args.name,
            description=args.description,
            scope=args.scope,
            mode=args.mode,
            repo_root=args.repo_root,
            force=args.force,
            update=args.update,
            dry_run=args.dry_run,
            output=args.output,
            display_name=args.display_name,
        )
    except Exception as exc:  # noqa: BLE001
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2

    if args.json:
        print(json.dumps(report, indent=2))
    else:
        print(f"STATUS: {report.get('status')}")
        for k in ("name", "scope", "mode", "path", "backup", "message", "reason"):
            if report.get(k):
                print(f"  {k}: {report[k]}")
        if report.get("validation"):
            print(f"  validation: {report['validation'].get('status')}")
    return 0 if report.get("status") in ("CREATED", "UPDATED", "DRY_RUN", "STOPPED") else 1


if __name__ == "__main__":
    raise SystemExit(main())
