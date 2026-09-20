#!/usr/bin/env python3
"""Central tool executor — EVERY call goes through Policy/Risk/Budget/Approval."""
from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Optional

_HERE = Path(__file__).resolve().parent


def _ensure_path() -> None:
    lib = str(_HERE.parent)
    if lib not in sys.path:
        sys.path.insert(0, lib)


def _hash_payload(obj: Any) -> str:
    raw = json.dumps(obj, sort_keys=True, default=str).encode()
    return hashlib.sha256(raw).hexdigest()[:16]


def _validate_input(schema: dict, payload: dict) -> Optional[str]:
    if not schema:
        return None
    required = schema.get("required") or []
    for r in required:
        if r not in payload or payload[r] is None:
            return f"missing required field: {r}"
    props = schema.get("properties") or {}
    for k, v in payload.items():
        if k not in props:
            continue
        t = props[k].get("type")
        if t == "string" and not isinstance(v, str):
            return f"{k} must be string"
        if t == "integer" and not isinstance(v, int):
            return f"{k} must be integer"
        if t == "boolean" and not isinstance(v, bool):
            return f"{k} must be boolean"
        if t == "object" and not isinstance(v, dict):
            return f"{k} must be object"
    return None


def _action_for_tool(tool_id: str, payload: dict, shell_info: Optional[dict] = None) -> tuple[str, Optional[str], dict]:
    """Map tool to enforcement action + resource + context."""
    ctx: dict[str, Any] = {"tool_id": tool_id, "payload_keys": list(payload.keys())}
    if tool_id == "file.read":
        return "filesystem.read", payload.get("path"), ctx
    if tool_id == "file.write":
        return "filesystem.write", payload.get("path"), ctx
    if tool_id == "git.status":
        return "filesystem.read", payload.get("cwd") or "/workspace", ctx
    if tool_id == "git.diff":
        return "filesystem.read", payload.get("cwd") or payload.get("path") or "/workspace", ctx
    if tool_id == "http.get":
        return "network.outbound", payload.get("url"), ctx
    if tool_id == "docker.ps":
        return "docker.run", None, {**ctx, "read_only": True}
    if tool_id == "shell.run":
        info = shell_info or {}
        cmd = payload.get("command") or ""
        ctx["command"] = cmd
        ctx["shell_risk"] = info
        if info.get("denied"):
            ctx["destructive"] = True
            if any(x in cmd.lower() for x in ("--force", "rm -rf", "privileged", "mkfs")):
                ctx["force"] = True
            return "shell.dangerous", payload.get("cwd"), ctx
        if info.get("allowlisted"):
            return "before_run", payload.get("cwd"), ctx
        # non-allowlisted → treat as elevated shell
        return "shell.run", payload.get("cwd"), ctx
    return tool_id.replace("/", "."), None, ctx


def _run_file_read(payload: dict) -> dict:
    from tools.sandbox import resolve_allowed_path
    path = resolve_allowed_path(payload["path"])
    max_bytes = int(payload.get("max_bytes") or 1_048_576)
    enc = payload.get("encoding") or "utf-8"
    data = path.read_bytes()[:max_bytes]
    try:
        content = data.decode(enc)
    except Exception:
        content = data.decode("utf-8", errors="replace")
    return {"ok": True, "path": str(path), "content": content, "size": len(data)}


def _run_file_write(payload: dict) -> dict:
    from tools.sandbox import resolve_allowed_path
    # workspace-only: force under /workspace
    path = resolve_allowed_path(payload["path"], workspace=os.environ.get("AGENTBOX_WORKSPACE") or "/workspace")
    ws = Path(os.environ.get("AGENTBOX_WORKSPACE") or "/workspace").resolve()
    try:
        path.relative_to(ws)
    except ValueError:
        # also allow share paths via resolve_allowed_path but MUST says workspace-only for write
        if not str(path).startswith("/workspace"):
            raise PermissionError(f"file.write is workspace-only: {path}")
    content = payload.get("content") or ""
    enc = payload.get("encoding") or "utf-8"
    if payload.get("create_dirs", True):
        path.parent.mkdir(parents=True, exist_ok=True)
    raw = content.encode(enc)
    path.write_bytes(raw)
    return {"ok": True, "path": str(path), "bytes_written": len(raw)}


