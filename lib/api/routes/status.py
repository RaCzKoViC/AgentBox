from __future__ import annotations
from fastapi import APIRouter, Depends
from ..deps import Actor, get_actor, system_stats

router = APIRouter(tags=["status"])

@router.get("/api/v1/status")
def status(_actor: Actor = Depends(get_actor)):
    from storage import db as dbmod
    counts = dbmod.count_by_status()
    running = counts.get("running", 0)
    queued = counts.get("queued", 0) + counts.get("scheduled", 0)
    blocked = sum(counts.get(s, 0) for s in ("blocked", "paused_budget", "awaiting_approval", "awaiting_policy"))
    conn = dbmod.connect()
    try:
        agents_active = conn.execute(
            "SELECT COUNT(*) FROM agents WHERE status IN ('active','busy','idle')"
        ).fetchone()[0]
        try:
            handoffs_pending = conn.execute(
                "SELECT COUNT(*) FROM agent_handoffs WHERE status IN ('pending','policy_check','approved','created')"
            ).fetchone()[0]
        except Exception:
            handoffs_pending = 0
        approvals_pending = conn.execute(
            "SELECT COUNT(*) FROM approvals WHERE status='pending'"
        ).fetchone()[0]
    finally:
        conn.close()
    return {
        "tasks": {"running": running, "queued": queued, "blocked": blocked, "by_status": counts},
        "agents": {"active": agents_active},
        "handoffs": {"pending": handoffs_pending},
        "approvals": {"pending": approvals_pending},
        "system": system_stats(),
    }
