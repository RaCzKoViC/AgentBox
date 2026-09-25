"""AgentBox v5.6 — Operations Autopilot & Autonomous Platform Maintenance."""
from __future__ import annotations

def _platform_version() -> str:
    """Platform version from the VERSION file (single source of truth)."""
    try:
        from ops.paths import read_version
        return read_version()
    except Exception:
        return "5.6.3"


VERSION = _platform_version()

__all__ = [
    "VERSION",
    "status",
    "scan",
    "remediate",
    "list_playbooks",
    "run_playbook",
]

def status(*args, **kwargs):
    from ops_autopilot.remediation import status as _s
    return _s(*args, **kwargs)

def scan(*args, **kwargs):
    from ops_autopilot.remediation import scan as _scan
    return _scan(*args, **kwargs)

def remediate(*args, **kwargs):
    from ops_autopilot.remediation import remediate as _r
    return _r(*args, **kwargs)

def list_playbooks(*args, **kwargs):
    from ops_autopilot.playbooks import list_playbooks as _lp
    return _lp(*args, **kwargs)

def run_playbook(*args, **kwargs):
    from ops_autopilot.playbooks import run_playbook as _rp
    return _rp(*args, **kwargs)
