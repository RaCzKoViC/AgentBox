#!/usr/bin/env python3
"""AgentBox v5 — Permission Profiles (beta3)."""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any, Optional

_HERE = Path(__file__).resolve().parent

# Spec §13 permission keys
PERMISSION_KEYS = (
    "read_files",
    "write_files",
    "delete_files",
    "network",
    "git_commit",
    "git_merge",
    "git_push",
    "package_install",
    "docker",
    "database",
    "deploy",
    "delegate_to",
)

# Default profiles by role
DEFAULT_PROFILES: dict[str, dict[str, Any]] = {
    "planner": {
        "read_files": True, "write_files": False, "delete_files": False,
        "network": True, "git_commit": False, "git_merge": False, "git_push": False,
        "package_install": False, "docker": False, "database": False,
        "deploy": False, "delegate_to": ["researcher", "architect"],
    },
    "researcher": {
        "read_files": True, "write_files": True, "delete_files": False,
        "network": True, "git_commit": False, "git_merge": False, "git_push": False,
        "package_install": False, "docker": False, "database": False,
        "deploy": False, "delegate_to": [],
    },
    "architect": {
        "read_files": True, "write_files": True, "delete_files": False,
        "network": True, "git_commit": True, "git_merge": False, "git_push": False,
        "package_install": False, "docker": False, "database": False,
        "deploy": False, "delegate_to": ["security", "performance", "coder"],
    },
    "coder": {
        "read_files": True, "write_files": True, "delete_files": True,
        "network": True, "git_commit": True, "git_merge": False, "git_push": False,
        "package_install": True, "docker": True, "database": False,
        "deploy": False, "delegate_to": ["tester", "debugger"],
    },
    "tester": {
        "read_files": True, "write_files": True, "delete_files": False,
        "network": True, "git_commit": False, "git_merge": False, "git_push": False,
        "package_install": True, "docker": True, "database": False,
        "deploy": False, "delegate_to": ["debugger"],
    },
    "debugger": {
        "read_files": True, "write_files": True, "delete_files": False,
        "network": True, "git_commit": True, "git_merge": False, "git_push": False,
        "package_install": False, "docker": False, "database": False,
        "deploy": False, "delegate_to": [],
    },
    "security": {
        "read_files": True, "write_files": False, "delete_files": False,
        "network": True, "git_commit": False, "git_merge": False, "git_push": False,
        "package_install": False, "docker": False, "database": False,
        "deploy": False, "delegate_to": [],
    },
    "performance": {
        "read_files": True, "write_files": True, "delete_files": False,
        "network": True, "git_commit": False, "git_merge": False, "git_push": False,
        "package_install": False, "docker": False, "database": False,
        "deploy": False, "delegate_to": [],
    },
    "reviewer": {
        "read_files": True, "write_files": False, "delete_files": False,
        "network": False, "git_commit": False, "git_merge": True, "git_push": False,
        "package_install": False, "docker": False, "database": False,
        "deploy": False, "delegate_to": ["security", "debugger"],
    },
}

ACTION_TO_PERM: dict[str, str] = {
    "filesystem.read": "read_files",
    "read_file": "read_files",
    "filesystem.write": "write_files",
    "filesystem.create": "write_files",
    "modify_workspace_file": "write_files",
    "create_file": "write_files",
    "filesystem.delete": "delete_files",
    "delete_file": "delete_files",
    "network.outbound": "network",
    "network_request": "network",
    "git.commit": "git_commit",
    "git_commit": "git_commit",
    "git.merge": "git_merge",
    "git_merge": "git_merge",
    "git.push": "git_push",
    "git_push": "git_push",
    "git.force_push": "git_push",
    "force_push": "git_push",
    "packages.install": "package_install",
    "install_dependency": "package_install",
    "docker.run": "docker",
    "docker.build": "docker",
    "docker.privileged": "docker",
    "database.migration": "database",
    "deployment.production": "deploy",
    "deployment.staging": "deploy",
    "agent.delegate": "delegate_to",
    "handoff.create": "delegate_to",
}


def _ensure_path() -> None:
    lib = str(_HERE.parent)
    if lib not in sys.path:
        sys.path.insert(0, lib)


def _tomllib():
    try:
        import tomllib
        return tomllib
    except ImportError:
        import tomli as tomllib  # type: ignore
        return tomllib


def load_profiles_from_config() -> dict[str, dict[str, Any]]:
    """Merge DEFAULT_PROFILES with optional [permissions.*] in agents.toml."""
    profiles = {k: dict(v) for k, v in DEFAULT_PROFILES.items()}
    home = Path(os.environ.get("AGENTBOX_V5_HOME", Path.home() / ".local/share/agentbox/v5"))
    candidates = [
        home / "config" / "agents.toml",
        _HERE.parent.parent / "config" / "agents.toml",
    ]
    path = next((p for p in candidates if p.is_file()), None)
    if not path:
        return profiles
    try:
        with open(path, "rb") as f:
            data = _tomllib().load(f)
        perms = data.get("permissions") or {}
        for role, cfg in perms.items():
            if isinstance(cfg, dict):
                base = profiles.get(role, {k: False for k in PERMISSION_KEYS})
                base = dict(base)
                for k, v in cfg.items():
                    base[k] = v
                profiles[role] = base
        # Also allow permissions nested under agents.<id>.permissions
        agents = data.get("agents") or {}
        for aid, cfg in agents.items():
            if isinstance(cfg, dict) and isinstance(cfg.get("permissions"), dict):
                role = str(cfg.get("role") or aid)
                base = dict(profiles.get(role, {k: False for k in PERMISSION_KEYS}))
                base.update(cfg["permissions"])
                profiles[role] = base
                profiles[aid] = base
    except Exception:
        pass
    return profiles


