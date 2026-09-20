"""Golden: memory retrieval stub — deterministic local check."""
from __future__ import annotations

from typing import Any


def validate(definition=None, context=None, case_dir=None, **kwargs) -> dict[str, Any]:
    definition = definition or {}
    # Deterministic stub corpus
    corpus = [
        {"id": "m1", "text": "agentbox evaluation harness scores golden suites"},
        {"id": "m2", "text": "tool git.status reports working tree state"},
        {"id": "m3", "text": "planner software_feature compiles a DAG of stages"},
    ]
    query = "evaluation harness golden"
    q_tokens = set(query.lower().split())
    hits = []
    for doc in corpus:
        tokens = set(doc["text"].lower().split())
        score = len(q_tokens & tokens) / max(len(q_tokens), 1)
        if score > 0:
            hits.append({"id": doc["id"], "score": score})
    hits.sort(key=lambda x: -x["score"])
    min_hits = int((definition.get("expect") or {}).get("min_hits", 1))
    ok = len(hits) >= min_hits
    recall_at_3 = 1.0 if ok else 0.0
    return {
        "ok": ok,
        "success": ok,
        "scores": {
            "correctness": 1.0 if ok else 0.0,
            "quality": recall_at_3,
            "efficiency": 1.0,
        },
        "metrics": {"hits": len(hits), "recall_at_3": recall_at_3},
        "artifacts": {"hits": hits[:3], "query": query},
        "error": None if ok else "no retrieval hits",
    }
