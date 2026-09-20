#!/usr/bin/env python3
"""AgentBox v5 handoff engine — create/accept/start/complete/fail/reject (beta3 policy gate)."""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any, Optional

HANDOFF_STATUSES = frozenset({
    "pending", "accepted", "running", "completed", "failed", "rejected",
    # beta3
    "policy_check", "approved", "denied", "blocked",
})


def _ensure_path() -> None:
    lib = str(Path(__file__).resolve().parent.parent)
    if lib not in sys.path:
        sys.path.insert(0, lib)


def _db():
    _ensure_path()
    from storage import db as dbmod  # type: ignore

    return dbmod


def _emit(kind: str, message: str, task_id: Optional[str] = None,
          run_id: Optional[str] = None, payload: Optional[dict] = None,
          db_path: Optional[str] = None) -> None:
    db = _db()
    db.emit_event(kind=kind, message=message, task_id=task_id, run_id=run_id,
                  payload=payload or {}, db_path=db_path)


def _metric(name: str, value: float = 1.0, labels: Optional[dict] = None,
            db_path: Optional[str] = None) -> None:
    try:
        _ensure_path()
        from observability.metrics import record_metric  # type: ignore

        record_metric(name, value, labels=labels, db_path=db_path)
    except Exception:
        pass


def can_delegate(source: str, target: str, db_path: Optional[str] = None) -> dict[str, Any]:
    """Check agent registry can_delegate policy. Random delegation DENIED."""
    _ensure_path()
    from agents.registry import can_delegate as reg_can_delegate  # type: ignore

    return reg_can_delegate(source, target, db_path=db_path)


def get_handoff(handoff_id: str, db_path: Optional[str] = None) -> Optional[dict]:
    db = _db()
    with db.connect(db_path) as conn:
        row = conn.execute("SELECT * FROM agent_handoffs WHERE id = ?", (handoff_id,)).fetchone()
        return dict(row) if row else None


def list_handoffs(
    task_id: Optional[str] = None,
    status: Optional[str] = None,
    limit: int = 100,
    db_path: Optional[str] = None,
) -> list[dict]:
    db = _db()
    clauses = []
    params: list[Any] = []
    if task_id:
        clauses.append("task_id = ?")
        params.append(task_id)
    if status:
        clauses.append("status = ?")
        params.append(status)
    where = ("WHERE " + " AND ".join(clauses)) if clauses else ""
    params.append(limit)
    with db.connect(db_path) as conn:
        rows = conn.execute(
            f"SELECT * FROM agent_handoffs {where} ORDER BY created_at DESC LIMIT ?",
            params,
        ).fetchall()
        return [dict(r) for r in rows]


