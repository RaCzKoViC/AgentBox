"""Node quarantine / unquarantine."""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

_HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(_HERE.parent))

from distributed import registry  # noqa: E402
from distributed import enrollment  # noqa: E402


def quarantine(worker_id: str, reason: str = "manual") -> dict[str, Any]:
    w = registry.get_worker(worker_id)
    if not w:
        raise KeyError(worker_id)
    enrollment.revoke_sessions(w["id"])
    return registry.set_status(w["id"], "quarantined", reason=reason)


def unquarantine(worker_id: str) -> dict[str, Any]:
    w = registry.get_worker(worker_id)
    if not w:
        raise KeyError(worker_id)
    return registry.set_status(w["id"], "offline", reason="unquarantined")


def drain(worker_id: str) -> dict[str, Any]:
    w = registry.get_worker(worker_id)
    if not w:
        raise KeyError(worker_id)
    return registry.set_status(w["id"], "draining", reason="drain")
