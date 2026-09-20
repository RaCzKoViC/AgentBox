#!/usr/bin/env python3
"""Autonomous retry strategy + failure taxonomy + loop detection."""
from __future__ import annotations

import re
from typing import Any, Optional

FAILURE_CLASSES = [
    "TRANSIENT", "CODE", "TEST", "DEPENDENCY", "PROVIDER",
    "WORKER", "POLICY", "BUDGET", "APPROVAL", "SECURITY", "UNKNOWN",
]

# failure_class -> action
DECISION_MATRIX = {
    "TRANSIENT": {"action": "retry", "fallback_agent": None, "max_attempts": 3},
    "CODE": {"action": "debugger", "fallback_agent": "debugger", "max_attempts": 2},
    "TEST": {"action": "debugger", "fallback_agent": "coder", "max_attempts": 2},
    "DEPENDENCY": {"action": "replan", "fallback_agent": "researcher", "max_attempts": 1},
    "PROVIDER": {"action": "fallback", "fallback_agent": None, "max_attempts": 2},
    "WORKER": {"action": "failover", "fallback_agent": None, "max_attempts": 2},
    "POLICY": {"action": "block", "fallback_agent": None, "max_attempts": 0},
    "BUDGET": {"action": "pause", "fallback_agent": None, "max_attempts": 0},
    "APPROVAL": {"action": "wait", "fallback_agent": None, "max_attempts": 0},
    "SECURITY": {"action": "block", "fallback_agent": None, "max_attempts": 0},
    "UNKNOWN": {"action": "replan", "fallback_agent": "planner", "max_attempts": 1},
}

_PATTERNS = [
    ("POLICY", r"policy.?denied|not.?allowed|forbidden"),
    ("SECURITY", r"security|secret|credential|force.?push"),
    ("APPROVAL", r"approval|awaiting.?approval|rejected.?by.?human"),
    ("BUDGET", r"budget|quota|cost.?exceed"),
    ("PROVIDER", r"rate.?limit|provider|timeout|503|429"),
    ("WORKER", r"worker.?(lost|offline|dead)|lease.?expir"),
    ("TEST", r"assertion|pytest|test.?fail|failed.?test"),
    ("CODE", r"syntax|traceback|typeerror|nameerror|compile"),
    ("DEPENDENCY", r"import.?error|module.?not.?found|dependency|version.?conflict"),
    ("TRANSIENT", r"temporar|retry|connection.?reset|timed?\s*out"),
]


def classify_failure(error: str = "", observations: Optional[dict] = None) -> str:
    obs = observations or {}
    text = f"{error or ''} {obs.get('error') or ''} {obs.get('message') or ''}".lower()
    if obs.get("failure_class") in FAILURE_CLASSES:
        return obs["failure_class"]
    for cls, pat in _PATTERNS:
        if re.search(pat, text, re.I):
            return cls
    return "UNKNOWN"


def decide_retry(
    failure_class: str,
    attempt: int = 1,
    recent_errors: Optional[list] = None,
) -> dict[str, Any]:
    base = dict(DECISION_MATRIX.get(failure_class, DECISION_MATRIX["UNKNOWN"]))
    recent = recent_errors or []
    loop = detect_loop(recent)
    if loop.get("loop_detected"):
        return {
            "action": "escalate",
            "failure_class": failure_class,
            "attempt": attempt,
            "loop_detected": True,
            "reason": loop.get("reason"),
            "title": "Human escalation: loop detected",
            "fallback_agent": None,
            "max_attempts": 0,
        }
    max_a = int(base.get("max_attempts") or 0)
    if attempt > max_a or base["action"] in ("block", "pause", "wait"):
        return {
            **base,
            "failure_class": failure_class,
            "attempt": attempt,
            "loop_detected": False,
            "exhausted": True,
            "action": "escalate" if base["action"] not in ("block", "pause", "wait") else base["action"],
            "title": f"Escalate after {failure_class}",
        }
    title_map = {
        "retry": f"Retry after {failure_class}",
        "debugger": "Debug failed step",
        "replan": "Research/replan dependency",
        "fallback": "Provider fallback retry",
        "failover": "Worker failover retry",
    }
    return {
        **base,
        "failure_class": failure_class,
        "attempt": attempt,
        "loop_detected": False,
        "exhausted": False,
        "title": title_map.get(base["action"], f"Handle {failure_class}"),
    }


def detect_loop(recent_errors: list, threshold: int = 3) -> dict[str, Any]:
    if not recent_errors:
        return {"loop_detected": False}
    # normalize
    norms = []
    for e in recent_errors[-10:]:
        if isinstance(e, dict):
            norms.append(str(e.get("error") or e.get("message") or e).strip().lower()[:200])
        else:
            norms.append(str(e).strip().lower()[:200])
    if len(norms) < threshold:
        return {"loop_detected": False}
    last = norms[-1]
    count = sum(1 for n in norms[-threshold:] if n == last)
    if count >= threshold:
        return {"loop_detected": True, "reason": f"same error x{count}", "error": last}
    return {"loop_detected": False}
