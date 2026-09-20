#!/usr/bin/env python3
"""Backup manager — SQLite online backup + config + manifests."""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import socket
import sqlite3
import sys
import tarfile
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

_HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(_HERE.parent))

from ops import SCHEMA_VERSION  # noqa: E402
from ops.paths import (  # noqa: E402
    acquire_lock,
    backups_dir,
    config_dir,
    db_path,
    load_ini,
    read_version,
    release_lock,
    share_config_dir,
)
from storage import db as dbmod  # noqa: E402


def _stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _sqlite_backup(src: Path, dest: Path) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    src_conn = sqlite3.connect(str(src), timeout=60)
    try:
        dst_conn = sqlite3.connect(str(dest), timeout=60)
        try:
            src_conn.backup(dst_conn)
            dst_conn.commit()
        finally:
            dst_conn.close()
    finally:
        src_conn.close()


def create(note: str = "", label: str = "") -> dict[str, Any]:
    acquire_lock("backup", operation_id="backup.create")
    try:
        bid = f"bkp_{_stamp()}"
        if label:
            bid = f"bkp_{label}_{_stamp()}"
        dest = backups_dir() / bid
        dest.mkdir(parents=True, exist_ok=False)

        src_db = db_path()
        db_dest = dest / "agentbox.db"
        if src_db.is_file():
            _sqlite_backup(src_db, db_dest)
        else:
            db_dest.write_bytes(b"")

        # config tarball
        cfg_tar = dest / "config.tar.gz"
        with tarfile.open(cfg_tar, "w:gz") as tar:
            for d in (config_dir(), share_config_dir()):
                if d.is_dir():
                    tar.add(str(d), arcname=d.name)

        ver = read_version()
        (dest / "version.txt").write_text(ver + "\n", encoding="utf-8")

        files = {}
        for name in ("agentbox.db", "config.tar.gz", "version.txt"):
            p = dest / name
            if p.is_file():
                files[name] = {"sha256": _sha256_file(p), "size": p.stat().st_size}

        checksum_path = dest / "checksum.sha256"
        lines = [f"{v['sha256']}  {k}" for k, v in files.items()]
        checksum_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        files["checksum.sha256"] = {
            "sha256": _sha256_file(checksum_path),
            "size": checksum_path.stat().st_size,
        }

        manifest = {
            "backup_id": bid,
            "version": ver,
            "schema_version": SCHEMA_VERSION,
            "created_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "database": "agentbox.db",
            "config": "config.tar.gz",
            "sha256": files.get("agentbox.db", {}).get("sha256", ""),
            "files": files,
            "hostname": socket.gethostname(),
            "environment": "AgentBox",
            "note": note,
            "path": str(dest),
        }
        (dest / "manifest.json").write_text(
            json.dumps(manifest, indent=2) + "\n", encoding="utf-8"
        )
        try:
            dbmod.emit_event(
                kind="backup.created",
                message=f"backup {bid}",
                payload={"backup_id": bid},
            )
        except Exception:
            pass
        return manifest
    finally:
        release_lock("backup")


def list_backups() -> list[dict[str, Any]]:
    out = []
    for d in sorted(backups_dir().iterdir(), reverse=True):
        if not d.is_dir():
            continue
        mf = d / "manifest.json"
        if mf.is_file():
            try:
                out.append(json.loads(mf.read_text(encoding="utf-8")))
                continue
            except Exception:
                pass
        # legacy install backups without manifest
        if d.name.startswith("beta") or d.name.startswith("rc") or d.name.startswith("stable"):
            out.append({
                "backup_id": d.name,
                "path": str(d),
                "version": "legacy",
                "created_at": "",
                "legacy": True,
            })
        elif (d / "agentbox.db").is_file() or (d / "manifest.json").is_file():
            out.append({"backup_id": d.name, "path": str(d), "legacy": True})
    return out


def inspect(backup_id: str) -> dict[str, Any]:
    dest = _resolve(backup_id)
    mf = dest / "manifest.json"
    if mf.is_file():
        data = json.loads(mf.read_text(encoding="utf-8"))
        data["path"] = str(dest)
        data["files_on_disk"] = sorted(p.name for p in dest.iterdir())
        return data
    return {
        "backup_id": backup_id,
        "path": str(dest),
        "legacy": True,
        "files_on_disk": sorted(p.name for p in dest.iterdir()),
    }


