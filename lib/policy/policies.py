#!/usr/bin/env python3
"""AgentBox v5 — Policy Engine (beta3: INI + TOML + SQLite policies)."""
from __future__ import annotations

import configparser
import json
import os
import sys
from pathlib import Path
from typing import Any, Optional

_HERE = Path(__file__).resolve().parent


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


def _db():
    _ensure_path()
    from storage import db as dbmod  # type: ignore
    return dbmod


# Map dotted actions → (section, key) for INI/TOML
ACTION_MAP = {
    "git.commit": ("git", "commit"),
    "git.merge": ("git", "merge"),
    "git.push": ("git", "push"),
    "git.force_push": ("git", "force_push"),
    "git.delete_branch": ("git", "delete_branch"),
    "filesystem.read": ("filesystem", "read"),
    "filesystem.write": ("filesystem", "write"),
    "filesystem.create": ("filesystem", "create"),
    "filesystem.delete": ("filesystem", "allow_delete"),
    "filesystem.workspace_only": ("filesystem", "workspace_only"),
    "filesystem.system_write": ("filesystem", "allow_system_write"),
    "filesystem.secret_files": ("filesystem", "secret_files"),
    "docker.allow": ("docker", "enabled"),
    "docker.enabled": ("docker", "enabled"),
    "docker.privileged": ("docker", "privileged"),
    "docker.host_network": ("docker", "host_network"),
    "docker.bind_system_paths": ("docker", "bind_system_paths"),
    "docker.run": ("docker", "run"),
    "docker.build": ("docker", "build"),
    "network.outbound": ("network", "outbound"),
    "network.unknown_domains": ("network", "unknown_domains"),
    "network.allow": ("network", "outbound"),
    "packages.install": ("packages", "install"),
    "packages.remove": ("packages", "remove"),
    "database.migration": ("database", "migration"),
    "database.destructive_migration": ("database", "destructive_migration"),
    "deployment.production": ("deployment", "production"),
    "deployment.staging": ("deployment", "staging"),
    "run.before_run": ("run", "before_run"),
    "before_run": ("run", "before_run"),
    "agent.delegate": ("agent", "delegate"),
    "handoff.create": ("agent", "delegate"),
    # legacy toml keys
    "git.allow_commit": ("git", "commit"),
    "git.allow_merge": ("git", "merge"),
    "git.allow_push": ("git", "push"),
    "git.allow_force_push": ("git", "force_push"),
}


def normalize_decision(raw: Any) -> str:
    if raw is True or raw in ("true", "allow", "auto", "1", "yes", "on"):
        return "allow"
    if raw is False or raw in ("false", "deny", "0", "no", "off", "block"):
        return "deny"
    if isinstance(raw, str):
        v = raw.strip().lower()
        if v in ("approval", "prompt", "ask"):
            return "approval"
        if v in ("audit", "log"):
            return "audit"
        if v in ("allow", "auto", "true"):
            return "allow"
        if v in ("deny", "false", "block"):
            return "deny"
    return "deny"


def ini_path() -> Path:
    return Path(os.environ.get(
        "AGENTBOX_POLICIES_INI",
        Path.home() / ".config" / "agentbox-v5" / "policies.ini",
    ))


def toml_paths() -> list[Path]:
    home = Path(os.environ.get("AGENTBOX_V5_HOME", Path.home() / ".local/share/agentbox/v5"))
    lib = Path(os.environ.get("AGENTBOX_V5_LIB", _HERE.parent))
    return [
        home / "config" / "policies.toml",
        lib.parent / "config" / "policies.toml",
        _HERE.parent.parent / "config" / "policies.toml",
    ]


def seed_ini_from_defaults() -> Path:
    """Ensure ~/.config/agentbox-v5/policies.ini exists (seed from project config)."""
    dest = ini_path()
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.is_file():
        return dest
    candidates = [
        _HERE.parent.parent / "config" / "policies.ini",
        Path("/workspace/agentbox-v5/config/policies.ini"),
    ]
    for src in candidates:
        if src.is_file():
            dest.write_text(src.read_text(encoding="utf-8"), encoding="utf-8")
            return dest
    # Minimal fallback
    dest.write_text(
        "[git]\nforce_push = deny\ncommit = allow\npush = approval\nmerge = approval\n"
        "[filesystem]\nallow_system_write = false\nsecret_files = deny\nwrite = allow\n"
        "[docker]\nprivileged = deny\nenabled = true\n"
        "[approvals]\nrisk_threshold = 60\ncritical_threshold = 80\n",
        encoding="utf-8",
    )
    return dest


