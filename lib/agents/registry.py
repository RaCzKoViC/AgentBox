#!/usr/bin/env python3
"""AgentBox v5 agent registry — register / list / show / set / can_delegate (beta2)."""
from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

ALLOWED_STATUSES = frozenset({"active", "disabled", "idle", "busy", "error"})


def utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def _ensure_path() -> None:
    lib = str(Path(__file__).resolve().parent.parent)
    if lib not in sys.path:
        sys.path.insert(0, lib)


def _db():
    _ensure_path()
    from storage import db as dbmod  # type: ignore

    return dbmod


def register_agent(
    agent_id: str,
    name: str,
    role: str = "",
    capabilities: Optional[list] = None,
    provider: str = "",
    model: str = "",
    status: str = "active",
    meta: Optional[dict] = None,
    db_path: Optional[str] = None,
) -> dict:
    agent_id = (agent_id or "").strip()
    if not agent_id:
        raise ValueError("agent id required")
    name = (name or agent_id).strip()
    status = (status or "active").strip().lower()
    if status not in ALLOWED_STATUSES:
        raise ValueError(f"invalid status: {status}; allowed: {sorted(ALLOWED_STATUSES)}")
    now = utc_now()
    caps_json = json.dumps(list(capabilities or []))
    meta_json = json.dumps(meta or {})
    db = _db()
    with db.connect(db_path) as conn:
        existing = conn.execute("SELECT id FROM agents WHERE id = ?", (agent_id,)).fetchone()
        if existing:
            conn.execute(
                """
                UPDATE agents SET name=?, role=?, capabilities_json=?, provider=?, model=?,
                    status=?, meta_json=?, updated_at=?
                WHERE id=?
                """,
                (name, role or "", caps_json, provider or "", model or "", status, meta_json, now, agent_id),
            )
        else:
            # Support both old (kind) and new schema
            cols = {r[1] for r in conn.execute("PRAGMA table_info(agents)").fetchall()}
            if "role" in cols:
                conn.execute(
                    """
                    INSERT INTO agents (
                        id, name, role, capabilities_json, provider, model,
                        status, meta_json, created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        agent_id, name, role or "", caps_json, provider or "", model or "",
                        status, meta_json, now, now,
                    ),
                )
            else:
                conn.execute(
                    """
                    INSERT INTO agents (id, name, kind, status, meta_json, created_at, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (agent_id, name, role or "stub", status, meta_json, now, now),
                )
        conn.commit()
    return get_agent(agent_id, db_path=db_path)  # type: ignore[return-value]


def get_agent(agent_id: str, db_path: Optional[str] = None) -> Optional[dict]:
    db = _db()
    with db.connect(db_path) as conn:
        row = conn.execute("SELECT * FROM agents WHERE id = ?", (agent_id,)).fetchone()
        if not row:
            return None
        d = dict(row)
        # Normalize for callers
        if "role" not in d and "kind" in d:
            d["role"] = d.get("kind") or ""
        if "capabilities_json" not in d:
            d["capabilities_json"] = "[]"
        if "provider" not in d:
            d["provider"] = ""
        if "model" not in d:
            d["model"] = ""
        return d


def list_agents(status: Optional[str] = None, db_path: Optional[str] = None) -> list[dict]:
    db = _db()
    with db.connect(db_path) as conn:
        if status:
            rows = conn.execute(
                "SELECT * FROM agents WHERE status = ? ORDER BY name ASC",
                (status,),
            ).fetchall()
        else:
            rows = conn.execute("SELECT * FROM agents ORDER BY name ASC").fetchall()
        out = []
        for r in rows:
            d = dict(r)
            if "role" not in d and "kind" in d:
                d["role"] = d.get("kind") or ""
            out.append(d)
        return out


def set_agent_status(agent_id: str, status: str, db_path: Optional[str] = None) -> dict:
    status = (status or "").strip().lower()
    if status not in ALLOWED_STATUSES:
        raise ValueError(f"invalid status: {status}; allowed: {sorted(ALLOWED_STATUSES)}")
    row = get_agent(agent_id, db_path=db_path)
    if not row:
        raise KeyError(f"agent not found: {agent_id}")
    now = utc_now()
    db = _db()
    with db.connect(db_path) as conn:
        conn.execute(
            "UPDATE agents SET status = ?, updated_at = ? WHERE id = ?",
            (status, now, agent_id),
        )
        conn.commit()
    return get_agent(agent_id, db_path=db_path)  # type: ignore[return-value]


def update_agent(
    agent_id: str,
    *,
    name: Optional[str] = None,
    role: Optional[str] = None,
    provider: Optional[str] = None,
    model: Optional[str] = None,
    capabilities: Optional[list] = None,
    status: Optional[str] = None,
    db_path: Optional[str] = None,
) -> dict:
    row = get_agent(agent_id, db_path=db_path)
    if not row:
        raise KeyError(f"agent not found: {agent_id}")
    return register_agent(
        agent_id=agent_id,
        name=name if name is not None else row.get("name", agent_id),
        role=role if role is not None else row.get("role", ""),
        capabilities=capabilities if capabilities is not None else json.loads(row.get("capabilities_json") or "[]"),
        provider=provider if provider is not None else row.get("provider", ""),
        model=model if model is not None else row.get("model", ""),
        status=status if status is not None else row.get("status", "active"),
        meta=json.loads(row.get("meta_json") or "{}"),
        db_path=db_path,
    )



# Default can_delegate matrix (overridden by config/agents.toml [delegate])
DEFAULT_DELEGATE: dict[str, list[str]] = {
    "planner": ["researcher", "architect"],
    "architect": ["security", "performance", "coder"],
    "coder": ["tester", "debugger"],
    "tester": ["debugger"],
    "reviewer": ["security", "debugger"],
}


def _agents_toml_paths() -> list[Path]:
    home = Path(os.environ.get("AGENTBOX_V5_HOME", Path.home() / ".local/share/agentbox/v5"))
    lib = Path(__file__).resolve().parent.parent
    return [
        home / "config" / "agents.toml",
        lib.parent / "config" / "agents.toml",
    ]


def load_delegate_matrix() -> dict[str, list[str]]:
    """Load [delegate] from agents.toml; fall back to DEFAULT_DELEGATE."""
    matrix = {k: list(v) for k, v in DEFAULT_DELEGATE.items()}
    path = next((p for p in _agents_toml_paths() if p.is_file()), None)
    if not path:
        return matrix
    try:
        try:
            import tomllib
        except ImportError:
            import tomli as tomllib  # type: ignore
        with open(path, "rb") as f:
            data = tomllib.load(f)
        dele = data.get("delegate") or {}
        for src, targets in dele.items():
            if isinstance(targets, list):
                matrix[str(src)] = [str(t) for t in targets]
            elif isinstance(targets, str):
                matrix[str(src)] = [t.strip() for t in targets.split(",") if t.strip()]
    except Exception:
        pass
    return matrix


def _role_of(agent_id_or_role: str, db_path: Optional[str] = None) -> str:
    """Resolve agent id → role name; if already a known role, return as-is."""
    key = (agent_id_or_role or "").strip().lower()
    if not key:
        return ""
    matrix = load_delegate_matrix()
    if key in matrix or any(key in targets for targets in matrix.values()):
        # May still be an agent id that equals a role name
        pass
    row = get_agent(key, db_path=db_path)
    if row:
        role = (row.get("role") or row.get("kind") or key).strip().lower()
        return role or key
    return key


def can_delegate(
    source: str,
    target: str,
    db_path: Optional[str] = None,
) -> dict[str, Any]:
    """Return {allowed, reason, source_role, target_role}. Random delegation DENIED."""
    src_role = _role_of(source, db_path=db_path)
    tgt_role = _role_of(target, db_path=db_path)
    if not src_role or not tgt_role:
        return {
            "allowed": False,
            "reason": "missing source or target",
            "source_role": src_role,
            "target_role": tgt_role,
        }
    if src_role == tgt_role and source.strip().lower() == target.strip().lower():
        return {
            "allowed": False,
            "reason": "self-delegation denied",
            "source_role": src_role,
            "target_role": tgt_role,
        }
    matrix = load_delegate_matrix()
    allowed_targets = [t.lower() for t in matrix.get(src_role, [])]
    if tgt_role in allowed_targets:
        return {
            "allowed": True,
            "reason": f"policy allow: {src_role} → {tgt_role}",
            "source_role": src_role,
            "target_role": tgt_role,
        }
    return {
        "allowed": False,
        "reason": f"delegation DENIED (not in can_delegate): {src_role} → {tgt_role}",
        "source_role": src_role,
        "target_role": tgt_role,
    }


def seed_from_config(db_path: Optional[str] = None) -> list[dict]:
    """Register agents defined in config/agents.toml [agents.*]."""
    path = next((p for p in _agents_toml_paths() if p.is_file()), None)
    if not path:
        return []
    try:
        try:
            import tomllib
        except ImportError:
            import tomli as tomllib  # type: ignore
        with open(path, "rb") as f:
            data = tomllib.load(f)
    except Exception:
        return []
    agents_sec = data.get("agents") or {}
    out = []
    for aid, cfg in agents_sec.items():
        if not isinstance(cfg, dict):
            continue
        caps = cfg.get("capabilities") or []
        if isinstance(caps, str):
            caps = [c.strip() for c in caps.split(",") if c.strip()]
        row = register_agent(
            agent_id=str(aid),
            name=str(cfg.get("name") or aid),
            role=str(cfg.get("role") or aid),
            capabilities=list(caps),
            provider=str(cfg.get("provider") or ""),
            model=str(cfg.get("model") or ""),
            status=str(cfg.get("status") or "active"),
            db_path=db_path,
        )
        out.append(row)
    return out


def _print_json(obj: Any) -> None:

    print(json.dumps(obj, indent=2, ensure_ascii=False, default=str))


def main(argv: Optional[list[str]] = None) -> int:
    argv = list(argv if argv is not None else sys.argv[1:])
    if not argv:
        print("usage: registry.py register|list|show|set|can-delegate|seed|delegate-matrix ...", file=sys.stderr)
        return 2
    cmd = argv[0]
    db_path = os.environ.get("AGENTBOX_V5_DB")
    try:
        if cmd == "register":
            import argparse

            p = argparse.ArgumentParser()
            p.add_argument("--id", required=True)
            p.add_argument("--name", required=True)
            p.add_argument("--role", default="")
            p.add_argument("--provider", default="")
            p.add_argument("--model", default="")
            p.add_argument("--status", default="active")
            p.add_argument("--capability", action="append", default=[])
            args = p.parse_args(argv[1:])
            row = register_agent(
                agent_id=args.id,
                name=args.name,
                role=args.role,
                capabilities=args.capability,
                provider=args.provider,
                model=args.model,
                status=args.status,
                db_path=db_path,
            )
            _print_json(row)
            return 0
        if cmd == "list":
            import argparse

            p = argparse.ArgumentParser()
            p.add_argument("--status", default=None)
            args = p.parse_args(argv[1:])
            _print_json(list_agents(status=args.status, db_path=db_path))
            return 0
        if cmd == "show":
            if len(argv) < 2:
                print("show ID", file=sys.stderr)
                return 2
            row = get_agent(argv[1], db_path=db_path)
            if not row:
                print(f"not found: {argv[1]}", file=sys.stderr)
                return 1
            _print_json(row)
            return 0
        if cmd == "set":
            import argparse

            p = argparse.ArgumentParser()
            p.add_argument("agent_id")
            p.add_argument("--status", default=None)
            p.add_argument("--name", default=None)
            p.add_argument("--role", default=None)
            p.add_argument("--provider", default=None)
            p.add_argument("--model", default=None)
            args = p.parse_args(argv[1:])
            if args.status and args.name is None and args.role is None and args.provider is None and args.model is None:
                row = set_agent_status(args.agent_id, args.status, db_path=db_path)
            else:
                row = update_agent(
                    args.agent_id,
                    name=args.name,
                    role=args.role,
                    provider=args.provider,
                    model=args.model,
                    status=args.status,
                    db_path=db_path,
                )
            _print_json(row)
            return 0
        if cmd in ("can-delegate", "can_delegate"):
            if len(argv) < 3:
                print("can-delegate SOURCE TARGET", file=sys.stderr)
                return 2
            _print_json(can_delegate(argv[1], argv[2], db_path=db_path))
            return 0
        if cmd == "seed":
            rows = seed_from_config(db_path=db_path)
            _print_json(rows)
            return 0
        if cmd == "delegate-matrix":
            _print_json(load_delegate_matrix())
            return 0
        print(f"unknown: {cmd}", file=sys.stderr)
        return 2
    except Exception as e:
        print(f"error: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
