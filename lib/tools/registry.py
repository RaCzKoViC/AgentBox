#!/usr/bin/env python3
"""Tool Registry v2 — register, list, enable/disable/quarantine tools."""
from __future__ import annotations

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


def _db():
    _ensure_path()
    from storage import db as dbmod
    return dbmod


def manifests_dir() -> Path:
    return _HERE / "manifests"


def ensure_schema(db_path: Optional[str] = None) -> None:
    """Ensure tools tables exist (idempotent)."""
    db = _db()
    with db.connect(db_path) as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS tools (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                display_name TEXT,
                category TEXT NOT NULL,
                provider TEXT DEFAULT 'builtin',
                version TEXT DEFAULT '1.0.0',
                enabled INTEGER NOT NULL DEFAULT 1,
                execution_mode TEXT NOT NULL DEFAULT 'local',
                capabilities_json TEXT NOT NULL DEFAULT '[]',
                permissions_json TEXT DEFAULT '[]',
                risk_level TEXT DEFAULT 'LOW',
                cost_profile_json TEXT DEFAULT '{}',
                timeout_seconds INTEGER DEFAULT 60,
                retry_policy_json TEXT DEFAULT '{}',
                health_status TEXT DEFAULT 'unknown',
                worker_requirements_json TEXT DEFAULT '{}',
                input_schema_json TEXT DEFAULT '{}',
                output_schema_json TEXT DEFAULT '{}',
                manifest_json TEXT DEFAULT '{}',
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS tool_versions (
                id TEXT PRIMARY KEY,
                tool_id TEXT NOT NULL,
                version TEXT NOT NULL,
                changelog TEXT DEFAULT '',
                input_schema_json TEXT DEFAULT '{}',
                output_schema_json TEXT DEFAULT '{}',
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(tool_id) REFERENCES tools(id)
            );
            CREATE TABLE IF NOT EXISTS tool_calls (
                id TEXT PRIMARY KEY,
                tool_id TEXT NOT NULL,
                task_id TEXT,
                run_id TEXT,
                agent_name TEXT,
                worker_id TEXT,
                status TEXT NOT NULL DEFAULT 'pending',
                input_json TEXT DEFAULT '{}',
                output_json TEXT DEFAULT '{}',
                input_hash TEXT,
                output_hash TEXT,
                exit_code INTEGER,
                duration_ms INTEGER,
                risk_score INTEGER,
                risk_level TEXT,
                cost REAL DEFAULT 0,
                decision TEXT,
                approval_id TEXT,
                error TEXT,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                finished_at TEXT,
                FOREIGN KEY(tool_id) REFERENCES tools(id)
            );
            CREATE TABLE IF NOT EXISTS tool_outcomes (
                id TEXT PRIMARY KEY,
                tool_id TEXT NOT NULL,
                call_id TEXT,
                capability TEXT,
                task_type TEXT DEFAULT '',
                input_class TEXT DEFAULT '',
                success INTEGER NOT NULL DEFAULT 0,
                failure_type TEXT,
                latency_ms INTEGER,
                worker_id TEXT,
                provider TEXT,
                meta_json TEXT DEFAULT '{}',
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(tool_id) REFERENCES tools(id)
            );
            CREATE TABLE IF NOT EXISTS tool_permissions (
                id TEXT PRIMARY KEY,
                agent_name TEXT NOT NULL,
                tool_id TEXT,
                capability TEXT,
                allowed INTEGER NOT NULL DEFAULT 1,
                requires_approval INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS mcp_servers (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                transport TEXT NOT NULL DEFAULT 'stdio',
                endpoint TEXT,
                command TEXT,
                enabled INTEGER NOT NULL DEFAULT 1,
                auth_mode TEXT DEFAULT 'none',
                trust_level TEXT DEFAULT 'standard',
                health_status TEXT DEFAULT 'unknown',
                capabilities_json TEXT DEFAULT '[]',
                metadata_json TEXT DEFAULT '{}',
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS tool_reliability (
                tool_id TEXT PRIMARY KEY,
                success_count INTEGER NOT NULL DEFAULT 0,
                failure_count INTEGER NOT NULL DEFAULT 0,
                timeout_count INTEGER NOT NULL DEFAULT 0,
                validation_failure_count INTEGER NOT NULL DEFAULT 0,
                retry_count INTEGER NOT NULL DEFAULT 0,
                reliability_score REAL NOT NULL DEFAULT 50,
                avg_latency_ms REAL,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(tool_id) REFERENCES tools(id)
            );
            CREATE INDEX IF NOT EXISTS idx_tools_category ON tools(category);
            CREATE INDEX IF NOT EXISTS idx_tools_health ON tools(health_status);
            CREATE INDEX IF NOT EXISTS idx_tool_calls_tool ON tool_calls(tool_id);
            CREATE INDEX IF NOT EXISTS idx_tool_calls_status ON tool_calls(status);
            CREATE INDEX IF NOT EXISTS idx_tool_outcomes_tool ON tool_outcomes(tool_id);
            CREATE INDEX IF NOT EXISTS idx_mcp_enabled ON mcp_servers(enabled);
            """
        )
        conn.commit()


def _row_to_tool(row) -> dict[str, Any]:
    d = dict(row)
    for k in (
        "capabilities_json", "permissions_json", "cost_profile_json",
        "retry_policy_json", "worker_requirements_json",
        "input_schema_json", "output_schema_json", "manifest_json",
    ):
        raw = d.pop(k, None) if k in d else None
        key = k.replace("_json", "") if k.endswith("_json") else k
        # keep both styles: capabilities + capabilities_json-free
        short = key
        if short.endswith("_json"):
            short = short[:-5]
        try:
            d[short if not short.endswith("s") or True else short] = json.loads(raw or ("[]" if "capabilities" in k or "permissions" in k else "{}"))
        except Exception:
            d[short] = [] if "capabilities" in k or "permissions" in k else {}
    # normalize keys
    if "capabilities" not in d and "capabilities" in locals():
        pass
    caps = d.get("capabilities")
    if caps is None:
        d["capabilities"] = []
    return d


def register_tool(manifest: dict[str, Any], db_path: Optional[str] = None) -> dict[str, Any]:
    ensure_schema(db_path)
    db = _db()
    tid = manifest.get("id") or manifest.get("name")
    if not tid:
        raise ValueError("tool manifest requires id")
    now = db.utc_now()
    caps = manifest.get("capabilities") or []
    perms = manifest.get("permissions") or []
    risk = (manifest.get("risk") or {}).get("default") if isinstance(manifest.get("risk"), dict) else (manifest.get("risk_level") or "LOW")
    cost = manifest.get("cost_profile") or {}
    timeout = (manifest.get("execution") or {}).get("timeout") if isinstance(manifest.get("execution"), dict) else manifest.get("timeout_seconds", 60)
    mode = (manifest.get("execution") or {}).get("mode") if isinstance(manifest.get("execution"), dict) else manifest.get("execution_mode", "local")
    with db.connect(db_path) as conn:
        conn.execute(
            """
            INSERT INTO tools (
                id, name, display_name, category, provider, version, enabled,
                execution_mode, capabilities_json, permissions_json, risk_level,
                cost_profile_json, timeout_seconds, health_status,
                input_schema_json, output_schema_json, manifest_json, created_at, updated_at
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            ON CONFLICT(id) DO UPDATE SET
                name=excluded.name,
                display_name=excluded.display_name,
                category=excluded.category,
                provider=excluded.provider,
                version=excluded.version,
                execution_mode=excluded.execution_mode,
                capabilities_json=excluded.capabilities_json,
                permissions_json=excluded.permissions_json,
                risk_level=excluded.risk_level,
                cost_profile_json=excluded.cost_profile_json,
                timeout_seconds=excluded.timeout_seconds,
                input_schema_json=excluded.input_schema_json,
                output_schema_json=excluded.output_schema_json,
                manifest_json=excluded.manifest_json,
                updated_at=excluded.updated_at
            """,
            (
                tid,
                manifest.get("name") or tid,
                manifest.get("display_name") or manifest.get("name") or tid,
                manifest.get("category") or "custom",
                manifest.get("provider") or "builtin",
                str(manifest.get("version") or "1.0.0"),
                1 if manifest.get("enabled", True) else 0,
                mode or "local",
                json.dumps(caps),
                json.dumps(perms),
                str(risk or "LOW").upper(),
                json.dumps(cost),
                int(timeout or 60),
                manifest.get("health_status") or "unknown",
                json.dumps(manifest.get("input_schema") or {}),
                json.dumps(manifest.get("output_schema") or {}),
                json.dumps(manifest),
                now,
                now,
            ),
        )
        vid = db.new_id("tv_")
        conn.execute(
            """
            INSERT OR IGNORE INTO tool_versions (id, tool_id, version, input_schema_json, output_schema_json, created_at)
            VALUES (?,?,?,?,?,?)
            """,
            (
                vid, tid, str(manifest.get("version") or "1.0.0"),
                json.dumps(manifest.get("input_schema") or {}),
                json.dumps(manifest.get("output_schema") or {}),
                now,
            ),
        )
        conn.execute(
            """
            INSERT OR IGNORE INTO tool_reliability (tool_id, reliability_score, updated_at)
            VALUES (?, 70, ?)
            """,
            (tid, now),
        )
        conn.commit()
    try:
        db.emit_event(kind="tool.registered", message=f"registered {tid}", payload={"tool_id": tid})
    except Exception:
        pass
    return get_tool(tid, db_path=db_path) or {"id": tid}


def get_tool(tool_id: str, db_path: Optional[str] = None) -> Optional[dict[str, Any]]:
    ensure_schema(db_path)
    db = _db()
    with db.connect(db_path) as conn:
        row = conn.execute("SELECT * FROM tools WHERE id = ?", (tool_id,)).fetchone()
        if not row:
            # also try by name
            row = conn.execute("SELECT * FROM tools WHERE name = ?", (tool_id,)).fetchone()
        if not row:
            return None
        t = dict(row)
        for k, default in (
            ("capabilities_json", "[]"),
            ("permissions_json", "[]"),
            ("cost_profile_json", "{}"),
            ("retry_policy_json", "{}"),
            ("worker_requirements_json", "{}"),
            ("input_schema_json", "{}"),
            ("output_schema_json", "{}"),
            ("manifest_json", "{}"),
        ):
            raw = t.get(k) or default
            short = k.replace("_json", "")
            try:
                t[short] = json.loads(raw)
            except Exception:
                t[short] = json.loads(default)
        rel = conn.execute("SELECT * FROM tool_reliability WHERE tool_id = ?", (t["id"],)).fetchone()
        if rel:
            t["reliability"] = dict(rel)
        return t


def list_tools(
    category: Optional[str] = None,
    enabled_only: bool = False,
    query: Optional[str] = None,
    db_path: Optional[str] = None,
) -> list[dict[str, Any]]:
    ensure_schema(db_path)
    db = _db()
    sql = "SELECT * FROM tools WHERE 1=1"
    params: list[Any] = []
    if category:
        sql += " AND category = ?"
        params.append(category)
    if enabled_only:
        sql += " AND enabled = 1 AND health_status != 'quarantined'"
    if query:
        q = f"%{query.lower()}%"
        sql += " AND (lower(id) LIKE ? OR lower(name) LIKE ? OR lower(category) LIKE ? OR lower(capabilities_json) LIKE ?)"
        params.extend([q, q, q, q])
    sql += " ORDER BY category, name"
    with db.connect(db_path) as conn:
        rows = conn.execute(sql, params).fetchall()
        out = []
        for row in rows:
            t = dict(row)
            try:
                t["capabilities"] = json.loads(t.get("capabilities_json") or "[]")
            except Exception:
                t["capabilities"] = []
            try:
                t["input_schema"] = json.loads(t.get("input_schema_json") or "{}")
            except Exception:
                t["input_schema"] = {}
            rel = conn.execute(
                "SELECT reliability_score, success_count, failure_count, avg_latency_ms FROM tool_reliability WHERE tool_id=?",
                (t["id"],),
            ).fetchone()
            if rel:
                t["reliability_score"] = rel["reliability_score"]
                t["success_count"] = rel["success_count"]
                t["failure_count"] = rel["failure_count"]
            out.append(t)
        return out


def set_enabled(tool_id: str, enabled: bool, db_path: Optional[str] = None) -> Optional[dict]:
    ensure_schema(db_path)
    db = _db()
    with db.connect(db_path) as conn:
        conn.execute(
            "UPDATE tools SET enabled=?, updated_at=? WHERE id=?",
            (1 if enabled else 0, db.utc_now(), tool_id),
        )
        conn.commit()
    return get_tool(tool_id, db_path=db_path)


def quarantine(tool_id: str, reason: str = "", db_path: Optional[str] = None) -> Optional[dict]:
    ensure_schema(db_path)
    db = _db()
    with db.connect(db_path) as conn:
        conn.execute(
            "UPDATE tools SET health_status='quarantined', enabled=0, updated_at=? WHERE id=?",
            (db.utc_now(), tool_id),
        )
        conn.commit()
    try:
        db.emit_event(kind="tool.quarantined", message=reason or tool_id, payload={"tool_id": tool_id, "reason": reason})
    except Exception:
        pass
    return get_tool(tool_id, db_path=db_path)


def set_health(tool_id: str, status: str, db_path: Optional[str] = None) -> None:
    ensure_schema(db_path)
    db = _db()
    with db.connect(db_path) as conn:
        conn.execute(
            "UPDATE tools SET health_status=?, updated_at=? WHERE id=?",
            (status, db.utc_now(), tool_id),
        )
        conn.commit()


def load_manifest_file(path: Path) -> dict[str, Any]:
    text = path.read_text(encoding="utf-8")
    if path.suffix in (".yaml", ".yml"):
        try:
            import yaml  # type: ignore
            return yaml.safe_load(text) or {}
        except Exception:
            # minimal YAML-ish fallback: prefer JSON manifests
            pass
    return json.loads(text)


def ensure_builtins(db_path: Optional[str] = None) -> list[dict[str, Any]]:
    """Register all manifests from manifests/ directory."""
    ensure_schema(db_path)
    registered = []
    mdir = manifests_dir()
    if not mdir.is_dir():
        return registered
    for path in sorted(mdir.glob("*.json")):
        try:
            man = load_manifest_file(path)
            registered.append(register_tool(man, db_path=db_path))
        except Exception as exc:
            registered.append({"error": str(exc), "path": str(path)})
    return registered


def search_tools(query: str, db_path: Optional[str] = None) -> list[dict[str, Any]]:
    return list_tools(query=query, enabled_only=False, db_path=db_path)