def verify(backup_id: str) -> dict[str, Any]:
    dest = _resolve(backup_id)
    mf = dest / "manifest.json"
    errors: list[str] = []
    if not mf.is_file():
        # legacy: just check db exists and quick_check
        db_file = dest / "agentbox.db"
        if not db_file.is_file():
            return {"ok": False, "backup_id": backup_id, "errors": ["no agentbox.db"]}
        from ops.integrity import quick_check
        qc = quick_check(str(db_file))
        return {"ok": qc["ok"], "backup_id": backup_id, "legacy": True, "quick_check": qc}

    manifest = json.loads(mf.read_text(encoding="utf-8"))
    for name, meta in (manifest.get("files") or {}).items():
        if name == "checksum.sha256":
            continue
        p = dest / name
        if not p.is_file():
            errors.append(f"missing {name}")
            continue
        got = _sha256_file(p)
        exp = meta.get("sha256")
        if exp and got != exp:
            errors.append(f"checksum mismatch {name}")

    db_file = dest / "agentbox.db"
    qc = {"ok": True}
    if db_file.is_file() and db_file.stat().st_size > 0:
        from ops.integrity import quick_check, integrity_check
        qc = quick_check(str(db_file))
        if not qc["ok"]:
            errors.append(f"quick_check failed: {qc.get('result')}")
        # restore-to-temp verification
        with tempfile.TemporaryDirectory(prefix="ab5-bkp-verify-") as td:
            tmpdb = Path(td) / "verify.db"
            shutil.copy2(db_file, tmpdb)
            ic = integrity_check(str(tmpdb), full=True)
            if not ic["ok"]:
                errors.append(f"temp integrity_check failed: {ic.get('result')}")

    ok = not errors
    result = {
        "ok": ok,
        "backup_id": backup_id,
        "verified": ok,
        "errors": errors,
        "quick_check": qc,
        "manifest_version": manifest.get("version"),
    }
    # update manifest verified flag
    if ok:
        manifest["verified"] = True
        manifest["verified_at"] = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        mf.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    return result


def prune() -> dict[str, Any]:
    """Prune by keep_daily/weekly/monthly from backup.ini (simple: keep newest N)."""
    cfg = load_ini("backup.ini")
    keep_daily = cfg.getint("backup", "keep_daily", fallback=7)
    keep = max(keep_daily, 3)
    items = [b for b in list_backups() if not b.get("legacy")]
    removed = []
    if len(items) > keep:
        for b in items[keep:]:
            bid = b["backup_id"]
            path = Path(b.get("path") or (backups_dir() / bid))
            if path.is_dir() and path.resolve().is_relative_to(backups_dir().resolve()):
                shutil.rmtree(path)
                removed.append(bid)
    return {"ok": True, "kept": keep, "removed": removed, "remaining": len(items) - len(removed)}


def export(backup_id: str, dest_path: str) -> dict[str, Any]:
    src = _resolve(backup_id)
    dest = Path(dest_path)
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.suffixes[-2:] == [".tar", ".gz"] or dest.suffix == ".tgz":
        with tarfile.open(dest, "w:gz") as tar:
            tar.add(str(src), arcname=src.name)
    else:
        if dest.exists():
            shutil.rmtree(dest) if dest.is_dir() else dest.unlink()
        shutil.copytree(src, dest)
    return {"ok": True, "backup_id": backup_id, "exported_to": str(dest)}


def _resolve(backup_id: str) -> Path:
    # accept id or path
    p = Path(backup_id)
    if p.is_dir():
        return p
    cand = backups_dir() / backup_id
    if cand.is_dir():
        return cand
    # prefix match
    matches = [d for d in backups_dir().iterdir() if d.is_dir() and d.name.startswith(backup_id)]
    if len(matches) == 1:
        return matches[0]
    if matches:
        raise FileNotFoundError(f"ambiguous backup id {backup_id}: {[m.name for m in matches]}")
    raise FileNotFoundError(f"backup not found: {backup_id}")


def main(argv: Optional[list[str]] = None) -> int:
    argv = list(argv or sys.argv[1:])
    if not argv:
        print("usage: backups.py create|list|inspect|verify|prune|export ...", file=sys.stderr)
        return 2
    cmd = argv[0]
    if cmd == "create":
        note = " ".join(argv[1:]) if len(argv) > 1 else ""
        print(json.dumps(create(note=note), indent=2))
    elif cmd == "list":
        print(json.dumps(list_backups(), indent=2))
    elif cmd == "inspect":
        print(json.dumps(inspect(argv[1]), indent=2))
    elif cmd == "verify":
        out = verify(argv[1])
        print(json.dumps(out, indent=2))
        return 0 if out.get("ok") else 1
    elif cmd == "prune":
        print(json.dumps(prune(), indent=2))
    elif cmd == "export":
        print(json.dumps(export(argv[1], argv[2]), indent=2))
    else:
        print(f"unknown: {cmd}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
