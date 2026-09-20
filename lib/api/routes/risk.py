from __future__ import annotations
from fastapi import APIRouter, Depends
from ..deps import Actor, get_actor, require_role
from ..schemas import RiskCheckIn

router = APIRouter(tags=["risk"])

@router.get("/api/v1/risk")
def risk_overview(_actor: Actor = Depends(get_actor)):
    from policy import risk as riskmod
    hist = riskmod.list_history(limit=50)
    high = [h for h in hist if str(h.get("risk_level") or h.get("level") or "").upper() in ("HIGH", "CRITICAL")]
    return {"recent_high": high[:10], "history_count": len(hist)}

@router.get("/api/v1/risk/history")
def risk_history(limit: int = 50, _actor: Actor = Depends(get_actor)):
    from policy import risk as riskmod
    return {"items": riskmod.list_history(limit=limit)}

@router.get("/api/v1/risk/task/{task_id}")
def risk_task(task_id: str, _actor: Actor = Depends(get_actor)):
    from storage import db as dbmod
    conn = dbmod.connect()
    try:
        rows = conn.execute(
            "SELECT * FROM risk_assessments WHERE task_id=? ORDER BY created_at DESC LIMIT 50",
            (task_id,),
        ).fetchall()
        return {"items": [dict(r) for r in rows]}
    finally:
        conn.close()

@router.post("/api/v1/risk/check")
def risk_check(body: RiskCheckIn, _actor: Actor = Depends(require_role("operator"))):
    from policy import risk as riskmod
    result = riskmod.assess_risk(action=body.action, resource=body.resource, task_id=body.task_id or None)
    try:
        if isinstance(result, dict):
            riskmod.persist_assessment(result)
    except Exception:
        pass
    return result if isinstance(result, dict) else {"result": result}
