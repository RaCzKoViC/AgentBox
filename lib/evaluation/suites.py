"""Benchmark suite registry — filesystem + DB."""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any, Optional

_HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(_HERE.parent))

from storage import db as dbmod  # noqa: E402
from evaluation import store  # noqa: E402

def _resolve_root() -> Path:
    import os
    env = os.environ.get("AGENTBOX_V5_ROOT")
    if env and Path(env).is_dir():
        return Path(env)
    # source tree (lib/evaluation -> agentbox-v5)
    cand = Path(__file__).resolve().parent.parent.parent
    if (cand / "benchmarks").is_dir():
        return cand
    # installed: ~/.local/share/agentbox/v5 or alongside lib
    share = Path.home() / ".local" / "share" / "agentbox" / "v5"
    if (share / "benchmarks").is_dir():
        return share
    return cand

ROOT = _resolve_root()
BENCHMARKS_ROOT = ROOT / "benchmarks"


def _load_yaml(path: Path) -> dict[str, Any]:
    text = path.read_text(encoding="utf-8")
    try:
        import yaml  # type: ignore
        return yaml.safe_load(text) or {}
    except Exception:
        # minimal YAML subset for our golden fixtures (key: value / lists)
        return _simple_yaml(text)


def _simple_yaml(text: str) -> dict[str, Any]:
    """Tiny YAML-ish parser for flat keys + nested blocks we need."""
    try:
        import json as _json
        # if somehow JSON
        if text.strip().startswith("{"):
            return _json.loads(text)
    except Exception:
        pass
    data: dict[str, Any] = {}
    stack: list[tuple[int, Any]] = [(0, data)]
    pending_key: Optional[str] = None
    for raw in text.splitlines():
        if not raw.strip() or raw.strip().startswith("#"):
            continue
        indent = len(raw) - len(raw.lstrip(" "))
        line = raw.strip()
        while len(stack) > 1 and indent < stack[-1][0]:
            stack.pop()
        cur = stack[-1][1]
        if line.startswith("- "):
            item = line[2:].strip()
            if isinstance(cur, list):
                if ":" in item and not item.startswith("{"):
                    k, v = item.split(":", 1)
                    cur.append({k.strip(): _coerce(v.strip())})
                else:
                    cur.append(_coerce(item))
            elif pending_key is not None and isinstance(cur, dict):
                lst: list[Any] = []
                cur[pending_key] = lst
                stack.append((indent, lst))
                pending_key = None
                if ":" in item:
                    k, v = item.split(":", 1)
                    lst.append({k.strip(): _coerce(v.strip())})
                else:
                    lst.append(_coerce(item))
            continue
        if ":" in line:
            k, v = line.split(":", 1)
            k, v = k.strip(), v.strip()
            if v == "" or v == "|" or v == ">":
                pending_key = k
                # peek next — leave empty dict/list placeholder
                cur[k] = {}
                stack.append((indent + 2, cur[k]))
            else:
                cur[k] = _coerce(v)
                pending_key = None
    return data


def _coerce(v: str) -> Any:
    if v.lower() in ("true", "yes"):
        return True
    if v.lower() in ("false", "no"):
        return False
    if v.lower() in ("null", "none", "~"):
        return None
    try:
        if "." in v:
            return float(v)
        return int(v)
    except ValueError:
        pass
    if (v.startswith('"') and v.endswith('"')) or (v.startswith("'") and v.endswith("'")):
        return v[1:-1]
    return v