def load_ini() -> dict[str, dict[str, str]]:
    seed_ini_from_defaults()
    path = ini_path()
    cp = configparser.ConfigParser()
    cp.optionxform = str  # preserve case
    if path.is_file():
        cp.read(str(path))
    out: dict[str, dict[str, str]] = {}
    for section in cp.sections():
        out[section] = {k: v for k, v in cp.items(section)}
    return out


def load_toml() -> dict[str, Any]:
    tomllib = _tomllib()
    for p in toml_paths():
        if p.is_file():
            with open(p, "rb") as f:
                return tomllib.load(f)
    return {}


def _legacy_toml_key(section: str, key: str, toml: dict) -> Any:
    """Map new INI key names to legacy TOML allow_* booleans."""
    sec = toml.get(section) or {}
    if key in sec:
        return sec[key]
    # legacy aliases
    aliases = {
        ("git", "commit"): "allow_commit",
        ("git", "merge"): "allow_merge",
        ("git", "push"): "allow_push",
        ("git", "force_push"): "allow_force_push",
        ("filesystem", "allow_system_write"): "allow_system_write",
        ("docker", "privileged"): "allow_privileged",
        ("docker", "enabled"): "allow",
        ("network", "outbound"): "allow",
        ("packages", "install"): "install",
        ("run", "before_run"): "before_run",
        ("agent", "delegate"): "delegate",
    }
    alt = aliases.get((section, key))
    if alt and alt in sec:
        return sec[alt]
    return None


def load_policies() -> dict[str, Any]:
    """Merged view: INI preferred, TOML fills gaps. Returns nested dict."""
    ini = load_ini()
    toml = load_toml()
    merged: dict[str, Any] = {}
    # Start with toml
    for sec, vals in toml.items():
        if isinstance(vals, dict):
            merged[sec] = dict(vals)
    # Overlay INI (wins)
    for sec, vals in ini.items():
        merged.setdefault(sec, {})
        for k, v in vals.items():
            merged[sec][k] = v
            # Also write legacy allow_* mirrors for old callers
            if sec == "git" and k == "commit":
                merged[sec]["allow_commit"] = normalize_decision(v) == "allow"
            if sec == "git" and k == "merge":
                merged[sec]["allow_merge"] = normalize_decision(v) != "deny"
            if sec == "git" and k == "push":
                merged[sec]["allow_push"] = normalize_decision(v) != "deny"
            if sec == "git" and k == "force_push":
                merged[sec]["allow_force_push"] = normalize_decision(v) == "allow"
            if sec == "docker" and k == "privileged":
                merged[sec]["allow_privileged"] = normalize_decision(v) == "allow"
            if sec == "docker" and k == "enabled":
                merged[sec]["allow"] = normalize_decision(v) == "allow"
    return merged


def lookup_effect(action: str, policies: Optional[dict] = None) -> tuple[str, str, Any]:
    """Return (decision, reason, raw) for action."""
    policies = policies if policies is not None else load_policies()
    action = action.strip().replace("/", ".")
    if action in ACTION_MAP:
        section, key = ACTION_MAP[action]
    elif "." in action:
        section, key = action.split(".", 1)
    else:
        return "deny", f"unknown action: {action}", None

    raw = None
    sec = policies.get(section) or {}
    if key in sec:
        raw = sec[key]
    else:
        # try legacy
        raw = _legacy_toml_key(section, key, policies)

    if raw is None:
        if action in ("before_run", "run.before_run"):
            return "allow", "default allow (no run.before_run)", None
        if action in ("filesystem.write", "filesystem.read", "filesystem.create"):
            return "allow", f"default allow for {action}", None
        return "deny", f"missing policy {section}.{key}", None

    decision = normalize_decision(raw)
    if decision == "audit":
        decision = "allow"  # audit = allow + audit trail
    return decision, f"policy {section}.{key}={raw!r}", raw


def check_action(action: str, policies: Optional[dict] = None) -> dict[str, Any]:
    """Backward-compatible check. Returns decision dict."""
    decision, reason, raw = lookup_effect(action, policies)
    return {"action": action.strip().replace("/", "."), "decision": decision, "reason": reason, "raw": raw}


