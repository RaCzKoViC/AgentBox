"""Secure one-time enrollment tokens + worker session issuance."""
from __future__ import annotations

import hashlib
import hmac
import json
import secrets
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Optional

_HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(_HERE.parent))

from storage import db as dbmod  # noqa: E402
from distributed import PROTOCOL_VERSION  # noqa: E402
from distributed import registry  # noqa: E402

DEFAULT_TTL_MINUTES = 60
SESSION_TTL_DAYS = 30


def _hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def _now() -> datetime:
    return datetime.now(timezone.utc)


def create_enrollment_token(ttl_minutes: int = DEFAULT_TTL_MINUTES) -> dict[str, Any]:
    tid = "etok_" + secrets.token_hex(8)
    raw = secrets.token_urlsafe(32)
    exp = _now() + timedelta(minutes=ttl_minutes)
    with dbmod.connect() as conn:
        conn.execute(
            """INSERT INTO enrollment_tokens (id, token_hash, created_at, expires_at)
               VALUES (?,?,?,?)""",
            (tid, _hash(raw), dbmod.utc_now(), exp.strftime("%Y-%m-%dT%H:%M:%SZ")),
        )
        conn.commit()
    return {
        "id": tid,
        "token": raw,
        "expires_at": exp.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "ttl_minutes": ttl_minutes,
        "one_time": True,
    }


def _parse_exp(s: str) -> datetime:
    s = (s or "").rstrip("Z")
    for fmt in ("%Y-%m-%dT%H:%M:%S.%f", "%Y-%m-%dT%H:%M:%S"):
        try:
            return datetime.strptime(s[:26] if "." in s else s[:19], fmt).replace(tzinfo=timezone.utc)
        except Exception:
            continue
    raise ValueError(f"bad expiry: {s}")


def enroll(
    token: str,
    *,
    name: str,
    hostname: str = "",
    tailscale_ip: str = "",
    platform: str = "",
    architecture: str = "",
    version: str = "5.1.0",
    capabilities: Optional[dict] = None,
    labels: Optional[list] = None,
    max_parallel_tasks: int = 1,
    protocol_version: int = 1,
    auto_approve: bool = True,
) -> dict[str, Any]:
    if protocol_version != PROTOCOL_VERSION:
        raise ValueError(f"upgrade_required: protocol {protocol_version} != {PROTOCOL_VERSION}")
    if not token:
        raise ValueError("enrollment token required")

    with dbmod.connect() as conn:
        row = conn.execute(
            "SELECT * FROM enrollment_tokens WHERE token_hash=? AND used_at IS NULL",
            (_hash(token),),
        ).fetchone()
        if not row:
            raise PermissionError("invalid or already-used enrollment token")
        exp = _parse_exp(row["expires_at"])
        if exp < _now():
            raise PermissionError("enrollment token expired")

        worker_id = "wrk_" + secrets.token_hex(6)
        status = "online" if auto_approve else "new"
        caps = capabilities or {}
        labs = labels or ["linux", "local"]
        conn.execute(
            """INSERT INTO workers
               (id, name, hostname, tailscale_ip, platform, architecture, version,
                status, capabilities_json, labels_json, max_parallel_tasks,
                current_load, last_heartbeat, enrolled_at, quarantined)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,0,?,?,0)""",
            (
                worker_id, name or hostname or worker_id, hostname, tailscale_ip,
                platform, architecture, version, status,
                json.dumps(caps), json.dumps(labs), max_parallel_tasks,
                dbmod.utc_now(), dbmod.utc_now(),
            ),
        )
        # issue session
        sid = "wses_" + secrets.token_hex(8)
        session_raw = secrets.token_urlsafe(40)
        sexp = _now() + timedelta(days=SESSION_TTL_DAYS)
        conn.execute(
            """INSERT INTO worker_sessions (id, worker_id, token_hash, created_at, expires_at)
               VALUES (?,?,?,?,?)""",
            (sid, worker_id, _hash(session_raw), dbmod.utc_now(), sexp.strftime("%Y-%m-%dT%H:%M:%SZ")),
        )
        conn.execute(
            "UPDATE enrollment_tokens SET used_at=?, used_by_worker_id=? WHERE id=?",
            (dbmod.utc_now(), worker_id, row["id"]),
        )
        conn.execute(
            "INSERT INTO worker_events (worker_id, event_type, payload_json) VALUES (?,?,?)",
            (worker_id, "worker.enrolled", json.dumps({"name": name, "status": status})),
        )
        try:
            conn.execute(
                "INSERT INTO events (ts, kind, message, payload_json) VALUES (?,?,?,?)",
                (dbmod.utc_now(), "worker.enrolled", f"enrolled {worker_id}",
                 json.dumps({"worker_id": worker_id, "name": name})),
            )
        except Exception:
            pass
        conn.commit()

    return {
        "worker_id": worker_id,
        "session_id": sid,
        "session_token": session_raw,
        "status": status,
        "protocol_version": PROTOCOL_VERSION,
        "expires_at": sexp.strftime("%Y-%m-%dT%H:%M:%SZ"),
    }


def verify_worker_session(token: str) -> Optional[dict[str, Any]]:
    if not token:
        return None
    with dbmod.connect() as conn:
        row = conn.execute(
            """SELECT s.*, w.status AS worker_status, w.name AS worker_name, w.quarantined
               FROM worker_sessions s JOIN workers w ON w.id = s.worker_id
               WHERE s.token_hash=? AND s.revoked_at IS NULL""",
            (_hash(token),),
        ).fetchone()
        if not row:
            return None
        try:
            exp = _parse_exp(row["expires_at"])
            if exp < _now():
                return None
        except Exception:
            return None
        return dict(row)


def revoke_sessions(worker_id: str) -> int:
    with dbmod.connect() as conn:
        cur = conn.execute(
            "UPDATE worker_sessions SET revoked_at=? WHERE worker_id=? AND revoked_at IS NULL",
            (dbmod.utc_now(), worker_id),
        )
        conn.commit()
        return cur.rowcount