def create_handoff(
    task_id: str,
    source_agent: str,
    target_agent: str,
    reason: str,
    context: Optional[dict] = None,
    required: bool = True,
    run_id: Optional[str] = None,
    max_retries: int = 2,
    db_path: Optional[str] = None,
) -> dict:
    """Create a handoff after risk → policy → budget → can_delegate (beta3)."""
    source_agent = (source_agent or "").strip()
    target_agent = (target_agent or "").strip()
    if not source_agent or not target_agent:
        raise ValueError("source_agent and target_agent required")
    if source_agent == target_agent:
        raise ValueError("source and target must differ")

    db = _db()
    task = db.get_task(task_id, db_path=db_path)
    if not task:
        raise KeyError(f"task not found: {task_id}")

    # beta3 pipeline: Risk → Policy → Budget → can_delegate
    _ensure_path()
    try:
        from policy.enforcement import enforce_action  # type: ignore

        enf = enforce_action(
            "handoff.create",
            resource=f"{source_agent}->{target_agent}",
            task_id=task_id,
            run_id=run_id,
            agent_name=source_agent,
            context={
                "target_agent": target_agent,
                "reason": reason,
            },
            budget_metric="max_handoffs",
            budget_value=1.0,
            db_path=db_path,
        )
        if enf["decision"] == "deny":
            _emit(
                "policy.denied",
                f"handoff denied: {enf.get('reason')}",
                task_id=task_id,
                run_id=run_id,
                payload={"enforcement": {k: enf[k] for k in ("decision", "reason", "action")}},
                db_path=db_path,
            )
            raise PermissionError(
                f"handoff DENIED by enforcement: {enf.get('reason')}"
            )
        if enf["decision"] == "approval":
            # Create handoff in policy_check / awaiting — but still require approval
            # For handoffs, we raise so caller can wait; store pending approval id
            raise PermissionError(
                f"handoff REQUIRES APPROVAL: {enf.get('approval_id')} — {enf.get('reason')}"
            )
    except PermissionError:
        raise
    except Exception as e:
        # If enforcement modules fail unexpectedly, fall back to can_delegate only
        _emit(
            "policy.evaluated",
            f"enforcement fallback: {e}",
            task_id=task_id,
            payload={"error": str(e)},
            db_path=db_path,
        )

    policy = can_delegate(source_agent, target_agent, db_path=db_path)
    if not policy.get("allowed"):
        raise PermissionError(
            f"delegation DENIED: {source_agent} → {target_agent}: {policy.get('reason', 'policy')}"
        )

    # Build compact handoff context if not provided
    ctx = context
    if ctx is None:
        try:
            from memory.context import build_handoff_context  # type: ignore

            ctx = build_handoff_context(
                task_id=task_id,
                source_agent=source_agent,
                target_agent=target_agent,
                reason=reason,
                db_path=db_path,
            )
        except Exception as e:
            ctx = {
                "task_goal": task.get("title") or "",
                "source_summary": f"handoff from {source_agent}",
                "reason": reason,
                "error_building_context": str(e),
                "memories": [],
                "files": [],
                "artifacts": [],
                "findings": [],
                "constraints": [],
            }

    hid = db.new_id("h_")
    now = db.utc_now()
    with db.connect(db_path) as conn:
        conn.execute(
            """
            INSERT INTO agent_handoffs (
                id, task_id, run_id, source_agent, target_agent, status, reason,
                context_json, required, retries, max_retries, error, result_json,
                created_at, accepted_at, completed_at
            ) VALUES (?, ?, ?, ?, ?, 'pending', ?, ?, ?, 0, ?, '', '{}', ?, NULL, NULL)
            """,
            (
                hid, task_id, run_id, source_agent, target_agent, reason or "",
                json.dumps(ctx), 1 if required else 0, int(max_retries), now,
            ),
        )
        conn.commit()

    _emit(
        "handoff.created",
        f"{source_agent} → {target_agent}: {reason}",
        task_id=task_id,
        run_id=run_id,
        payload={"handoff_id": hid, "source": source_agent, "target": target_agent, "required": required},
        db_path=db_path,
    )
    _metric("handoffs.created", 1.0, labels={"source": source_agent, "target": target_agent}, db_path=db_path)
    try:
        from policy.budgets import record_usage  # type: ignore
        record_usage("task", task_id, "max_handoffs", 1.0, task_id=task_id, run_id=run_id, db_path=db_path)
    except Exception:
        pass
    return get_handoff(hid, db_path=db_path)  # type: ignore[return-value]


def accept_handoff(handoff_id: str, db_path: Optional[str] = None) -> dict:
    row = get_handoff(handoff_id, db_path=db_path)
    if not row:
        raise KeyError(f"handoff not found: {handoff_id}")
    if row["status"] not in ("pending",):
        raise ValueError(f"cannot accept handoff in status={row['status']}")
    db = _db()
    now = db.utc_now()
    with db.connect(db_path) as conn:
        conn.execute(
            "UPDATE agent_handoffs SET status='accepted', accepted_at=? WHERE id=?",
            (now, handoff_id),
        )
        conn.commit()
    _emit(
        "handoff.accepted",
        f"accepted by {row['target_agent']}",
        task_id=row["task_id"],
        run_id=row.get("run_id"),
        payload={"handoff_id": handoff_id},
        db_path=db_path,
    )
    return get_handoff(handoff_id, db_path=db_path)  # type: ignore[return-value]


