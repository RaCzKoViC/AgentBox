"""Configuration / Worker / Provider drift detection."""
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path
from typing import Any, Optional

_HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(_HERE.parent))

from ops.paths import config_dir, share_config_dir  # noqa: E402
from storage import db as dbmod  # noqa: E402
from ops_autopilot import store  # noqa: E402

WATCH_FILES = [
    "agentbox.toml",
    "providers.toml",
    "policies.toml",
    "budgets.toml",
    "tools.toml",
    "evaluation.toml",
    "intelligence.toml",
    "web.ini",
    "backup.ini",
    "recovery.ini",
]


def _hash_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


def _resolve_config(name: str) -> Optional[Path]:
    for base in (config_dir(), share_config_dir(), Path(__file__).resolve().parents[2] / "config"):
        p = base / name
        if p.is_file():
            return p
    return None


def _baseline_path() -> Path:
    from ops.paths import data_home
    d = data_home() / "ops_autopilot"
    d.mkdir(parents=True, exist_ok=True)
    return d / "drift_baseline.json"


def load_baseline() -> dict[str, Any]:
    bp = _baseline_path()
    if bp.is_file():
        try:
            return json.loads(bp.read_text(encoding="utf-8"))
        except Exception:
            return {}
    return {}


def save_baseline(data: dict[str, Any]) -> None:
    _baseline_path().write_text(json.dumps(data, indent=2, sort_keys=True), encoding="utf-8")


def snapshot_config() -> dict[str, Any]:
    files = {}
    for name in WATCH_FILES:
        p = _resolve_config(name)
        if p and p.is_file():
            text = p.read_text(encoding="utf-8", errors="replace")
            files[name] = {"hash": _hash_text(text), "path": str(p), "size": len(text)}
        else:
            files[name] = {"hash": None, "path": None, "size": 0, "missing": True}
    blob = json.dumps({k: v["hash"] for k, v in sorted(files.items())}, sort_keys=True)
    return {"files": files, "hash": _hash_text(blob)}


def snapshot_workers() -> dict[str, Any]:
    try:
        from distributed.registry import list_workers
        workers = list_workers()
    except Exception as e:
        return {"hash": "error", "workers": [], "error": str(e)}
    compact = [
        {
            "id": w.get("id"),
            "status": w.get("status"),
            "quarantined": int(w.get("quarantined") or 0),
            "hostname": w.get("hostname") or w.get("host"),
        }
        for w in workers
    ]
    blob = json.dumps(compact, sort_keys=True, default=str)
    return {"workers": compact, "count": len(compact), "hash": _hash_text(blob)}


def snapshot_providers() -> dict[str, Any]:
    p = _resolve_config("providers.toml")
    if not p:
        return {"hash": "missing", "providers": {}, "missing": True}
    text = p.read_text(encoding="utf-8", errors="replace")
    # crude section parse
    providers = {}
    current = None
    for line in text.splitlines():
        line = line.strip()
        if line.startswith("[") and line.endswith("]"):
            current = line[1:-1].strip()
            providers[current] = {"enabled": None}
        elif current and line.startswith("enabled"):
            val = line.split("=", 1)[-1].strip().lower()
            providers[current]["enabled"] = val in ("true", "1", "yes")
    blob = json.dumps(providers, sort_keys=True)
    return {"providers": providers, "hash": _hash_text(blob), "path": str(p)}


def detect_config(persist: bool = True) -> dict[str, Any]:
    current = snapshot_config()
    baseline = load_baseline()
    base_cfg = baseline.get("config") or {}
    findings = []
    if not base_cfg:
        # first run — establish baseline
        baseline["config"] = {"hash": current["hash"], "files": {k: v["hash"] for k, v in current["files"].items()}}
        save_baseline(baseline)
        drifted = False
        findings.append({"kind": "baseline_established", "scope": "config"})
    else:
        for name, info in current["files"].items():
            bh = (base_cfg.get("files") or {}).get(name)
            ch = info.get("hash")
            if bh != ch:
                findings.append({
                    "kind": "file_changed",
                    "file": name,
                    "baseline_hash": bh,
                    "current_hash": ch,
                    "missing": info.get("missing", False),
                })
        drifted = len([f for f in findings if f["kind"] == "file_changed"]) > 0

    snap_id = None
    if persist:
        snap_id = dbmod.new_id("drift_")
        with dbmod.connect() as conn:
            store.ensure_schema(conn)
            store.insert_drift(
                conn,
                {
                    "id": snap_id,
                    "scope": "config",
                    "baseline_hash": (base_cfg or {}).get("hash", ""),
                    "current_hash": current["hash"],
                    "drifted": drifted,
                    "findings": findings,
                },
            )
            conn.commit()
    return {
        "scope": "config",
        "drifted": drifted,
        "findings": findings,
        "current_hash": current["hash"],
        "baseline_hash": (base_cfg or {}).get("hash", ""),
        "snapshot_id": snap_id,
    }


