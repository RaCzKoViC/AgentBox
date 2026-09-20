#!/usr/bin/env python3
"""AgentBox v5 — Approval Queue (beta3, compatible with alpha3 schema)."""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any, Optional

_HERE = Path(__file__).resolve().parent
for _c in (_HERE.parent / "storage", _HERE.parent.parent / "lib" / "storage"):
    if (_c / "db.py").is_file():
        sys.path.insert(0, str(_c))
        break

import db  # noqa: E402

ALLOWED_APPROVAL_STATUSES = frozenset({"pending", "approved", "rejected"})


def _ensure_lib() -> None:
    lib = str(_HERE.parent)
    if lib not in sys.path:
        sys.path.insert(0, lib)


def auto_approve_enabled() -> bool:
    env = os.environ.get("AGENTBOX_AUTO_APPROVE", "1").strip().lower()
    if env in ("0", "false", "no", "off"):
        return False
    if env in ("1", "true", "yes", "on"):
        return True
    try:
        import tomllib
    except ImportError:
        try:
            import tomli as tomllib  # type: ignore
        except ImportError:
            return True
    home = Path(os.environ.get("AGENTBOX_V5_HOME", Path.home() / ".local/share/agentbox/v5"))
    cfg = home / "config" / "agentbox.toml"
    if not cfg.is_file():
        return True
    try:
        with open(cfg, "rb") as f:
            data = tomllib.load(f)
        if data.get("core", {}).get("auto_approve") is False:
            return False
        if data.get("daemon", {}).get("auto_approve") is False:
            return False
        return bool(data.get("core", {}).get("auto_approve", True))
    except Exception:
        return True


def _approval_cols(conn) -> set[str]:
    return {r[1] for r in conn.execute("PRAGMA table_info(approvals)").fetchall()}


def create_approval(
    task_id: Optional[str] = None,
    gate: str = "action",
    reason: str = "",
    approval_type: Optional[str] = None,
    run_id: Optional[str] = None,
    handoff_id: Optional[str] = None,
    requested_by: Optional[str] = None,
    risk_score: Optional[int] = None,
    payload: Optional[dict] = None,
    db_path: Optional[str] = None,
) -> dict:
    """Create pending approval. Supports alpha3 (gate) and beta3 columns."""
    approval_type = approval_type or gate or "action"
    gate = gate or approval_type
    if task_id:
        task = db.get_task(task_id, db_path)
        if not task:
            raise KeyError(f"task not found: {task_id}")
    else:
        task = None
    aid = db.new_id("a_")
    now = db.utc_now()
    with db.connect(db_path) as conn:
        cols = _approval_cols(conn)
        fields = ["id", "task_id", "status", "reason"]
        values: list[Any] = [aid, task_id, "pending", reason]
        if "gate" in cols:
            fields.append("gate")
            values.append(gate)
        if "approval_type" in cols:
            fields.append("approval_type")
            values.append(approval_type)
        if "run_id" in cols:
            fields.append("run_id")
            values.append(run_id)
        if "handoff_id" in cols:
            fields.append("handoff_id")
            values.append(handoff_id)
        if "requested_by" in cols:
            fields.append("requested_by")
            values.append(requested_by)
        if "risk_score" in cols:
            fields.append("risk_score")
            values.append(risk_score)
        if "payload_json" in cols:
            fields.append("payload_json")
            values.append(json.dumps(payload or {}))
        if "created_at" in cols:
            fields.append("created_at")
            values.append(now)
        if "requested_at" in cols:
            fields.append("requested_at")
            values.append(now)
        if "resolved_at" in cols:
            fields.append("resolved_at")
            values.append(None)
        placeholders = ", ".join("?" for _ in fields)
        conn.execute(
            f"INSERT INTO approvals ({', '.join(fields)}) VALUES ({placeholders})",
            values,
        )
        conn.execute(
            """
            INSERT INTO events (ts, task_id, run_id, kind, message, payload_json)
            VALUES (?, ?, ?, 'approval.requested', ?, ?)
            """,
            (
                now,
                task_id,
                run_id,
                f"Approval requested: type={approval_type}",
                json.dumps({
                    "approval_id": aid,
                    "gate": gate,
                    "approval_type": approval_type,
                    "reason": reason,
                    "risk_score": risk_score,
                    "handoff_id": handoff_id,
                }),
            ),
        )
        if task and task["status"] not in (
            "completed", "failed", "cancelled", "rejected", "merged",
        ):
            conn.execute(
                "UPDATE tasks SET status = 'awaiting_approval', updated_at = ? WHERE id = ?",
                (now, task_id),
            )
            conn.execute(
                """
                INSERT INTO events (ts, task_id, run_id, kind, message, payload_json)
                VALUES (?, ?, NULL, 'task.status', ?, ?)
                """,
                (
                    now,
                    task_id,
                    f"Status {task['status']} -> awaiting_approval",
                    json.dumps({"from": task["status"], "to": "awaiting_approval"}),
                ),
            )
        conn.commit()
    try:
        _ensure_lib()
        from observability.metrics import record_metric  # type: ignore
        record_metric("agentbox_approvals_total", 1.0, labels={"status": "pending"}, db_path=db_path)
        # gauge pending
        with db.connect(db_path) as conn:
            pending = conn.execute(
                "SELECT COUNT(*) c FROM approvals WHERE status='pending'"
            ).fetchone()["c"]
        record_metric("agentbox_approvals_pending", float(pending), db_path=db_path)
    except Exception:
        pass
    return get_approval(aid, db_path)


