#!/usr/bin/env python3
"""Doctor / diagnostics for AgentBox v5 Stable."""
from __future__ import annotations

import json
import os
import shutil
import socket
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

_HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(_HERE.parent))

from ops.integrity import integrity_check, quick_check, schema_tables  # noqa: E402
from ops.lifecycle import status as life_status  # noqa: E402
from ops.maintenance import status as maint_status  # noqa: E402
from ops.migrations import status as mig_status  # noqa: E402
from ops.paths import (  # noqa: E402
    backups_dir,
    config_dir,
    data_home,
    db_path,
    read_version,
    share_config_dir,
)
from ops.recovery import status as recovery_status  # noqa: E402
from ops.security_hardening import check_security  # noqa: E402


_LEGACY_EXPECTED_HOSTNAMES = ["cursor"]
_SOFT_CHECKS = ("lifecycle", "recovery_scan", "maintenance")


def expected_hostnames() -> tuple[list[str], str]:
    """Allowed hostnames from <data_home>/config/agentbox.toml.

    [doctor]
    expected_hostname  = "host"            # single value, or
    expected_hostnames = ["host1", "host2"] # list of allowed hostnames
    Falls back to the legacy default ("cursor") when not configured.
    """
    cfg = share_config_dir() / "agentbox.toml"
    try:
        import tomllib

        data = tomllib.loads(cfg.read_text(encoding="utf-8")) if cfg.is_file() else {}
    except Exception:
        data = {}
    sec = data.get("doctor") or {}
    names: list[str] = []
    raw_list = sec.get("expected_hostnames")
    if isinstance(raw_list, str):
        raw_list = [raw_list]
    if isinstance(raw_list, list):
        names.extend(str(x).strip() for x in raw_list if str(x).strip())
    single = sec.get("expected_hostname")
    if isinstance(single, str) and single.strip():
        names.append(single.strip())
    if names:
        return names, str(cfg)
    return list(_LEGACY_EXPECTED_HOSTNAMES), "built-in default"


def hostname_check() -> dict[str, Any]:
    actual_full = socket.gethostname()
    actual = actual_full.split(".")[0]
    allowed, source = expected_hostnames()
    allowed_short = {a.split(".")[0] for a in allowed}
    if actual in allowed_short or actual_full in allowed:
        return {"name": "hostname", "ok": True, "level": "PASS",
                "detail": {"actual": actual_full, "expected": allowed, "source": source}}
    cfg = share_config_dir() / "agentbox.toml"
    msg = (
        f"hostname mismatch: expected one of {allowed} (from {source}), actual '{actual_full}'. "
        f"If this box was recreated, update [doctor] expected_hostnames in {cfg} "
        f"(e.g. expected_hostnames = [\"{actual}\"])."
    )
    return {"name": "hostname", "ok": True, "level": "WARN",
            "detail": {"actual": actual_full, "expected": allowed, "source": source, "message": msg}}


def doctor() -> dict[str, Any]:
    checks = []

    def add(name: str, ok: bool, detail: Any = None):
        level = "PASS" if ok else ("WARN" if name in _SOFT_CHECKS else "FAIL")
        checks.append({"name": name, "ok": ok, "level": level, "detail": detail})

    ver = read_version()
    # v5.6+: any semver 5.x.y (and current VERSION file) is healthy
    import re
    ver_ok = bool(re.match(r"^5\.\d+\.\d+", ver or ""))
    add("version", ver_ok, ver)

    qc = quick_check()
    add("db_quick_check", qc["ok"], qc.get("result"))

    sch = schema_tables()
    add("schema_tables", sch["ok"], {"missing": sch.get("missing")})

    mig = mig_status()
    add("migrations", len(mig.get("pending", [])) == 0, mig)

    life = life_status()
    add("lifecycle", True, {
        "daemon": life["daemon"].get("running"),
        "web": life["web"].get("running"),
    })

    maint = maint_status()
    add("maintenance", not maint.get("active"), maint.get("mode"))

    rec = recovery_status()
    add("recovery_scan", True, rec.get("by_type"))

    sec = check_security()
    add("security", sec.get("ok", False), sec.get("issues"))

    # disk
    usage = shutil.disk_usage(str(data_home()))
    free_gb = usage.free / (1024 ** 3)
    add("disk_free", free_gb >= 1.0, f"{free_gb:.2f}G")

    # backups dir writable
    try:
        backups_dir().mkdir(parents=True, exist_ok=True)
        test = backups_dir() / ".write_test"
        test.write_text("ok", encoding="utf-8")
        test.unlink()
        add("backups_writable", True, str(backups_dir()))
    except Exception as e:
        add("backups_writable", False, str(e))

    # hostname: mismatch is a WARN (box may be recreated with a new hostname)
    hn = hostname_check()
    checks.append(hn)

    overall = all(c["ok"] for c in checks if c["name"] not in ("lifecycle",))  # web/daemon optional
    # soft: lifecycle informational
    hard_fail = [c for c in checks if not c["ok"] and c["name"] not in ("lifecycle", "recovery_scan", "maintenance")]
    health = "HEALTHY" if not hard_fail else ("DEGRADED" if qc["ok"] else "UNHEALTHY")
    if maint.get("active"):
        health = "MAINTENANCE"

    return {
        "ok": len(hard_fail) == 0,
        "health": health,
        "version": ver,
        "db": str(db_path()),
        "checks": checks,
        "failed": [c["name"] for c in hard_fail],
        "warnings": [
            {"name": c["name"], "message": (c.get("detail") or {}).get("message") if isinstance(c.get("detail"), dict) else c.get("detail")}
            for c in checks if c.get("level") == "WARN"
        ],
        "ts": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }


def create_bundle() -> dict[str, Any]:
    """Write a diagnostics JSON under logs/diagnostics/."""
    report = doctor()
    report["integrity_full"] = integrity_check(full=True)
    report["lifecycle"] = life_status()
    report["migrations"] = mig_status()
    report["recovery"] = recovery_status()
    report["security"] = check_security()
    out_dir = data_home() / "logs" / "diagnostics"
    out_dir.mkdir(parents=True, exist_ok=True)
    name = f"diag_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}.json"
    path = out_dir / name
    path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    return {"ok": True, "path": str(path), "health": report["health"]}


def main(argv: Optional[list[str]] = None) -> int:
    argv = list(argv or sys.argv[1:])
    cmd = argv[0] if argv else "doctor"
    if cmd in ("doctor", "check"):
        out = doctor()
        print(json.dumps(out, indent=2))
        for w in out.get("warnings") or []:
            print(f"WARN: {w.get('name')}: {w.get('message')}", file=sys.stderr)
        return 0 if out.get("ok") else 1
    if cmd == "create":
        print(json.dumps(create_bundle(), indent=2))
        return 0
    print("usage: diagnostics.py doctor|create", file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
