"""Improvement proposals — measure + propose; NEVER auto-mutate core without approval."""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any, Optional

_HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(_HERE.parent))

from storage import db as dbmod  # noqa: E402
from evaluation import store  # noqa: E402

VALID_STATUSES = frozenset({
    "draft", "evaluating", "awaiting_approval", "approved",
    "canary", "promoted", "rejected", "rolled_back",
})


def create_proposal(
    target_type: str,
    target_id: str,
    proposal: dict[str, Any],
    *,
    evidence: Optional[dict[str, Any]] = None,
    risk_level: str = "LOW",
    current_version: str = "",
    proposed_version: str = "",
    status: str = "awaiting_approval",
) -> dict[str, Any]:
    pid = dbmod.new_id("prop_")
    now = dbmod.utc_now()
    with dbmod.connect() as conn:
        store.ensure_schema(conn)
        conn.execute(
            """INSERT INTO improvement_proposals
               (id, target_type, target_id, current_version, proposed_version,
                proposal_json, evidence_json, risk_level, status, created_at, updated_at)
               VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
            (pid, target_type, target_id, current_version, proposed_version,
             json.dumps(proposal, default=str), json.dumps(evidence or {}, default=str),
             risk_level, status, now, now),
        )
        conn.commit()
    return get_proposal(pid)  # type: ignore


def get_proposal(proposal_id: str) -> Optional[dict[str, Any]]:
    with dbmod.connect() as conn:
        store.ensure_schema(conn)
        r = conn.execute(
            "SELECT * FROM improvement_proposals WHERE id=?", (proposal_id,)
        ).fetchone()
        if not r:
            return None
        return _row(r)


def list_proposals(status: Optional[str] = None, limit: int = 50) -> list[dict[str, Any]]:
    with dbmod.connect() as conn:
        store.ensure_schema(conn)
        if status:
            rows = conn.execute(
                "SELECT * FROM improvement_proposals WHERE status=? ORDER BY created_at DESC LIMIT ?",
                (status, limit),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM improvement_proposals ORDER BY created_at DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [_row(r) for r in rows]


def _row(r) -> dict[str, Any]:
    d = dict(r)
    d["proposal"] = json.loads(d.pop("proposal_json") or "{}")
    d["evidence"] = json.loads(d.pop("evidence_json") or "{}")
    return d


def _set_status(proposal_id: str, status: str, extra: Optional[dict] = None) -> dict[str, Any]:
    if status not in VALID_STATUSES:
        raise ValueError(f"invalid status {status}")
    with dbmod.connect() as conn:
        store.ensure_schema(conn)
        conn.execute(
            "UPDATE improvement_proposals SET status=?, updated_at=? WHERE id=?",
            (status, dbmod.utc_now(), proposal_id),
        )
        conn.commit()
    p = get_proposal(proposal_id)
    if not p:
        raise ValueError(f"proposal not found: {proposal_id}")
    if extra:
        p.update(extra)
    return p


def approve(proposal_id: str, *, apply: bool = False) -> dict[str, Any]:
    """Approve proposal. Apply only if low-risk AND (apply flag or AGENTBOX_AUTO_APPROVE gated)."""
    p = get_proposal(proposal_id)
    if not p:
        raise ValueError(f"proposal not found: {proposal_id}")
    if p["status"] in ("rejected", "promoted", "rolled_back"):
        raise ValueError(f"cannot approve from status {p['status']}")
    p = _set_status(proposal_id, "approved")

    auto = os.environ.get("AGENTBOX_AUTO_APPROVE", "1") == "1"
    risk = (p.get("risk_level") or "LOW").upper()
    # NEVER auto-mutate core; only low-risk proposal apply when explicitly gated
    applied = False
    if apply and risk == "LOW" and auto:
        applied = _apply_low_risk(p)
        if applied:
            p = _set_status(proposal_id, "promoted", {"applied": True})
    p["applied"] = applied
    p["note"] = (
        "approved; apply requires explicit apply=True + LOW risk + AGENTBOX_AUTO_APPROVE"
        if not applied else "approved and applied (low-risk)"
    )
    return p


def reject(proposal_id: str, reason: str = "") -> dict[str, Any]:
    p = _set_status(proposal_id, "rejected")
    p["reject_reason"] = reason
    return p


def _apply_low_risk(proposal: dict[str, Any]) -> bool:
    """Apply only safe, non-core mutations (e.g. record prompt draft). Never touch security/policy."""
    target_type = proposal.get("target_type")
    body = proposal.get("proposal") or {}
    if target_type == "prompt" and body.get("content"):
        from evaluation.prompt_versioning import create_version
        create_version(
            proposal["target_id"],
            body["content"],
            status="candidate",
            parent_id=None,
        )
        return True
    if target_type == "workflow" and body.get("definition"):
        from evaluation.workflow_versioning import create_version
        create_version(
            proposal["target_id"],
            body["definition"],
            status="candidate",
        )
        return True
    # case/hardening proposals: mark promoted as acknowledged only (no core mutation)
    if target_type in ("case", "platform", "tool"):
        return True  # acknowledgment only — no file/core mutation
    return False