def get_approval(approval_id: str, db_path: Optional[str] = None) -> Optional[dict]:
    with db.connect(db_path) as conn:
        row = conn.execute("SELECT * FROM approvals WHERE id = ?", (approval_id,)).fetchone()
        if not row:
            return None
        d = dict(row)
        # Normalize aliases
        if "approval_type" not in d and "gate" in d:
            d["approval_type"] = d.get("gate")
        if "requested_at" not in d and "created_at" in d:
            d["requested_at"] = d.get("created_at")
        if "decided_at" not in d and "resolved_at" in d:
            d["decided_at"] = d.get("resolved_at")
        return d


def list_approvals(
    status: Optional[str] = None,
    task_id: Optional[str] = None,
    db_path: Optional[str] = None,
) -> list[dict]:
    with db.connect(db_path) as conn:
        q = "SELECT * FROM approvals WHERE 1=1"
        args: list[Any] = []
        if status:
            q += " AND status = ?"
            args.append(status)
        if task_id:
            q += " AND task_id = ?"
            args.append(task_id)
        cols = _approval_cols(conn)
        order = "requested_at" if "requested_at" in cols else "created_at"
        q += f" ORDER BY {order} DESC"
        rows = conn.execute(q, args).fetchall()
        out = []
        for r in rows:
            d = dict(r)
            if "approval_type" not in d and "gate" in d:
                d["approval_type"] = d.get("gate")
            out.append(d)
        return out