def _run_git_status(payload: dict) -> dict:
    from tools.sandbox import resolve_allowed_path
    cwd = resolve_allowed_path(payload.get("cwd") or "/workspace/projects/demo-python")
    porcelain = payload.get("porcelain", True)
    cmd = ["git", "status", "--porcelain"] if porcelain else ["git", "status"]
    r = subprocess.run(cmd, cwd=str(cwd), capture_output=True, text=True, timeout=30)
    return {
        "ok": r.returncode == 0,
        "stdout": r.stdout,
        "stderr": r.stderr,
        "exit_code": r.returncode,
        "cwd": str(cwd),
    }


def _run_git_diff(payload: dict) -> dict:
    from tools.sandbox import resolve_allowed_path
    cwd = resolve_allowed_path(payload.get("cwd") or "/workspace/projects/demo-python")
    cmd = ["git", "diff"]
    if payload.get("staged"):
        cmd.append("--cached")
    if payload.get("path"):
        cmd.extend(["--", payload["path"]])
    r = subprocess.run(cmd, cwd=str(cwd), capture_output=True, text=True, timeout=60)
    return {
        "ok": r.returncode == 0,
        "stdout": r.stdout,
        "stderr": r.stderr,
        "exit_code": r.returncode,
        "cwd": str(cwd),
    }


def _run_shell(payload: dict, shell_info: dict) -> dict:
    from tools.sandbox import resolve_allowed_path
    cmd = payload.get("command") or ""
    if shell_info.get("denied"):
        return {
            "ok": False,
            "denied": True,
            "stdout": "",
            "stderr": f"denied: {'; '.join(shell_info.get('reasons') or [])}",
            "exit_code": 126,
            "risk_level": shell_info.get("level"),
        }
    cwd = resolve_allowed_path(payload.get("cwd") or "/workspace")
    timeout = int(payload.get("timeout") or 60)
    env = os.environ.copy()
    if isinstance(payload.get("env"), dict):
        env.update({str(k): str(v) for k, v in payload["env"].items()})
    r = subprocess.run(
        cmd, shell=True, cwd=str(cwd), capture_output=True, text=True,
        timeout=timeout, env=env,
    )
    return {
        "ok": r.returncode == 0,
        "denied": False,
        "stdout": r.stdout,
        "stderr": r.stderr,
        "exit_code": r.returncode,
        "cwd": str(cwd),
    }


def _run_http_get(payload: dict) -> dict:
    url = payload["url"]
    if not url.startswith(("http://", "https://")):
        raise ValueError("url must be http(s)")
    timeout = int(payload.get("timeout") or 15)
    headers = payload.get("headers") or {}
    req = urllib.request.Request(url, headers={str(k): str(v) for k, v in headers.items()}, method="GET")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = resp.read(512_000).decode("utf-8", errors="replace")
            return {
                "ok": True,
                "status_code": getattr(resp, "status", 200),
                "body": body,
                "headers": dict(resp.headers.items()) if resp.headers else {},
            }
    except urllib.error.HTTPError as e:
        return {"ok": False, "status_code": e.code, "body": e.read(65536).decode("utf-8", errors="replace"), "headers": {}}
    except Exception as exc:
        return {"ok": False, "status_code": 0, "body": "", "error": str(exc), "headers": {}}


def _run_docker_ps(payload: dict) -> dict:
    cmd = ["docker", "ps", "--format", "{{.ID}} {{.Image}} {{.Status}} {{.Names}}"]
    if payload.get("all"):
        cmd.insert(2, "-a")
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
    return {
        "ok": r.returncode == 0,
        "stdout": r.stdout,
        "stderr": r.stderr,
        "exit_code": r.returncode,
    }


HANDLERS = {
    "file.read": _run_file_read,
    "file.write": _run_file_write,
    "git.status": _run_git_status,
    "git.diff": _run_git_diff,
    "shell.run": None,  # special
    "http.get": _run_http_get,
    "docker.ps": _run_docker_ps,
}