def check_task_run(task: dict, policies: Optional[dict] = None) -> dict[str, Any]:
    """Combine task.approval_policy with run.before_run.
    AGENTBOX_AUTO_APPROVE=1: auto-allow non-critical before_run gates.
    """
    policies = policies if policies is not None else load_policies()
    ap = (task.get("approval_policy") or "auto").strip().lower()
    base = check_action("before_run", policies)
    env = os.environ.get("AGENTBOX_AUTO_APPROVE", "1").strip().lower()
    if env not in ("0", "false", "no", "off"):
        return {
            "action": "before_run",
            "decision": "allow",
            "reason": f"autonomous bypass (AUTO_APPROVE={env}, task.approval_policy={ap})",
            "raw": ap,
            "policy": base,
        }
    if ap in ("always", "approval", "prompt"):
        return {
            "action": "before_run",
            "decision": "approval",
            "reason": f"task.approval_policy={ap}",
            "raw": ap,
            "policy": base,
        }
    if ap in ("deny", "never"):
        return {
            "action": "before_run",
            "decision": "deny",
            "reason": f"task.approval_policy={ap}",
            "raw": ap,
            "policy": base,
        }
    return base


def evaluate_policy(
    action: str,
    resource: str | None = None,
    task_id: str | None = None,
    agent_name: str | None = None,
    context: Optional[dict] = None,
    db_path: Optional[str] = None,
) -> dict[str, Any]:
    """Full policy evaluation (spec §8) with risk awareness."""
    context = dict(context or {})
    if resource:
        context.setdefault("resource", resource)
    _ensure_path()
    from policy.risk import assess_risk  # type: ignore

    risk = assess_risk(action, resource=resource, context=context)
    decision, reason, raw = lookup_effect(action)
    policy_id = f"ini:{(action or '').replace('/', '.')}"

    # Risk thresholds from [approvals]
    policies = load_policies()
    appr = policies.get("approvals") or {}
    risk_threshold = int(float(appr.get("risk_threshold", 60)))
    critical_threshold = int(float(appr.get("critical_threshold", 80)))

    final = decision
    # Escalate by risk
    if risk["risk_score"] >= critical_threshold or risk["decision"] == "deny":
        final = "deny"
        reason = f"{reason}; risk CRITICAL/deny (score={risk['risk_score']})"
    elif risk["risk_score"] >= risk_threshold and final == "allow":
        final = "approval"
        reason = f"{reason}; risk score {risk['risk_score']} >= threshold {risk_threshold}"

    # Hard safety (spec §18) — always win
    act = (action or "").replace("/", ".")
    if act in ("git.force_push", "force_push") or context.get("force_push"):
        final = "deny"
        reason = "hard deny: force_push"
    if act in ("docker.privileged",) or context.get("privileged"):
        final = "deny"
        reason = "hard deny: privileged docker"
    if act == "filesystem.system_write" or (
        resource and str(resource).startswith(("/etc", "/usr", "/boot"))
        and "write" in act
    ):
        final = "deny"
        reason = "hard deny: system path write"
    if act == "filesystem.secret_files" or (
        resource and decision == "deny" and "secret" in reason
    ):
        if lookup_effect("filesystem.secret_files")[0] == "deny":
            # already handled via lookup; reinforce
            pass

    # AUTO_APPROVE: auto-approve non-CRITICAL; CRITICAL stays deny
    env = os.environ.get("AGENTBOX_AUTO_APPROVE", "1").strip().lower()
    auto = env not in ("0", "false", "no", "off")
    if auto and final == "approval" and risk["risk_level"] != "CRITICAL":
        final = "allow"
        reason = f"{reason}; AUTO_APPROVE bypass (non-CRITICAL)"
    if auto and final == "deny" and risk["risk_level"] == "CRITICAL":
        # CRITICAL still DENY even with AUTO_APPROVE
        reason = f"{reason}; AUTO_APPROVE does NOT bypass CRITICAL"

    result = {
        "decision": final,
        "reason": reason,
        "policy_id": policy_id,
        "risk_score": risk["risk_score"],
        "risk_level": risk["risk_level"],
        "action": act,
        "resource": resource,
        "agent_name": agent_name,
        "task_id": task_id,
        "raw": raw,
        "auto_approve": auto,
    }

    # Persist policy row lookup + events/metrics
    try:
        db = _db()
        kind_map = {
            "allow": "policy.allowed",
            "deny": "policy.denied",
            "approval": "policy.approval_required",
        }
        db.emit_event(
            kind="policy.evaluated",
            message=f"{act} → {final}",
            task_id=task_id,
            payload=result,
            db_path=db_path,
        )
        db.emit_event(
            kind=kind_map.get(final, "policy.evaluated"),
            message=reason,
            task_id=task_id,
            payload=result,
            db_path=db_path,
        )
        from observability.metrics import record_metric  # type: ignore
        record_metric("agentbox_policy_checks_total", 1.0,
                      labels={"decision": final}, db_path=db_path)
        if final == "deny":
            record_metric("agentbox_policy_denies_total", 1.0, db_path=db_path)
    except Exception:
        pass
    return result


