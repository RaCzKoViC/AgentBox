"""Evaluation & proposals REST API (v5.5)."""
from __future__ import annotations

from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from ..deps import Actor, get_actor, require_role

router = APIRouter(tags=["evaluation"])


class EvalRunBody(BaseModel):
    suite_id: str = "golden"
    subject_type: str = "platform"
    subject_id: str = "agentbox"
    set_baseline: bool = False
    threshold: Optional[float] = None


class ProposeMineBody(BaseModel):
    min_count: int = 1


class ProposalActionBody(BaseModel):
    apply: bool = False
    reason: str = ""


@router.get("/api/v1/eval/suites")
@router.get("/api/v1/evaluation/suites")
def list_suites(_actor: Actor = Depends(get_actor)):
    from evaluation.suites import list_suites as _ls
    suites = _ls(sync=True)
    return {
        "suites": [
            {
                "id": s["id"],
                "name": s.get("name"),
                "version": s.get("version"),
                "case_count": s.get("case_count"),
                "description": s.get("description"),
            }
            for s in suites
        ],
        "count": len(suites),
    }


@router.post("/api/v1/eval/runs")
@router.post("/api/v1/evaluation/runs")
def start_run(body: EvalRunBody, _actor: Actor = Depends(require_role("operator"))):
    from evaluation.harness import run_suite
    try:
        result = run_suite(
            body.suite_id,
            subject_type=body.subject_type,
            subject_id=body.subject_id,
            set_as_baseline=body.set_baseline,
            threshold=body.threshold,
        )
    except ValueError as e:
        raise HTTPException(404, str(e))
    return {
        "run_id": result["run_id"],
        "suite_id": result["suite_id"],
        "status": result["status"],
        "score": result["score"],
        "gate": result["gate"],
        "summary": result["summary"],
    }


@router.get("/api/v1/eval/runs")
@router.get("/api/v1/evaluation/runs")
def list_runs(suite_id: Optional[str] = None, limit: int = 50, _actor: Actor = Depends(get_actor)):
    from evaluation.store import list_runs as _lr
    return {"runs": _lr(suite_id=suite_id, limit=limit)}


@router.get("/api/v1/eval/runs/{run_id}")
@router.get("/api/v1/evaluation/runs/{run_id}")
def get_run(run_id: str, _actor: Actor = Depends(get_actor)):
    from evaluation.store import get_run as _gr
    run = _gr(run_id)
    if not run:
        raise HTTPException(404, "run not found")
    return run


@router.get("/api/v1/eval/runs/{run_id}/report")
@router.get("/api/v1/evaluation/runs/{run_id}/report")
def run_report(run_id: str, _actor: Actor = Depends(get_actor)):
    from evaluation.store import get_run as _gr
    run = _gr(run_id)
    if not run:
        raise HTTPException(404, "run not found")
    meta = run.get("metadata") or {}
    return {
        "run_id": run_id,
        "suite_id": run.get("suite_id"),
        "status": run.get("status"),
        "score": run.get("score"),
        "gate_status": run.get("gate_status"),
        "summary": meta.get("summary"),
        "gate": meta.get("gate"),
        "regressions": meta.get("regressions"),
        "results": run.get("results"),
    }


@router.get("/api/v1/eval/baselines")
@router.get("/api/v1/baselines")
def baselines(suite_id: Optional[str] = None, _actor: Actor = Depends(get_actor)):
    from evaluation.baselines import get_baseline, list_baselines
    if suite_id:
        bl = get_baseline(suite_id)
        return {"baseline": bl}
    return {"baselines": list_baselines()}


@router.get("/api/v1/eval/regressions")
def regressions(limit: int = 50, _actor: Actor = Depends(get_actor)):
    from evaluation.regressions import list_regressions
    return {"regressions": list_regressions(limit=limit)}


@router.post("/api/v1/quality-gates/check")
def quality_gate_check(body: dict[str, Any], _actor: Actor = Depends(get_actor)):
    from evaluation.quality_gates import check_gate
    summary = body.get("summary") or {}
    results = body.get("results") or []
    return check_gate(summary, results, threshold=body.get("threshold"))


@router.get("/api/v1/benchmarks")
def benchmarks(_actor: Actor = Depends(get_actor)):
    from benchmarks.registry import list_benchmarks
    items = list_benchmarks()
    return {"benchmarks": items, "count": len(items)}


@router.post("/api/v1/benchmarks/{suite_id}/run")
def benchmark_run(suite_id: str, _actor: Actor = Depends(require_role("operator"))):
    from evaluation.harness import run_suite
    try:
        result = run_suite(suite_id)
    except ValueError as e:
        raise HTTPException(404, str(e))
    return {"run_id": result["run_id"], "status": result["status"], "score": result["score"], "gate": result["gate"]}


@router.get("/api/v1/proposals")
@router.get("/api/v1/improvements")
def list_proposals(status: Optional[str] = None, _actor: Actor = Depends(get_actor)):
    from evaluation.proposals import list_proposals as _lp
    items = _lp(status=status)
    return {"proposals": items, "count": len(items)}


@router.get("/api/v1/proposals/{proposal_id}")
@router.get("/api/v1/improvements/{proposal_id}")
def get_proposal(proposal_id: str, _actor: Actor = Depends(get_actor)):
    from evaluation.proposals import get_proposal as _gp
    p = _gp(proposal_id)
    if not p:
        raise HTTPException(404, "proposal not found")
    return p


@router.post("/api/v1/proposals/{proposal_id}/approve")
@router.post("/api/v1/improvements/{proposal_id}/approve")
def approve_proposal(proposal_id: str, body: Optional[ProposalActionBody] = None,
                     _actor: Actor = Depends(require_role("operator"))):
    from evaluation.proposals import approve
    try:
        return approve(proposal_id, apply=bool(body and body.apply))
    except ValueError as e:
        raise HTTPException(400, str(e))


@router.post("/api/v1/proposals/{proposal_id}/reject")
@router.post("/api/v1/improvements/{proposal_id}/reject")
def reject_proposal(proposal_id: str, body: Optional[ProposalActionBody] = None,
                    _actor: Actor = Depends(require_role("operator"))):
    from evaluation.proposals import reject
    try:
        return reject(proposal_id, reason=(body.reason if body else ""))
    except ValueError as e:
        raise HTTPException(400, str(e))


@router.post("/api/v1/proposals/mine")
def mine_proposals(body: Optional[ProposeMineBody] = None,
                   _actor: Actor = Depends(require_role("operator"))):
    from evaluation.failure_mining import propose_from_failures, mine_failures
    mined = mine_failures()
    created = propose_from_failures(min_count=(body.min_count if body else 1))
    return {"mined": mined, "proposals": created, "count": len(created)}


@router.get("/api/v1/eval/failures")
def failure_clusters(_actor: Actor = Depends(get_actor)):
    from evaluation.failure_mining import mine_failures
    return mine_failures()
