from __future__ import annotations
import json
from fastapi import APIRouter, Depends
from ..deps import Actor, get_actor, require_role, audit, load_web_config, db_connect
from ..schemas import SettingsPatch

router = APIRouter(tags=["settings"])

@router.get("/api/v1/settings")
def get_settings(_actor: Actor = Depends(get_actor)):
    cfg = load_web_config()
    out = {sec: dict(cfg.items(sec)) for sec in cfg.sections()}
    return {"web": out}

@router.patch("/api/v1/settings")
def patch_settings(body: SettingsPatch, actor: Actor = Depends(require_role("admin"))):
    conn = db_connect()
    try:
        for k, v in body.values.items():
            if any(s in k.lower() for s in ("token", "password", "secret")):
                continue
            conn.execute(
                """INSERT INTO web_preferences (key, value_json, updated_at) VALUES (?,?,CURRENT_TIMESTAMP)
                   ON CONFLICT(key) DO UPDATE SET value_json=excluded.value_json, updated_at=CURRENT_TIMESTAMP""",
                (k, json.dumps(v)),
            )
        conn.commit()
        audit("PATCH", "/api/v1/settings", actor, 200)
        return {"ok": True}
    finally:
        conn.close()