def start_handoff(handoff_id: str, db_path: Optional[str] = None) -> dict:
    row = get_handoff(handoff_id, db_path=db_path)
    if not row:
        raise KeyError(f"handoff not found: {handoff_id}")
    if row["status"] not in ("pending", "accepted"):
        raise ValueError(f"cannot start handoff in status={row['status']}")
    db = _db()
    now = db.utc_now()
    with db.connect(db_path) as conn:
        if row["status"] == "pending":
            conn.execute(
                "UPDATE agent_handoffs SET status='running', accepted_at=COALESCE(accepted_at, ?) WHERE id=?",
                (now, handoff_id),
            )
        else:
            conn.execute(
                "UPDATE agent_handoffs SET status='running' WHERE id=?",
                (handoff_id,),
            )
        conn.commit()
    _emit(
        "handoff.started",
        f"started {row['source_agent']} → {row['target_agent']}",
        task_id=row["task_id"],
        run_id=row.get("run_id"),
        payload={"handoff_id": handoff_id},
        db_path=db_path,
    )
    return get_handoff(handoff_id, db_path=db_path)  # type: ignore[return-value]


def complete_handoff(
    handoff_id: str,
    result: Optional[dict] = None,
    db_path: Optional[str] = None,
) -> dict:
    row = get_handoff(handoff_id, db_path=db_path)
    if not row:
        raise KeyError(f"handoff not found: {handoff_id}")
    if row["status"] in ("completed", "rejected"):
        raise ValueError(f"cannot complete handoff in status={row['status']}")
    db = _db()
    now = db.utc_now()
    with db.connect(db_path) as conn:
        conn.execute(
            """
            UPDATE agent_handoffs
            SET status='completed', completed_at=?, result_json=?, error=''
            WHERE id=?
            """,
            (now, json.dumps(result or {}), handoff_id),
        )
        conn.commit()
    _emit(
        "handoff.completed",
        f"completed {row['source_agent']} → {row['target_agent']}",
        task_id=row["task_id"],
        run_id=row.get("run_id"),
        payload={"handoff_id": handoff_id, "result": result or {}},
        db_path=db_path,
    )
    _metric(
        "handoffs.completed", 1.0,
        labels={"source": row["source_agent"], "target": row["target_agent"]},
        db_path=db_path,
    )
    return get_handoff(handoff_id, db_path=db_path)  # type: ignore[return-value]


def fail_handoff(handoff_id: str, error: str, db_path: Optional[str] = None) -> dict:
    """Fail handoff; retry if retries < max_retries else mark failed; block parent if required."""
    row = get_handoff(handoff_id, db_path=db_path)
    if not row:
        raise KeyError(f"handoff not found: {handoff_id}")
    db = _db()
    now = db.utc_now()
    retries = int(row.get("retries") or 0)
    max_retries = int(row.get("max_retries") or 2)
    required = bool(int(row.get("required") or 0))

    if retries < max_retries:
        new_retries = retries + 1
        with db.connect(db_path) as conn:
            conn.execute(
                """
                UPDATE agent_handoffs
                SET status='pending', retries=?, error=?, accepted_at=NULL
                WHERE id=?
                """,
                (new_retries, error or "", handoff_id),
            )
            conn.commit()
        _emit(
            "handoff.retried",
            f"retry {new_retries}/{max_retries}: {error}",
            task_id=row["task_id"],
            run_id=row.get("run_id"),
            payload={"handoff_id": handoff_id, "retries": new_retries, "error": error},
            db_path=db_path,
        )
        _emit(
            "handoff.failed",
            f"transient fail (will retry): {error}",
            task_id=row["task_id"],
            run_id=row.get("run_id"),
            payload={"handoff_id": handoff_id, "retries": new_retries, "will_retry": True},
            db_path=db_path,
        )
        return get_handoff(handoff_id, db_path=db_path)  # type: ignore[return-value]

    # Exhausted retries → permanent fail
    with db.connect(db_path) as conn:
        conn.execute(
            """
            UPDATE agent_handoffs
            SET status='failed', completed_at=?, error=?
            WHERE id=?
            """,
            (now, error or "", handoff_id),
        )
        conn.commit()
    _emit(
        "handoff.failed",
        f"failed permanently: {error}",
        task_id=row["task_id"],
        run_id=row.get("run_id"),
        payload={"handoff_id": handoff_id, "retries": retries, "will_retry": False},
        db_path=db_path,
    )
    _metric(
        "handoffs.failed", 1.0,
        labels={"source": row["source_agent"], "target": row["target_agent"]},
        db_path=db_path,
    )
    if required:
        try:
            db.set_task_status(row["task_id"], "blocked", db_path=db_path)
            _emit(
                "task.blocked",
                f"blocked by required handoff {handoff_id}: {error}",
                task_id=row["task_id"],
                payload={"handoff_id": handoff_id},
                db_path=db_path,
            )
            _metric("tasks.blocked", 1.0, labels={"reason": "handoff_failed"}, db_path=db_path)
        except Exception:
            pass
    return get_handoff(handoff_id, db_path=db_path)  # type: ignore[return-value]