def get_agent_permissions(agent_name: str, db_path: Optional[str] = None) -> dict[str, Any]:
    """Resolve permission profile for an agent (by id or role)."""
    profiles = load_profiles_from_config()
    key = (agent_name or "").strip().lower()
    if key in profiles:
        return dict(profiles[key])
    # Try registry
    try:
        _ensure_path()
        from agents.registry import get_agent  # type: ignore

        row = get_agent(key, db_path=db_path)
        if row:
            # meta_json.permissions override
            meta = {}
            try:
                meta = json.loads(row.get("meta_json") or "{}")
            except Exception:
                meta = {}
            role = (row.get("role") or key).strip().lower()
            base = dict(profiles.get(role, profiles.get(key, {k: False for k in PERMISSION_KEYS})))
            if isinstance(meta.get("permissions"), dict):
                base.update(meta["permissions"])
            return base
    except Exception:
        pass
    return dict(profiles.get("coder", {k: False for k in PERMISSION_KEYS}))


def check_permission(
    agent_name: str,
    action: str,
    resource: Optional[str] = None,
    context: Optional[dict] = None,
    db_path: Optional[str] = None,
) -> dict[str, Any]:
    """Check whether agent may perform action. Returns {allowed, reason, permission}."""
    context = context or {}
    action_n = (action or "").strip().replace("/", ".")
    perm_key = ACTION_TO_PERM.get(action_n)
    profile = get_agent_permissions(agent_name, db_path=db_path)
    if perm_key is None:
        # Unknown action → allow at permission layer (policy/risk still apply)
        return {
            "allowed": True,
            "reason": f"no permission mapping for {action_n}",
            "permission": None,
            "profile": profile,
        }
    val = profile.get(perm_key)
    if perm_key == "delegate_to":
        target = (context.get("target_agent") or resource or "").strip().lower()
        allowed_list = val if isinstance(val, list) else []
        # Also consult can_delegate matrix
        ok = False
        if target and target in [str(t).lower() for t in allowed_list]:
            ok = True
        else:
            try:
                _ensure_path()
                from agents.registry import can_delegate  # type: ignore

                d = can_delegate(agent_name, target or "", db_path=db_path)
                ok = bool(d.get("allowed"))
            except Exception:
                ok = False
        result = {
            "allowed": ok,
            "reason": f"delegate_to {'allows' if ok else 'denies'} {target}",
            "permission": perm_key,
            "profile": profile,
        }
    else:
        allowed = bool(val)
        result = {
            "allowed": allowed,
            "reason": f"permission {perm_key}={'allow' if allowed else 'deny'} for {agent_name}",
            "permission": perm_key,
            "profile": profile,
        }

    # Emit events
    try:
        _ensure_path()
        from storage import db as dbmod  # type: ignore

        kind = "permission.allowed" if result["allowed"] else "permission.denied"
        dbmod.emit_event(
            kind=kind,
            message=result["reason"],
            task_id=context.get("task_id"),
            payload={
                "agent": agent_name,
                "action": action_n,
                "permission": perm_key,
                "allowed": result["allowed"],
            },
            db_path=db_path,
        )
    except Exception:
        pass
    return result


def _print(obj: Any) -> None:
    print(json.dumps(obj, indent=2, ensure_ascii=False, default=str))


def main(argv: Optional[list[str]] = None) -> int:
    argv = list(argv if argv is not None else sys.argv[1:])
    db_path = os.environ.get("AGENTBOX_V5_DB")
    if not argv:
        print("usage: permissions.py show AGENT | check AGENT ACTION [--target T]", file=sys.stderr)
        return 2
    cmd = argv[0]
    try:
        if cmd == "show":
            if len(argv) < 2:
                print("show AGENT", file=sys.stderr)
                return 2
            _print(get_agent_permissions(argv[1], db_path=db_path))
            return 0
        if cmd == "check":
            import argparse
            p = argparse.ArgumentParser()
            p.add_argument("agent")
            p.add_argument("action")
            p.add_argument("--target", default=None)
            p.add_argument("--resource", default=None)
            args = p.parse_args(argv[1:])
            ctx = {"target_agent": args.target}
            _print(check_permission(args.agent, args.action, resource=args.resource,
                                    context=ctx, db_path=db_path))
            return 0
        if cmd == "list-profiles":
            _print(load_profiles_from_config())
            return 0
        print(f"unknown: {cmd}", file=sys.stderr)
        return 2
    except Exception as e:
        print(f"error: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
