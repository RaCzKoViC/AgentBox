from __future__ import annotations
from fastapi import APIRouter, Depends
from ..deps import Actor, get_actor, require_role, audit
from ..schemas import BudgetCreate
from storage import db as dbmod

router = APIRouter(tags=["budgets"])

@router.get("/api/v1/budgets")
def list_budgets(_actor: Actor = Depends(get_actor)):
    from policy import budgets as bud
    summary = {}
    try:
        summary = bud.budget_summary()
    except Exception:
        try:
            summary = bud.show_global()
        except Exception:
            summary = {}
    conn = dbmod.connect()
    try:
        rows = conn.execute("SELECT * FROM budgets ORDER BY created_at DESC LIMIT 100").fetchall()
        items = [dict(r) for r in rows]
    except Exception:
        items = []
    finally:
        conn.close()
    return {"items": items, "summary": summary}

@router.get("/api/v1/budgets/usage")
def budgets_usage(_actor: Actor = Depends(get_actor)):
    from policy import budgets as bud
    try:
        return {"items": bud.list_usage(limit=100)}
    except Exception:
        return {"items": []}

@router.get("/api/v1/budgets/task/{task_id}")
def budget_task(task_id: str, _actor: Actor = Depends(get_actor)):
    from policy import budgets as bud
    try:
        return bud.show_task(task_id)
    except Exception as e:
        return {"task_id": task_id, "error": str(e)}

@router.post("/api/v1/budgets")
def create_budget(body: BudgetCreate, actor: Actor = Depends(require_role("admin"))):
    pid = dbmod.new_id("bud_")
    conn = dbmod.connect()
    try:
        conn.execute(
            """INSERT INTO budgets (id, scope_type, scope_id, metric, limit_value, period, enabled)
               VALUES (?,?,?,?,?,?,?)""",
            (pid, body.scope_type, body.scope_id, body.metric, body.limit_value, body.period, 1 if body.enabled else 0),
        )
        conn.commit()
        audit("POST", "/api/v1/budgets", actor, 201)
        return {"id": pid, "ok": True}
    finally:
        conn.close()