def detect_workers(persist: bool = True) -> dict[str, Any]:
    current = snapshot_workers()
    baseline = load_baseline()
    base_w = baseline.get("workers") or {}
    findings = []
    if not base_w:
        baseline["workers"] = {"hash": current["hash"], "count": current.get("count", 0)}
        save_baseline(baseline)
        drifted = False
        findings.append({"kind": "baseline_established", "scope": "workers"})
    else:
        if base_w.get("hash") != current["hash"]:
            findings.append({
                "kind": "worker_set_changed",
                "baseline_hash": base_w.get("hash"),
                "current_hash": current["hash"],
                "baseline_count": base_w.get("count"),
                "current_count": current.get("count"),
            })
        # quarantine drift
        for w in current.get("workers") or []:
            if int(w.get("quarantined") or 0) or w.get("status") == "quarantined":
                findings.append({"kind": "worker_quarantined", "worker_id": w.get("id")})
        drifted = any(f["kind"] != "baseline_established" for f in findings)

    snap_id = None
    if persist:
        snap_id = dbmod.new_id("drift_")
        with dbmod.connect() as conn:
            store.ensure_schema(conn)
            store.insert_drift(
                conn,
                {
                    "id": snap_id,
                    "scope": "workers",
                    "baseline_hash": base_w.get("hash", ""),
                    "current_hash": current["hash"],
                    "drifted": drifted,
                    "findings": findings,
                },
            )
            conn.commit()
    return {
        "scope": "workers",
        "drifted": drifted,
        "findings": findings,
        "current": current,
        "snapshot_id": snap_id,
    }


def detect_providers(persist: bool = True) -> dict[str, Any]:
    current = snapshot_providers()
    baseline = load_baseline()
    base_p = baseline.get("providers") or {}
    findings = []
    if not base_p:
        baseline["providers"] = {"hash": current["hash"], "providers": current.get("providers")}
        save_baseline(baseline)
        drifted = False
        findings.append({"kind": "baseline_established", "scope": "providers"})
    else:
        if base_p.get("hash") != current["hash"]:
            findings.append({
                "kind": "providers_changed",
                "baseline_hash": base_p.get("hash"),
                "current_hash": current["hash"],
                "baseline": base_p.get("providers"),
                "current": current.get("providers"),
            })
        drifted = len(findings) > 0

    snap_id = None
    if persist:
        snap_id = dbmod.new_id("drift_")
        with dbmod.connect() as conn:
            store.ensure_schema(conn)
            store.insert_drift(
                conn,
                {
                    "id": snap_id,
                    "scope": "providers",
                    "baseline_hash": base_p.get("hash", ""),
                    "current_hash": current["hash"],
                    "drifted": drifted,
                    "findings": findings,
                },
            )
            conn.commit()
    return {
        "scope": "providers",
        "drifted": drifted,
        "findings": findings,
        "current": current,
        "snapshot_id": snap_id,
    }


def detect_all(persist: bool = True) -> dict[str, Any]:
    scopes = {
        "config": detect_config(persist=persist),
        "workers": detect_workers(persist=persist),
        "providers": detect_providers(persist=persist),
    }
    drifted = any(s.get("drifted") for s in scopes.values())
    return {
        "drifted": drifted,
        "scopes": scopes,
        "snapshot_ids": [s.get("snapshot_id") for s in scopes.values() if s.get("snapshot_id")],
    }


def reset_baseline() -> dict[str, Any]:
    cfg = snapshot_config()
    wrk = snapshot_workers()
    prv = snapshot_providers()
    data = {
        "config": {"hash": cfg["hash"], "files": {k: v["hash"] for k, v in cfg["files"].items()}},
        "workers": {"hash": wrk["hash"], "count": wrk.get("count", 0)},
        "providers": {"hash": prv["hash"], "providers": prv.get("providers")},
    }
    save_baseline(data)
    return {"ok": True, "baseline": data}