def reject_handoff(handoff_id: str, reason: str, db_path: Optional[str] = None) -> dict:
    row = get_handoff(handoff_id, db_path=db_path)
    if not row:
        raise KeyError(f"handoff not found: {handoff_id}")
    if row["status"] in ("completed", "rejected"):
        raise ValueError(f"cannot reject handoff in status={row['status']}")
    db = _db()
    now = db.utc_now()
    with db.connect(db_path) as conn:
        conn.execute(
            """
            UPDATE agent_handoffs
            SET status='rejected', completed_at=?, error=?
            WHERE id=?
            """,
            (now, reason or "rejected", handoff_id),
        )
        conn.commit()
    _emit(
        "handoff.rejected",
        reason or "rejected",
        task_id=row["task_id"],
        run_id=row.get("run_id"),
        payload={"handoff_id": handoff_id, "reason": reason},
        db_path=db_path,
    )
    _metric(
        "handoffs.rejected", 1.0,
        labels={"source": row["source_agent"], "target": row["target_agent"]},
        db_path=db_path,
    )
    if bool(int(row.get("required") or 0)):
        try:
            db.set_task_status(row["task_id"], "blocked", db_path=db_path)
            _emit(
                "task.blocked",
                f"blocked by rejected required handoff {handoff_id}",
                task_id=row["task_id"],
                payload={"handoff_id": handoff_id},
                db_path=db_path,
            )
        except Exception:
            pass
    return get_handoff(handoff_id, db_path=db_path)  # type: ignore[return-value]


def _print(obj: Any) -> None:
    print(json.dumps(obj, indent=2, ensure_ascii=False, default=str))


def main(argv: Optional[list[str]] = None) -> int:
    argv = list(argv if argv is not None else sys.argv[1:])
    db_path = os.environ.get("AGENTBOX_V5_DB")
    if not argv:
        print(
            "usage: engine.py create|accept|start|complete|fail|reject|list|show ...",
            file=sys.stderr,
        )
        return 2
    cmd = argv[0]
    try:
        if cmd == "create":
            import argparse

            p = argparse.ArgumentParser()
            p.add_argument("task_id")
            p.add_argument("source")
            p.add_argument("target")
            p.add_argument("--reason", default="")
            p.add_argument("--optional", action="store_true")
            p.add_argument("--run-id", default=None)
            args = p.parse_args(argv[1:])
            row = create_handoff(
                task_id=args.task_id,
                source_agent=args.source,
                target_agent=args.target,
                reason=args.reason,
                required=not args.optional,
                run_id=args.run_id,
                db_path=db_path,
            )
            _print(row)
            return 0
        if cmd == "accept":
            _print(accept_handoff(argv[1], db_path=db_path))
            return 0
        if cmd == "start":
            _print(start_handoff(argv[1], db_path=db_path))
            return 0
        if cmd == "complete":
            result = {}
            if "--result" in argv:
                i = argv.index("--result")
                result = json.loads(argv[i + 1]) if i + 1 < len(argv) else {}
            _print(complete_handoff(argv[1], result=result, db_path=db_path))
            return 0
        if cmd == "fail":
            err = argv[2] if len(argv) > 2 else "failed"
            _print(fail_handoff(argv[1], err, db_path=db_path))
            return 0
        if cmd == "reject":
            reason = argv[2] if len(argv) > 2 else "rejected"
            _print(reject_handoff(argv[1], reason, db_path=db_path))
            return 0
        if cmd == "list":
            import argparse

            p = argparse.ArgumentParser()
            p.add_argument("--task", default=None)
            p.add_argument("--status", default=None)
            args = p.parse_args(argv[1:])
            _print(list_handoffs(task_id=args.task, status=args.status, db_path=db_path))
            return 0
        if cmd == "show":
            row = get_handoff(argv[1], db_path=db_path)
            if not row:
                print(f"not found: {argv[1]}", file=sys.stderr)
                return 1
            _print(row)
            return 0
        print(f"unknown: {cmd}", file=sys.stderr)
        return 2
    except Exception as e:
        print(f"error: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