def execute_tool(
    tool_id: str,
    input_payload: Optional[dict] = None,
    task_context: Optional[dict] = None,
    agent_context: Optional[dict] = None,
    db_path: Optional[str] = None,
) -> dict[str, Any]:
    """Execute a registered tool through enforcement. No bypass."""
    _ensure_path()
    from storage import db as dbmod
    from policy.enforcement import enforce_action
    from tools import registry, outcome_memory
    from tools.sandbox import shell_risk, sandbox_profile_for

    input_payload = dict(input_payload or {})
    task_context = dict(task_context or {})
    agent_context = dict(agent_context or {})
    registry.ensure_builtins(db_path=db_path)

    tool = registry.get_tool(tool_id, db_path=db_path)
    if not tool:
        return {"ok": False, "error": f"tool not found: {tool_id}", "status": "not_found"}
    if not tool.get("enabled"):
        return {"ok": False, "error": f"tool disabled: {tool_id}", "status": "disabled"}
    if tool.get("health_status") == "quarantined":
        return {"ok": False, "error": f"tool quarantined: {tool_id}", "status": "quarantined"}

    err = _validate_input(tool.get("input_schema") or {}, input_payload)
    if err:
        return {"ok": False, "error": err, "status": "invalid_input"}

    shell_info = None
    if tool_id == "shell.run":
        shell_info = shell_risk(input_payload.get("command") or "")

    action, resource, ctx = _action_for_tool(tool_id, input_payload, shell_info)
    ctx.update(task_context)
    # Add shell risk points into risk via context
    if shell_info and shell_info.get("denied"):
        ctx["destructive"] = True
        if shell_info.get("level") == "CRITICAL":
            ctx["force"] = True

    call_id = dbmod.new_id("tc_")
    now = dbmod.utc_now()
    with dbmod.connect(db_path) as conn:
        conn.execute(
            """
            INSERT INTO tool_calls (
                id, tool_id, task_id, run_id, agent_name, status, input_json, input_hash, created_at
            ) VALUES (?,?,?,?,?,?,?,?,?)
            """,
            (
                call_id, tool_id,
                task_context.get("task_id") or agent_context.get("task_id"),
                task_context.get("run_id"),
                agent_context.get("agent_name") or agent_context.get("name"),
                "pending",
                json.dumps(input_payload),
                _hash_payload(input_payload),
                now,
            ),
        )
        conn.commit()

    # Hard deny dangerous shell before enforcement (still record)
    if shell_info and shell_info.get("denied") and shell_info.get("level") == "CRITICAL":
        # Still run through enforce for audit — will deny
        pass

    budget_metric = "max_agent_runs"
    start = time.time()

    def _do_execute():
        if tool_id == "shell.run":
            return _run_shell(input_payload, shell_info or {})
        handler = HANDLERS.get(tool_id)
        if handler is None:
            raise RuntimeError(f"no handler for {tool_id}")
        return handler(input_payload)

    # For denied shell at CRITICAL — enforce will deny; for HIGH non-allowlisted need approval
    # Inject synthetic risk for shell.run HIGH
    if tool_id == "shell.run" and shell_info and not shell_info.get("allowlisted") and not shell_info.get("denied"):
        # Map to an action that requires approval: use packages.install-like elevated
        # Actually use shell.run which isn't in RISK_POINTS → base 25, boost via context
        ctx["elevated_shell"] = True

    # Add custom risk points for shell
    if tool_id == "shell.run":
        # Prefer mapping allowlisted to low, else high approval path
        if shell_info and shell_info.get("allowlisted"):
            action = "filesystem.read"  # low
        elif shell_info and shell_info.get("denied"):
            action = "git.force_push" if shell_info.get("level") == "CRITICAL" else "git.push"
        else:
            action = "git.push"  # HIGH → approval (or AUTO_APPROVE)

    try:
        dbmod.emit_event(kind="tool.started", message=tool_id, payload={"call_id": call_id}, db_path=db_path)
    except Exception:
        pass

    enforcement = enforce_action(
        action,
        resource=resource,
        task_id=task_context.get("task_id") or agent_context.get("task_id"),
        run_id=task_context.get("run_id"),
        agent_name=agent_context.get("agent_name") or agent_context.get("name"),
        context=ctx,
        budget_metric=budget_metric,
        budget_value=1.0,
        execute=None,  # we execute only on allow
        db_path=db_path,
    )

    decision = enforcement.get("decision")
    duration_ms = int((time.time() - start) * 1000)
    risk = enforcement.get("risk") or {}
    out: dict[str, Any] = {
        "call_id": call_id,
        "tool_id": tool_id,
        "decision": decision,
        "enforcement": {
            "decision": decision,
            "reason": enforcement.get("reason"),
            "risk_level": risk.get("risk_level"),
            "risk_score": risk.get("risk_score"),
            "approval_id": enforcement.get("approval_id"),
        },
        "sandbox_profile": sandbox_profile_for(tool_id, risk.get("risk_level") or tool.get("risk_level") or "LOW"),
    }

    if decision == "deny":
        result = {
            "ok": False,
            "denied": True,
            "stderr": enforcement.get("reason") or "denied by policy",
            "exit_code": 126,
        }
        if shell_info and shell_info.get("denied"):
            result["stderr"] = "; ".join(shell_info.get("reasons") or []) or result["stderr"]
            result["shell_risk"] = shell_info
        out.update(result)
        out["status"] = "denied"
        out["ok"] = False
        _finalize_call(call_id, tool_id, "denied", input_payload, result, enforcement, duration_ms, db_path)
        outcome_memory.record_outcome(
            tool_id, call_id=call_id, capability=tool_id,
            success=False, failure_type="denied", latency_ms=duration_ms,
            meta={"reason": enforcement.get("reason")}, db_path=db_path,
        )
        return out

    if decision == "approval":
        out["ok"] = False
        out["status"] = "awaiting_approval"
        out["approval_id"] = enforcement.get("approval_id")
        out["message"] = "tool call requires approval"
        _finalize_call(
            call_id, tool_id, "awaiting_approval", input_payload,
            {"ok": False, "awaiting_approval": True}, enforcement, duration_ms, db_path,
        )
        outcome_memory.record_outcome(
            tool_id, call_id=call_id, capability=tool_id,
            success=False, failure_type="approval_required", latency_ms=duration_ms,
            db_path=db_path,
        )
        return out

    # ALLOW → execute
    try:
        result = _do_execute()
        duration_ms = int((time.time() - start) * 1000)
        success = bool(result.get("ok"))
        out.update(result)
        out["ok"] = success
        out["status"] = "completed" if success else "failed"
        out["duration_ms"] = duration_ms
        _finalize_call(call_id, tool_id, out["status"], input_payload, result, enforcement, duration_ms, db_path)
        outcome_memory.record_outcome(
            tool_id, call_id=call_id, capability=(tool.get("capabilities") or [tool_id])[0],
            success=success,
            failure_type=None if success else "exec_failed",
            latency_ms=duration_ms,
            db_path=db_path,
        )
        try:
            dbmod.emit_event(
                kind="tool.completed" if success else "tool.failed",
                message=tool_id,
                payload={"call_id": call_id, "ok": success},
                db_path=db_path,
            )
        except Exception:
            pass
        return out
    except subprocess.TimeoutExpired:
        duration_ms = int((time.time() - start) * 1000)
        result = {"ok": False, "error": "timeout", "exit_code": 124}
        out.update(result)
        out["status"] = "timeout"
        _finalize_call(call_id, tool_id, "timeout", input_payload, result, enforcement, duration_ms, db_path)
        outcome_memory.record_outcome(
            tool_id, call_id=call_id, success=False, failure_type="timeout",
            latency_ms=duration_ms, db_path=db_path,
        )
        return out
    except Exception as exc:
        duration_ms = int((time.time() - start) * 1000)
        result = {"ok": False, "error": str(exc), "exit_code": 1}
        out.update(result)
        out["status"] = "failed"
        _finalize_call(call_id, tool_id, "failed", input_payload, result, enforcement, duration_ms, db_path)
        outcome_memory.record_outcome(
            tool_id, call_id=call_id, success=False, failure_type="exception",
            latency_ms=duration_ms, meta={"error": str(exc)}, db_path=db_path,
        )
        return out


def _finalize_call(
    call_id: str,
    tool_id: str,
    status: str,
    input_payload: dict,
    result: dict,
    enforcement: dict,
    duration_ms: int,
    db_path: Optional[str],
) -> None:
    _ensure_path()
    from storage import db as dbmod
    risk = enforcement.get("risk") or {}
    with dbmod.connect(db_path) as conn:
        conn.execute(
            """
            UPDATE tool_calls SET
                status=?, output_json=?, output_hash=?, exit_code=?, duration_ms=?,
                risk_score=?, risk_level=?, decision=?, approval_id=?, error=?, finished_at=?
            WHERE id=?
            """,
            (
                status,
                json.dumps(result, default=str),
                _hash_payload(result),
                result.get("exit_code"),
                duration_ms,
                risk.get("risk_score"),
                risk.get("risk_level"),
                enforcement.get("decision"),
                enforcement.get("approval_id"),
                result.get("error") or result.get("stderr"),
                dbmod.utc_now(),
                call_id,
            ),
        )
        conn.commit()
