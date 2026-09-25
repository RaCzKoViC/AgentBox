"""Incident engine — open/list/show/close + timeline (v5.6.2)."""
from __future__ import annotations

import hashlib
import sys
from pathlib import Path
from typing import Any, Optional

_HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(_HERE.parent))

from storage import db as dbmod  # noqa: E402
from ops_autopilot import store  # noqa: E402

_SEV_RANK = {"SEV1": 1, "SEV2": 2, "SEV3": 3, "SEV4": 4}


def fingerprint(component: str, kind: str, title: str) -> str:
    raw = f"{component}|{kind}|{title}".encode()
    return hashlib.sha256(raw).hexdigest()[:16]


def open_incident(
    *,
    title: str,
    severity: str = "SEV3",
    component: str = "",
    source: str = "anomaly",
    symptoms: Optional[list] = None,
    evidence: Optional[dict] = None,
    suspected_causes: Optional[list] = None,
    runbook_id: Optional[str] = None,
    kind: str = "",
    dedupe: bool = True,
) -> dict[str, Any]:
    severity = (severity or "SEV3").upper()
    if severity not in _SEV_RANK:
        severity = "SEV3"
    fp = fingerprint(component, kind or source, title)
    if dedupe:
        existing = store.find_open_incident_by_fingerprint(fp)
        if existing:
            if _SEV_RANK.get(severity, 9) < _SEV_RANK.get(existing.get("severity"), 9):
                with dbmod.connect() as conn:
                    store.ensure_schema(conn)
                    store.update_incident(
                        conn, existing["id"], severity=severity, updated_at=dbmod.utc_now()
                    )
                    store.insert_incident_event(
                        conn,
                        {
                            "id": dbmod.new_id("iev_"),
                            "incident_id": existing["id"],
                            "event_type": "severity_escalated",
                            "message": f"Escalated to {severity}",
                            "detail": {"from": existing.get("severity"), "to": severity},
                        },
                    )
                    conn.commit()
            else:
                with dbmod.connect() as conn:
                    store.ensure_schema(conn)
                    store.insert_incident_event(
                        conn,
                        {
                            "id": dbmod.new_id("iev_"),
                            "incident_id": existing["id"],
                            "event_type": "symptom_observed",
                            "message": title,
                            "detail": {"symptoms": symptoms or [], "evidence": evidence or {}},
                        },
                    )
                    store.update_incident(conn, existing["id"], updated_at=dbmod.utc_now())
                    conn.commit()
            out = store.get_incident(existing["id"]) or existing
            out["deduped"] = True
            out["timeline"] = store.list_incident_events(existing["id"])
            return out

    iid = dbmod.new_id("inc_")
    now = dbmod.utc_now()
    row = {
        "id": iid,
        "fingerprint": fp,
        "title": title,
        "severity": severity,
        "status": "open",
        "component": component,
        "source": source,
        "symptoms": symptoms or [],
        "evidence": evidence or {},
        "suspected_causes": suspected_causes or [],
        "runbook_id": runbook_id,
        "detected_at": now,
        "updated_at": now,
        "created_at": now,
    }
    with dbmod.connect() as conn:
        store.ensure_schema(conn)
        store.insert_incident(conn, row)
        store.insert_incident_event(
            conn,
            {
                "id": dbmod.new_id("iev_"),
                "incident_id": iid,
                "event_type": "opened",
                "message": f"Incident opened: {title}",
                "detail": {"severity": severity, "source": source},
            },
        )
        conn.commit()
    out = store.get_incident(iid) or row
    out["deduped"] = False
    out["timeline"] = store.list_incident_events(iid)
    return out


def list_incidents(status: Optional[str] = None, limit: int = 50) -> list[dict[str, Any]]:
    return store.list_incidents(status=status, limit=limit)


def get_incident(incident_id: str) -> Optional[dict[str, Any]]:
    inc = store.get_incident(incident_id)
    if not inc:
        return None
    inc["timeline"] = store.list_incident_events(incident_id)
    return inc


def close_incident(
    incident_id: str,
    *,
    resolution: Optional[dict] = None,
    status: str = "resolved",
    message: str = "Incident closed",
) -> dict[str, Any]:
    inc = store.get_incident(incident_id)
    if not inc:
        raise ValueError(f"incident not found: {incident_id}")
    if inc.get("status") in ("resolved", "closed"):
        inc["timeline"] = store.list_incident_events(incident_id)
        return {**inc, "already_closed": True}
    if inc.get("severity") == "SEV1" and not (resolution or {}).get("confirmed"):
        raise ValueError("SEV1 requires resolution.confirmed=true to close")
    now = dbmod.utc_now()
    with dbmod.connect() as conn:
        store.ensure_schema(conn)
        store.update_incident(
            conn,
            incident_id,
            status=status,
            resolution=resolution or {"message": message},
            resolved_at=now,
            updated_at=now,
        )
        store.insert_incident_event(
            conn,
            {
                "id": dbmod.new_id("iev_"),
                "incident_id": incident_id,
                "event_type": "closed",
                "message": message,
                "detail": resolution or {},
            },
        )
        conn.commit()
    out = store.get_incident(incident_id) or inc
    out["timeline"] = store.list_incident_events(incident_id)
    return out