def resolve_approval(
    approval_id: str,
    status: str,
    reason: str = "",
    decided_by: str = "user",
    db_path: Optional[str] = None,
    queue_on_approve: bool = True,
) -> dict:
    if status not in ("approved", "rejected"):
        raise ValueError("status must be approved|rejected")
    appr = get_approval(approval_id, db_path)
    if not appr:
        raise KeyError(f"approval not found: {approval_id}")
    if appr["status"] != "pending":
        raise ValueError(f"approval already resolved: {appr['status']}")
    now = db.utc_now()
    final_reason = reason or appr.get("reason") or ""
    with db.connect(db_path) as conn:
        cols = _approval_cols(conn)
        sets = ["status = ?", "reason = ?"]
        params: list[Any] = [status, final_reason]
        if "resolved_at" in cols:
            sets.append("resolved_at = ?")
            params.append(now)
        if "decided_at" in cols:
            sets.append("decided_at = ?")
            params.append(now)
        if "decided_by" in cols:
            sets.append("decided_by = ?")
            params.append(decided_by)
        params.append(approval_id)
        conn.execute(
            f"UPDATE approvals SET {', '.join(sets)} WHERE id = ?",
            params,
        )
        ev_kind = "approval.approved" if status == "approved" else "approval.rejected"
        # Also emit legacy approval.resolved
        for kind in (ev_kind, "approval.resolved"):
            conn.execute(
                """
                INSERT INTO events (ts, task_id, run_id, kind, message, payload_json)
                VALUES (?, ?, NULL, ?, ?, ?)
                """,
                (
                    now,
                    appr.get("task_id"),
                    kind,
                    f"Approval {status}: type={appr.get('approval_type') or appr.get('gate')}",
                    json.dumps({
                        "approval_id": approval_id,
                        "gate": appr.get("gate"),
                        "approval_type": appr.get("approval_type"),
                        "status": status,
                        "reason": final_reason,
                        "decided_by": decided_by,
                    }),
                ),
            )
        task_id = appr.get("task_id")
        if task_id and status == "approved" and queue_on_approve:
            row = conn.execute("SELECT status FROM tasks WHERE id = ?", (task_id,)).fetchone()
            if row and row["status"] == "awaiting_approval":
                # beta3: approved status briefly, then queued
                conn.execute(
                    "UPDATE tasks SET status = 'queued', updated_at = ? WHERE id = ?",
                    (now, task_id),
                )
                conn.execute(
                    """
                    INSERT INTO events (ts, task_id, run_id, kind, message, payload_json)
                    VALUES (?, ?, NULL, 'task.status', ?, ?)
                    """,
                    (
                        now, task_id,
                        "Status awaiting_approval -> queued",
                        json.dumps({"from": "awaiting_approval", "to": "queued"}),
                    ),
                )
        elif task_id and status == "rejected":
            conn.execute(
                "UPDATE tasks SET status = 'rejected', updated_at = ? WHERE id = ?",
                (now, task_id),
            )
            conn.execute(
                """
                INSERT INTO events (ts, task_id, run_id, kind, message, payload_json)
                VALUES (?, ?, NULL, 'task.status', ?, ?)
                """,
                (
                    now, task_id,
                    "Status -> rejected (approval rejected)",
                    json.dumps({"to": "rejected"}),
                ),
            )
        conn.commit()
    try:
        _ensure_lib()
        from observability.metrics import record_metric  # type: ignore
        record_metric("agentbox_approvals_total", 1.0, labels={"status": status}, db_path=db_path)
        with db.connect(db_path) as conn:
            pending = conn.execute(
                "SELECT COUNT(*) c FROM approvals WHERE status='pending'"
            ).fetchone()["c"]
        record_metric("agentbox_approvals_pending", float(pending), db_path=db_path)
    except Exception:
        pass
    return get_approval(approval_id, db_path)


def has_approved(task_id: str, gate: str, db_path: Optional[str] = None) -> bool:
    with db.connect(db_path) as conn:
        cols = _approval_cols(conn)
        if "gate" in cols:
            row = conn.execute(
                """
                SELECT id FROM approvals
                WHERE task_id = ? AND gate = ? AND status = 'approved'
                ORDER BY COALESCE(resolved_at, decided_at, created_at) DESC LIMIT 1
                """,
                (task_id, gate),
            ).fetchone()
        else:
            row = conn.execute(
                """
                SELECT id FROM approvals
                WHERE task_id = ? AND approval_type = ? AND status = 'approved'
                LIMIT 1
                """,
                (task_id, gate),
            ).fetchone()
        return row is not None


