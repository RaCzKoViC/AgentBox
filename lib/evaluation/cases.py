"""Load and execute individual benchmark cases (deterministic stubs)."""
from __future__ import annotations

import importlib.util
import json
import sys
import time
import traceback
from pathlib import Path
from typing import Any, Callable, Optional

_HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(_HERE.parent))

from evaluation.scoring import score_case  # noqa: E402


def _load_validator(case_dir: Path) -> Optional[Callable[..., Any]]:
    vp = case_dir / "validators.py"
    if not vp.is_file():
        return None
    spec = importlib.util.spec_from_file_location(f"golden_val_{case_dir.name}", vp)
    if not spec or not spec.loader:
        return None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return getattr(mod, "validate", None) or getattr(mod, "run", None)


def run_case(case: dict[str, Any], context: Optional[dict[str, Any]] = None) -> dict[str, Any]:
    """Run one golden/benchmark case. Fast, deterministic, no Codex."""
    context = context or {}
    case_dir = Path(case.get("path") or "")
    definition = case.get("definition") or {}
    case_id = case.get("id") or case_dir.name
    t0 = time.perf_counter()
    success = False
    error = None
    artifacts: dict[str, Any] = {}
    extra_scores: dict[str, Any] = {}
    metrics: dict[str, Any] = {}

    try:
        kind = definition.get("kind") or definition.get("type") or "validator"
        if kind in ("validator", "golden", "stub"):
            validate = _load_validator(case_dir) if case_dir.is_dir() else None
            if validate is None:
                # inline check from definition
                success, artifacts, extra_scores = _inline_check(definition, context)
            else:
                result = validate(definition=definition, context=context, case_dir=case_dir)
                if isinstance(result, bool):
                    success = result
                elif isinstance(result, dict):
                    success = bool(result.get("success", result.get("ok", False)))
                    artifacts = result.get("artifacts") or {}
                    extra_scores = result.get("scores") or {}
                    metrics = result.get("metrics") or {}
                    error = result.get("error")
                else:
                    success = bool(result)
        elif kind == "always_pass":
            success = True
            artifacts = {"note": "always_pass"}
        elif kind == "always_fail":
            success = False
            error = "always_fail"
        else:
            validate = _load_validator(case_dir) if case_dir.is_dir() else None
            if validate:
                result = validate(definition=definition, context=context, case_dir=case_dir)
                if isinstance(result, dict):
                    success = bool(result.get("success", result.get("ok", False)))
                    artifacts = result.get("artifacts") or {}
                    extra_scores = result.get("scores") or {}
                    metrics = result.get("metrics") or {}
                    error = result.get("error")
                else:
                    success = bool(result)
            else:
                error = f"unknown kind {kind} and no validators.py"
                success = False
    except Exception as e:
        success = False
        error = f"{type(e).__name__}: {e}"
        artifacts["traceback"] = traceback.format_exc()[-2000:]

    runtime_ms = (time.perf_counter() - t0) * 1000.0
    metrics.setdefault("runtime_ms", round(runtime_ms, 2))
    scores = score_case(success, extra_scores, runtime_ms=runtime_ms, cost=float(metrics.get("cost") or 0))
    return {
        "case_id": case_id,
        "name": case.get("name") or case_id,
        "success": success,
        "scores": scores,
        "metrics": metrics,
        "artifacts": artifacts,
        "error": error,
        "critical": bool(case.get("critical", definition.get("critical", True))),
    }


def _inline_check(definition: dict[str, Any], context: dict[str, Any]) -> tuple[bool, dict, dict]:
    expect = definition.get("expect") or definition.get("expected") or {}
    if "success" in expect:
        return bool(expect["success"]), {"inline": True}, {}
    return True, {"inline": True, "note": "no expect; pass"}, {}
