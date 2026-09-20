from __future__ import annotations
import json
from fastapi import APIRouter, Depends
from ..deps import Actor, get_actor, require_role, audit
from ..errors import APIError
from ..schemas import PolicyCreate, PolicyPatch

router = APIRouter(tags=["policies"])

@router.get("/api/v1/policies")
def list_policies(_actor: Actor = Depends(get_actor)):
    from policy import policies as pol
    items = []
    try:
        items = pol.list_policies_db()
    except Exception:
        pass
    if not items:
        try:
            items = pol.list_policies_config()
        except Exception:
            items = []
    return {"items": items}

@router.get("/api/v1/policies/{policy_id}")
def get_policy(policy_id: str, _actor: Actor = Depends(get_actor)):
    from policy import policies as pol
    p = pol.get_policy(policy_id)
    if not p:
        raise APIError("POLICY_NOT_FOUND", "Policy not found", status_code=404)
    return p

@router.post("/api/v1/policies")
def create_policy(body: PolicyCreate, actor: Actor = Depends(require_role("admin"))):
    from storage import db as dbmod
    pid = dbmod.new_id("pol_")
    conn = dbmod.connect()
    try:
        conn.execute(
            """INSERT INTO policies (id, scope_type, scope_id, category, action, effect, config_json, enabled)
               VALUES (?,?,?,?,?,?,?,?)""",
            (pid, body.scope_type, body.scope_id, body.category, body.action, body.effect,
             json.dumps(body.config_json or {}), 1 if body.enabled else 0),
        )
        conn.commit()
        audit("POST", "/api/v1/policies", actor, 201)
        return {"id": pid, "ok": True}
    finally:
        conn.close()

@router.patch("/api/v1/policies/{policy_id}")
def patch_policy(policy_id: str, body: PolicyPatch, actor: Actor = Depends(require_role("admin"))):
    from storage import db as dbmod
    conn = dbmod.connect()
    try:
        row = conn.execute("SELECT * FROM policies WHERE id=?", (policy_id,)).fetchone()
        if not row:
            raise APIError("POLICY_NOT_FOUND", "Policy not found", status_code=404)
        effect = body.effect if body.effect is not None else row["effect"]
        enabled = int(body.enabled) if body.enabled is not None else row["enabled"]
        cfg = json.dumps(body.config_json) if body.config_json is not None else row["config_json"]
        conn.execute(
            "UPDATE policies SET effect=?, enabled=?, config_json=?, updated_at=CURRENT_TIMESTAMP WHERE id=?",
            (effect, enabled, cfg, policy_id),
        )
        conn.commit()
        audit("PATCH", f"/api/v1/policies/{policy_id}", actor, 200)
        return {"id": policy_id, "ok": True}
    finally:
        conn.close()

@router.post("/api/v1/policies/{policy_id}/enable")
def enable_policy(policy_id: str, actor: Actor = Depends(require_role("admin"))):
    return patch_policy(policy_id, PolicyPatch(enabled=True), actor)

@router.post("/api/v1/policies/{policy_id}/disable")
def disable_policy(policy_id: str, actor: Actor = Depends(require_role("admin"))):
    return patch_policy(policy_id, PolicyPatch(enabled=False), actor)