def discover_suites() -> list[dict[str, Any]]:
    suites: list[dict[str, Any]] = []
    if not BENCHMARKS_ROOT.is_dir():
        return suites
    # golden/
    golden = BENCHMARKS_ROOT / "golden"
    if golden.is_dir():
        suite_meta = {"id": "golden", "name": "golden", "version": 1,
                      "description": "Fast deterministic golden checks", "path": str(golden)}
        meta_file = golden / "suite.yaml"
        if meta_file.is_file():
            m = _load_yaml(meta_file)
            suite_meta.update({k: m[k] for k in ("id", "name", "version", "description") if k in m})
        cases = []
        for child in sorted(golden.iterdir()):
            if not child.is_dir():
                continue
            task = child / "task.yaml"
            if task.is_file():
                td = _load_yaml(task)
                cases.append({
                    "id": td.get("id") or child.name,
                    "name": td.get("name") or child.name,
                    "path": str(child),
                    "definition": td,
                    "critical": bool(td.get("critical", True)),
                })
        suite_meta["cases"] = cases
        suites.append(suite_meta)
    # other top-level suite dirs with suite.yaml
    for child in sorted(BENCHMARKS_ROOT.iterdir()):
        if not child.is_dir() or child.name == "golden":
            continue
        meta_file = child / "suite.yaml"
        if not meta_file.is_file():
            continue
        m = _load_yaml(meta_file)
        suite_meta = {
            "id": m.get("id") or child.name,
            "name": m.get("name") or child.name,
            "version": int(m.get("version") or 1),
            "description": m.get("description") or "",
            "path": str(child),
            "cases": [],
        }
        for cdir in sorted(child.iterdir()):
            if cdir.is_dir() and (cdir / "task.yaml").is_file():
                td = _load_yaml(cdir / "task.yaml")
                suite_meta["cases"].append({
                    "id": td.get("id") or cdir.name,
                    "name": td.get("name") or cdir.name,
                    "path": str(cdir),
                    "definition": td,
                    "critical": bool(td.get("critical", True)),
                })
        suites.append(suite_meta)
    return suites


def sync_suites_to_db() -> dict[str, Any]:
    suites = discover_suites()
    with dbmod.connect() as conn:
        store.ensure_schema(conn)
        for s in suites:
            conn.execute(
                """INSERT INTO benchmark_suites (id, name, version, description, enabled, path, meta_json, created_at)
                   VALUES (?,?,?,?,1,?,?,?)
                   ON CONFLICT(id) DO UPDATE SET
                     name=excluded.name, version=excluded.version, description=excluded.description,
                     path=excluded.path, meta_json=excluded.meta_json""",
                (s["id"], s["name"], int(s.get("version") or 1), s.get("description") or "",
                 s.get("path") or "", json.dumps({"case_count": len(s.get("cases") or [])}),
                 dbmod.utc_now()),
            )
            for c in s.get("cases") or []:
                conn.execute(
                    """INSERT INTO benchmark_cases (id, suite_id, name, definition_json, version, enabled, critical, created_at)
                       VALUES (?,?,?,?,1,1,?,?)
                       ON CONFLICT(id) DO UPDATE SET
                         name=excluded.name, definition_json=excluded.definition_json,
                         critical=excluded.critical""",
                    (c["id"], s["id"], c["name"],
                     json.dumps(c.get("definition") or {}, default=str),
                     1 if c.get("critical", True) else 0, dbmod.utc_now()),
                )
        conn.commit()
    return {"suites": len(suites), "cases": sum(len(s.get("cases") or []) for s in suites)}


def list_suites(sync: bool = True) -> list[dict[str, Any]]:
    if sync:
        sync_suites_to_db()
    discovered = {s["id"]: s for s in discover_suites()}
    with dbmod.connect() as conn:
        store.ensure_schema(conn)
        rows = conn.execute(
            "SELECT * FROM benchmark_suites WHERE enabled=1 ORDER BY name"
        ).fetchall()
        out = []
        for r in rows:
            d = dict(r)
            disc = discovered.get(d["id"], {})
            d["cases"] = disc.get("cases") or []
            d["case_count"] = len(d["cases"]) or (
                conn.execute(
                    "SELECT COUNT(*) FROM benchmark_cases WHERE suite_id=? AND enabled=1",
                    (d["id"],),
                ).fetchone()[0]
            )
            out.append(d)
        # include discovered not yet in DB
        for sid, s in discovered.items():
            if sid not in {x["id"] for x in out}:
                out.append({**s, "case_count": len(s.get("cases") or [])})
        return out


def get_suite(suite_id: str) -> Optional[dict[str, Any]]:
    for s in list_suites(sync=True):
        if s["id"] == suite_id or s.get("name") == suite_id:
            return s
    return None