def ensure_before_run_gate(task: dict, db_path: Optional[str] = None) -> Optional[dict]:
    pol_dir = str(_HERE)
    if pol_dir not in sys.path:
        sys.path.insert(0, pol_dir)
    import policies as pol  # noqa: E402

    decision = pol.check_task_run(task)
    if decision["decision"] == "deny":
        db.set_task_status(task["id"], "rejected", db_path=db_path)
        db.emit_event(
            kind="policy.denied",
            message=decision.get("reason", "before_run denied"),
            task_id=task["id"],
            payload=decision,
            db_path=db_path,
        )
        return {"denied": True, "decision": decision}
    if decision["decision"] != "approval":
        return None
    if auto_approve_enabled():
        if has_approved(task["id"], "before_run", db_path=db_path):
            return None
        appr = create_approval(
            task["id"],
            gate="before_run",
            reason=f"auto-approved: {decision.get('reason', '')}",
            db_path=db_path,
        )
        resolve_approval(
            appr["id"],
            "approved",
            reason="AGENTBOX_AUTO_APPROVE / autonomous default",
            decided_by="auto",
            db_path=db_path,
            queue_on_approve=True,
        )
        return None
    if has_approved(task["id"], "before_run", db_path=db_path):
        return None
    pending = list_approvals(status="pending", task_id=task["id"], db_path=db_path)
    for p in pending:
        if p.get("gate") == "before_run" or p.get("approval_type") == "before_run":
            return p
    return create_approval(
        task["id"],
        gate="before_run",
        reason=decision.get("reason", "before_run requires approval"),
        db_path=db_path,
    )


def _print(obj: Any) -> None:
    print(json.dumps(obj, indent=2, ensure_ascii=False, default=str))


def main(argv: Optional[list[str]] = None) -> int:
    argv = list(argv if argv is not None else sys.argv[1:])
    db_path = os.environ.get("AGENTBOX_V5_DB")
    if not argv:
        print("usage: approvals.py list|show ID|create|approve|reject|get", file=sys.stderr)
        return 2
    cmd = argv[0]
    try:
        if cmd == "list":
            status = None
            task = None
            i = 1
            while i < len(argv):
                if argv[i] == "--status" and i + 1 < len(argv):
                    status = argv[i + 1]
                    i += 2
                elif argv[i] == "--task" and i + 1 < len(argv):
                    task = argv[i + 1]
                    i += 2
                else:
                    i += 1
            _print(list_approvals(status=status, task_id=task, db_path=db_path))
            return 0
        if cmd in ("get", "show"):
            if len(argv) < 2:
                print(f"{cmd} ID", file=sys.stderr)
                return 2
            a = get_approval(argv[1], db_path)
            if not a:
                print(f"not found: {argv[1]}", file=sys.stderr)
                return 1
            _print(a)
            return 0
        if cmd == "create":
            if len(argv) < 3:
                print("create TASK_ID GATE [--reason R]", file=sys.stderr)
                return 2
            reason = ""
            if "--reason" in argv:
                i = argv.index("--reason")
                reason = argv[i + 1] if i + 1 < len(argv) else ""
            _print(create_approval(argv[1], argv[2], reason=reason, db_path=db_path))
            return 0
        if cmd in ("approve", "reject"):
            if len(argv) < 2:
                print(f"{cmd} ID [--reason R]", file=sys.stderr)
                return 2
            reason = ""
            if "--reason" in argv:
                i = argv.index("--reason")
                reason = argv[i + 1] if i + 1 < len(argv) else ""
            status = "approved" if cmd == "approve" else "rejected"
            _print(resolve_approval(argv[1], status, reason=reason, db_path=db_path))
            return 0
        if cmd == "ensure-gate":
            if len(argv) < 2:
                print("ensure-gate TASK_ID", file=sys.stderr)
                return 2
            task = db.get_task(argv[1], db_path)
            if not task:
                print(f"not found: {argv[1]}", file=sys.stderr)
                return 1
            result = ensure_before_run_gate(task, db_path=db_path)
            _print(result if result is not None else {"gated": False})
            return 0
        print(f"unknown: {cmd}", file=sys.stderr)
        return 2
    except Exception as e:
        print(f"error: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
