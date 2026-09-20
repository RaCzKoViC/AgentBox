"""Smoke tests for evaluation harness (run with AGENTBOX_V5_ROOT set)."""
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "lib"))
os.environ.setdefault("AGENTBOX_V5_ROOT", str(ROOT))


def test_ab_assign():
    from evaluation.ab_test import assign_variant
    a = assign_variant("task-1", ["A", "B"])
    b = assign_variant("task-1", ["A", "B"])
    assert a == b
    assert a in ("A", "B")


def test_scoring():
    from evaluation.scoring import score_case
    s = score_case(True, runtime_ms=100)
    assert s["correctness"] == 1.0


def test_quality_gate_fail():
    from evaluation.quality_gates import check_gate
    g = check_gate({"score": 0.1}, [{"success": False, "critical": True, "case_id": "x"}], threshold=0.8)
    assert not g["passed"]