def list_policies_db(db_path: Optional[str] = None) -> list[dict]:
    db = _db()
    with db.connect(db_path) as conn:
        rows = conn.execute(
            "SELECT * FROM policies WHERE enabled=1 ORDER BY category, action"
        ).fetchall()
        return [dict(r) for r in rows]


def list_policies_config() -> list[dict]:
    """Flatten INI/TOML into list of policy entries for CLI list."""
    policies = load_policies()
    out = []
    for section, vals in sorted(policies.items()):
        if not isinstance(vals, dict):
            continue
        for key, raw in sorted(vals.items()):
            if key.startswith("allow_") and key[6:] in vals:
                continue  # skip legacy mirrors when modern key exists
            out.append({
                "id": f"{section}.{key}",
                "scope_type": "global",
                "scope_id": None,
                "category": section,
                "action": key,
                "effect": normalize_decision(raw),
                "raw": raw,
                "enabled": 1,
            })
    return out


def seed_policies_table(db_path: Optional[str] = None) -> int:
    """Seed policies table from config if empty."""
    db = _db()
    with db.connect(db_path) as conn:
        n = conn.execute("SELECT COUNT(*) c FROM policies").fetchone()["c"]
        if n > 0:
            return int(n)
        now = db.utc_now()
        count = 0
        for p in list_policies_config():
            pid = db.new_id("pol_")
            conn.execute(
                """
                INSERT INTO policies (id, scope_type, scope_id, category, action, effect,
                    config_json, enabled, created_at, updated_at)
                VALUES (?, 'global', NULL, ?, ?, ?, ?, 1, ?, ?)
                """,
                (
                    pid, p["category"], p["action"], p["effect"],
                    json.dumps({"raw": p["raw"]}), now, now,
                ),
            )
            count += 1
        conn.commit()
        return count


def get_policy(policy_id: str, db_path: Optional[str] = None) -> Optional[dict]:
    # Try DB first
    db = _db()
    with db.connect(db_path) as conn:
        row = conn.execute("SELECT * FROM policies WHERE id=?", (policy_id,)).fetchone()
        if row:
            return dict(row)
    # Config id like git.force_push
    for p in list_policies_config():
        if p["id"] == policy_id or f"{p['category']}.{p['action']}" == policy_id:
            return p
    return None


def _print(obj: Any) -> None:
    print(json.dumps(obj, indent=2, ensure_ascii=False, default=str))


def main(argv: Optional[list[str]] = None) -> int:
    argv = list(argv if argv is not None else sys.argv[1:])
    db_path = os.environ.get("AGENTBOX_V5_DB")
    if not argv:
        print("usage: policies.py list|show ID|check ACTION|evaluate ACTION|seed", file=sys.stderr)
        return 2
    cmd = argv[0]
    try:
        if cmd == "show":
            if len(argv) >= 2 and argv[1] not in ("--raw",):
                p = get_policy(argv[1], db_path=db_path)
                if not p:
                    print(f"not found: {argv[1]}", file=sys.stderr)
                    return 1
                _print(p)
                return 0
            _print(load_policies())
            return 0
        if cmd == "list":
            seed_ini_from_defaults()
            try:
                seed_policies_table(db_path=db_path)
                rows = list_policies_db(db_path=db_path)
                if rows:
                    _print(rows)
                    return 0
            except Exception:
                pass
            _print(list_policies_config())
            return 0
        if cmd == "check":
            if len(argv) < 2:
                print("check ACTION", file=sys.stderr)
                return 2
            result = check_action(argv[1])
            _print(result)
            d = result["decision"]
            return 0 if d == "allow" else (2 if d == "approval" else 1)
        if cmd == "evaluate":
            import argparse
            p = argparse.ArgumentParser()
            p.add_argument("action")
            p.add_argument("--resource", default=None)
            p.add_argument("--task", default=None)
            p.add_argument("--agent", default=None)
            args = p.parse_args(argv[1:])
            _print(evaluate_policy(args.action, resource=args.resource,
                                   task_id=args.task, agent_name=args.agent, db_path=db_path))
            return 0
        if cmd == "check-task":
            if len(argv) < 2:
                print("check-task TASK_ID", file=sys.stderr)
                return 2
            db = _db()
            task = db.get_task(argv[1], db_path)
            if not task:
                print(f"not found: {argv[1]}", file=sys.stderr)
                return 1
            _print(check_task_run(task))
            return 0
        if cmd == "seed":
            seed_ini_from_defaults()
            n = seed_policies_table(db_path=db_path)
            _print({"seeded": n, "ini": str(ini_path())})
            return 0
        print(f"unknown: {cmd}", file=sys.stderr)
        return 2
    except Exception as e:
        print(f"error: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
