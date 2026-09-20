#!/usr/bin/env python3
"""Persistence for goals, plans, plan_nodes, plan_revisions, reflections, workflow_runs."""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any, Optional

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from storage import db as dbmod  # noqa: E402


def _j(obj: Any) -> str:
    return json.dumps(obj if obj is not None else {}, default=str)


def _loads(raw: Any, default: Any = None):
    if raw is None:
        return [] if default == [] else ({} if default is None else default)
    if isinstance(raw, (dict, list)):
        return raw
    try:
        return json.loads(raw)
    except (TypeError, json.JSONDecodeError):
        return [] if default == [] else ({} if default is None else default)


def _evt(conn, kind: str, message: str, payload: dict, task_id: str | None = None):
    conn.execute(
        "INSERT INTO events (ts, task_id, run_id, kind, message, payload_json) VALUES (?,?,?,?,?,?)",
        (dbmod.utc_now(), task_id, None, kind, message, _j(payload)),
    )


def create_goal(
    title: str,
    description: str = "",
    project_id: str = "",
    priority: int = 100,
    success_criteria: Optional[list] = None,
    constraints: Optional[dict] = None,
    risk_profile: str = "MEDIUM",
    approval_policy: str = "plan",
    budget_id: str = "",
    db_path: Optional[str] = None,
) -> dict:
    gid = dbmod.new_id("g_")
    now = dbmod.utc_now()
    criteria = success_criteria or [
        "build passes", "tests pass", "no policy violations", "acceptance criteria satisfied"
    ]
    conn = dbmod.connect(db_path)
    try:
        conn.execute(
            """INSERT INTO goals (
                id, project_id, title, description, status, priority,
                success_criteria_json, constraints_json, budget_id,
                risk_profile, approval_policy, created_at, updated_at
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                gid, project_id or "", title, description or "", "created", int(priority),
                _j(criteria), _j(constraints or {}), budget_id or "",
                risk_profile or "MEDIUM", approval_policy or "plan", now, now,
            ),
        )
        _evt(conn, "goal.created", f"Goal created: {title}", {"goal_id": gid, "title": title})
        conn.commit()
    finally:
        conn.close()
    return get_goal(gid, db_path)  # type: ignore


def get_goal(goal_id: str, db_path: Optional[str] = None) -> Optional[dict]:
    conn = dbmod.connect(db_path)
    try:
        row = conn.execute("SELECT * FROM goals WHERE id=?", (goal_id,)).fetchone()
        if not row:
            return None
        d = dict(row)
        d["success_criteria"] = _loads(d.pop("success_criteria_json", None), [])
        d["constraints"] = _loads(d.pop("constraints_json", None), {})
        return d
    finally:
        conn.close()


def list_goals(status: Optional[str] = None, db_path: Optional[str] = None) -> list[dict]:
    conn = dbmod.connect(db_path)
    try:
        if status:
            rows = conn.execute(
                "SELECT * FROM goals WHERE status=? ORDER BY created_at DESC", (status,)
            ).fetchall()
        else:
            rows = conn.execute("SELECT * FROM goals ORDER BY created_at DESC").fetchall()
        out = []
        for r in rows:
            d = dict(r)
            d["success_criteria"] = _loads(d.pop("success_criteria_json", None), [])
            d["constraints"] = _loads(d.pop("constraints_json", None), {})
            out.append(d)
        return out
    finally:
        conn.close()


def set_goal_status(goal_id: str, status: str, db_path: Optional[str] = None) -> dict:
    now = dbmod.utc_now()
    completed = now if status == "completed" else None
    conn = dbmod.connect(db_path)
    try:
        conn.execute(
            "UPDATE goals SET status=?, updated_at=?, completed_at=COALESCE(?, completed_at) WHERE id=?",
            (status, now, completed, goal_id),
        )
        _evt(conn, "goal.status", f"Goal {goal_id} -> {status}", {"goal_id": goal_id, "status": status})
        conn.commit()
    finally:
        conn.close()
    g = get_goal(goal_id, db_path)
    if not g:
        raise KeyError(goal_id)
    return g


def save_plan(
    goal_id: str,
    graph: dict,
    summary: str = "",
    version: int = 1,
    status: str = "draft",
    estimated_cost: float = 0.0,
    estimated_runtime_seconds: float = 0.0,
    risk_summary: Optional[dict] = None,
    approval_points: Optional[list] = None,
    quality_score: float = 0.0,
    supersedes_plan_id: str = "",
    workflow_template: str = "",
    intelligence_notes: Optional[dict] = None,
    db_path: Optional[str] = None,
) -> dict:
    pid = dbmod.new_id("p_")
    now = dbmod.utc_now()
    nodes = list(graph.get("nodes") or [])
    # Always mint unique node IDs (template stage_* ids would collide across plans)
    id_map: dict[str, str] = {}
    for i, node in enumerate(nodes):
        old_id = str(node.get("id") or f"tmp_{i}")
        new_id = dbmod.new_id("n_")
        id_map[old_id] = new_id
        node["id"] = new_id
        node.setdefault("order_index", i)
    for node in nodes:
        node["dependencies"] = [id_map.get(d, d) for d in (node.get("dependencies") or [])]
    edges = []
    for e in (graph.get("edges") or []):
        ee = dict(e)
        ee["from"] = id_map.get(ee.get("from"), ee.get("from"))
        ee["to"] = id_map.get(ee.get("to"), ee.get("to"))
        edges.append(ee)
    graph = dict(graph)
    graph["nodes"] = nodes
    graph["edges"] = edges
    if graph.get("critical_path") and isinstance(graph["critical_path"], dict):
        cp = dict(graph["critical_path"])
        cp["path"] = [id_map.get(x, x) for x in (cp.get("path") or [])]
        graph["critical_path"] = cp

    conn = dbmod.connect(db_path)
    try:
        conn.execute(
            """INSERT INTO plans (
                id, goal_id, version, status, summary, graph_json,
                estimated_cost, estimated_runtime_seconds, risk_summary_json,
                approval_points_json, quality_score, supersedes_plan_id,
                workflow_template, intelligence_notes_json, created_at
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                pid, goal_id, int(version), status, summary, _j(graph),
                float(estimated_cost), float(estimated_runtime_seconds),
                _j(risk_summary or {}), _j(approval_points or []),
                float(quality_score), supersedes_plan_id or None,
                workflow_template or "", _j(intelligence_notes or {}), now,
            ),
        )
        for node in nodes:
            conn.execute(
                """INSERT INTO plan_nodes (
                    id, plan_id, goal_id, title, description, node_type, status,
                    assigned_agent, dependencies_json, required_capabilities_json,
                    estimated_runtime, estimated_cost, risk, parallel_safe,
                    critical, order_index, meta_json, created_at, updated_at
                ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    node["id"], pid, goal_id,
                    node.get("title") or node.get("agent") or node["id"],
                    node.get("description") or "",
                    node.get("type") or node.get("node_type") or "stage",
                    node.get("status") or "pending",
                    node.get("agent") or node.get("assigned_agent") or "",
                    _j(node.get("dependencies") or []),
                    _j(node.get("required_capabilities") or []),
                    float(node.get("estimated_runtime") or node.get("estimated_runtime_seconds") or 60),
                    float(node.get("estimated_cost") or 0.05),
                    node.get("risk") or "MEDIUM",
                    1 if node.get("parallel_safe") else 0,
                    1 if node.get("critical", True) else 0,
                    int(node.get("order_index") or 0),
                    _j(node.get("meta") or {}),
                    now, now,
                ),
            )
        _evt(conn, "plan.created", f"Plan v{version} for {goal_id}",
             {"plan_id": pid, "goal_id": goal_id, "version": version})
        conn.commit()
    finally:
        conn.close()
    return get_plan(pid, db_path)  # type: ignore


def get_plan(plan_id: str, db_path: Optional[str] = None) -> Optional[dict]:
    conn = dbmod.connect(db_path)
    try:
        row = conn.execute("SELECT * FROM plans WHERE id=?", (plan_id,)).fetchone()
        if not row:
            return None
        d = dict(row)
        d["graph"] = _loads(d.pop("graph_json", None), {"nodes": [], "edges": []})
        d["risk_summary"] = _loads(d.pop("risk_summary_json", None), {})
        d["approval_points"] = _loads(d.pop("approval_points_json", None), [])
        d["intelligence_notes"] = _loads(d.pop("intelligence_notes_json", None), {})
        nodes = conn.execute(
            "SELECT * FROM plan_nodes WHERE plan_id=? ORDER BY order_index ASC", (plan_id,)
        ).fetchall()
        d["nodes"] = []
        for n in nodes:
            nd = dict(n)
            nd["dependencies"] = _loads(nd.pop("dependencies_json", None), [])
            nd["required_capabilities"] = _loads(nd.pop("required_capabilities_json", None), [])
            nd["meta"] = _loads(nd.pop("meta_json", None), {})
            nd["agent"] = nd.get("assigned_agent") or ""
            nd["parallel_safe"] = bool(nd.get("parallel_safe"))
            nd["critical"] = bool(nd.get("critical"))
            d["nodes"].append(nd)
        return d
    finally:
        conn.close()


def list_plans(goal_id: Optional[str] = None, db_path: Optional[str] = None) -> list[dict]:
    conn = dbmod.connect(db_path)
    try:
        if goal_id:
            rows = conn.execute(
                "SELECT * FROM plans WHERE goal_id=? ORDER BY version DESC", (goal_id,)
            ).fetchall()
        else:
            rows = conn.execute("SELECT * FROM plans ORDER BY created_at DESC LIMIT 100").fetchall()
        out = []
        for r in rows:
            d = dict(r)
            d["graph"] = _loads(d.pop("graph_json", None), {})
            d["risk_summary"] = _loads(d.pop("risk_summary_json", None), {})
            d["approval_points"] = _loads(d.pop("approval_points_json", None), [])
            d["intelligence_notes"] = _loads(d.pop("intelligence_notes_json", None), {})
            out.append(d)
        return out
    finally:
        conn.close()


def set_plan_status(plan_id: str, status: str, db_path: Optional[str] = None) -> dict:
    conn = dbmod.connect(db_path)
    try:
        conn.execute("UPDATE plans SET status=? WHERE id=?", (status, plan_id))
        _evt(conn, "plan.status", f"Plan {plan_id} -> {status}", {"plan_id": plan_id, "status": status})
        conn.commit()
    finally:
        conn.close()
    p = get_plan(plan_id, db_path)
    if not p:
        raise KeyError(plan_id)
    return p


def record_revision(
    plan_id: str,
    goal_id: str,
    reason: str,
    changes: dict,
    new_plan_id: str = "",
    db_path: Optional[str] = None,
) -> dict:
    rid = dbmod.new_id("rev_")
    now = dbmod.utc_now()
    conn = dbmod.connect(db_path)
    try:
        conn.execute(
            """INSERT INTO plan_revisions (
                id, plan_id, goal_id, new_plan_id, reason, changes_json, created_at
            ) VALUES (?,?,?,?,?,?,?)""",
            (rid, plan_id, goal_id, new_plan_id or None, reason, _j(changes), now),
        )
        _evt(conn, "plan.revised", reason, {"revision_id": rid, "plan_id": plan_id, "new_plan_id": new_plan_id})
        conn.commit()
    finally:
        conn.close()
    return {
        "id": rid, "plan_id": plan_id, "goal_id": goal_id, "reason": reason,
        "changes": changes, "new_plan_id": new_plan_id, "created_at": now,
    }


def save_reflection(
    goal_id: str,
    decision: str,
    reason: str = "",
    confidence: float = 0.7,
    proposed_actions: Optional[list] = None,
    task_id: str = "",
    run_id: str = "",
    plan_id: str = "",
    db_path: Optional[str] = None,
) -> dict:
    rid = dbmod.new_id("ref_")
    now = dbmod.utc_now()
    conn = dbmod.connect(db_path)
    try:
        conn.execute(
            """INSERT INTO reflections (
                id, goal_id, task_id, run_id, plan_id, decision, confidence,
                reason, proposed_actions_json, created_at
            ) VALUES (?,?,?,?,?,?,?,?,?,?)""",
            (
                rid, goal_id, task_id or None, run_id or None, plan_id or None,
                decision, float(confidence), reason, _j(proposed_actions or []), now,
            ),
        )
        kind = f"reflection.{decision.lower()}" if decision else "reflection.created"
        conn.execute(
            "INSERT INTO events (ts, task_id, run_id, kind, message, payload_json) VALUES (?,?,?,?,?,?)",
            (now, task_id or None, run_id or None, kind, reason or decision,
             _j({"reflection_id": rid, "goal_id": goal_id, "decision": decision})),
        )
        conn.commit()
    finally:
        conn.close()
    return {
        "id": rid, "goal_id": goal_id, "decision": decision, "confidence": confidence,
        "reason": reason, "proposed_actions": proposed_actions or [], "created_at": now,
        "plan_id": plan_id, "task_id": task_id,
    }


def list_reflections(goal_id: Optional[str] = None, db_path: Optional[str] = None) -> list[dict]:
    conn = dbmod.connect(db_path)
    try:
        if goal_id:
            rows = conn.execute(
                "SELECT * FROM reflections WHERE goal_id=? ORDER BY created_at DESC", (goal_id,)
            ).fetchall()
        else:
            rows = conn.execute("SELECT * FROM reflections ORDER BY created_at DESC LIMIT 100").fetchall()
        out = []
        for r in rows:
            d = dict(r)
            d["proposed_actions"] = _loads(d.pop("proposed_actions_json", None), [])
            out.append(d)
        return out
    finally:
        conn.close()


def create_workflow_run(
    template_name: str,
    goal_id: str = "",
    plan_id: str = "",
    status: str = "running",
    meta: Optional[dict] = None,
    db_path: Optional[str] = None,
) -> dict:
    wid = dbmod.new_id("wr_")
    now = dbmod.utc_now()
    conn = dbmod.connect(db_path)
    try:
        conn.execute(
            """INSERT INTO workflow_runs (
                id, template_name, goal_id, plan_id, status, meta_json, created_at, updated_at
            ) VALUES (?,?,?,?,?,?,?,?)""",
            (wid, template_name, goal_id or None, plan_id or None, status, _j(meta or {}), now, now),
        )
        _evt(conn, "workflow.compiled", f"Workflow {template_name}",
             {"workflow_run_id": wid, "goal_id": goal_id, "plan_id": plan_id})
        conn.commit()
    finally:
        conn.close()
    return {"id": wid, "template_name": template_name, "goal_id": goal_id, "plan_id": plan_id, "status": status, "created_at": now}


def insert_plan_node(
    plan_id: str,
    goal_id: str,
    title: str,
    agent: str = "coder",
    dependencies: Optional[list] = None,
    order_index: int = 999,
    node_type: str = "retry",
    description: str = "",
    meta: Optional[dict] = None,
    db_path: Optional[str] = None,
) -> dict:
    nid = dbmod.new_id("n_")
    now = dbmod.utc_now()
    deps = dependencies or []
    conn = dbmod.connect(db_path)
    try:
        conn.execute(
            """INSERT INTO plan_nodes (
                id, plan_id, goal_id, title, description, node_type, status,
                assigned_agent, dependencies_json, required_capabilities_json,
                estimated_runtime, estimated_cost, risk, parallel_safe,
                critical, order_index, meta_json, created_at, updated_at
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                nid, plan_id, goal_id, title, description, node_type, "pending",
                agent, _j(deps), _j([]), 60.0, 0.01, "MEDIUM",
                0, 1, int(order_index), _j(meta or {}), now, now,
            ),
        )
        row = conn.execute("SELECT graph_json FROM plans WHERE id=?", (plan_id,)).fetchone()
        if row:
            graph = _loads(row[0], {"nodes": [], "edges": []})
            graph.setdefault("nodes", []).append({
                "id": nid, "title": title, "agent": agent,
                "dependencies": deps, "order_index": order_index, "type": node_type,
            })
            for dep in deps:
                graph.setdefault("edges", []).append({"from": dep, "to": nid, "type": "hard"})
            conn.execute("UPDATE plans SET graph_json=? WHERE id=?", (_j(graph), plan_id))
        conn.commit()
    finally:
        conn.close()
    return {"id": nid, "plan_id": plan_id, "title": title, "agent": agent}
