#!/usr/bin/env python3
"""Simple hybrid reranker — semantic + keyword + importance + recency."""
from __future__ import annotations

import math
import re
from datetime import datetime, timezone
from typing import Any, Optional


def _tokens(text: str) -> set[str]:
    return {t.lower() for t in re.findall(r"[a-zA-Z_][a-zA-Z0-9_]{1,40}", text or "")}


def keyword_overlap(query: str, text: str) -> float:
    qt = _tokens(query)
    tt = _tokens(text)
    if not qt or not tt:
        return 0.0
    return len(qt & tt) / max(1, len(qt))


def _parse_ts(ts: Optional[str]) -> float:
    if not ts:
        return 0.0
    try:
        # accept ...Z
        s = ts.replace("Z", "+00:00")
        dt = datetime.fromisoformat(s)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.timestamp()
    except Exception:
        return 0.0


def score_item(
    query: str,
    item: dict[str, Any],
    *,
    weights: Optional[dict[str, float]] = None,
) -> float:
    w = {
        "semantic": 0.40,
        "keyword": 0.25,
        "importance": 0.15,
        "recency": 0.10,
        "confidence": 0.10,
    }
    if weights:
        w.update(weights)
    sem = float(item.get("score") or item.get("semantic") or 0.0)
    text = item.get("text") or item.get("content") or item.get("text_preview") or ""
    sym = item.get("symbol") or ""
    path = item.get("file_path") or ""
    kw = keyword_overlap(query, f"{text} {sym} {path}")
    # boost if query token appears in path/symbol
    if any(t in (path + " " + sym).lower() for t in _tokens(query)):
        kw = min(1.0, kw + 0.25)
    importance = float(item.get("importance") or 0.5)
    confidence = float(item.get("confidence") or 0.5)
    ts = _parse_ts(item.get("updated_at") or item.get("created_at") or item.get("last_used_at"))
    now = datetime.now(timezone.utc).timestamp()
    recency = 0.0
    if ts > 0:
        age_days = max(0.0, (now - ts) / 86400.0)
        recency = math.exp(-age_days / 30.0)  # ~month half-life soft
    return (
        w["semantic"] * sem
        + w["keyword"] * kw
        + w["importance"] * importance
        + w["recency"] * recency
        + w["confidence"] * confidence
    )


def rerank(
    query: str,
    candidates: list[dict[str, Any]],
    *,
    top_k: int = 10,
    weights: Optional[dict[str, float]] = None,
) -> list[dict[str, Any]]:
    out = []
    for c in candidates:
        item = dict(c)
        item["rerank_score"] = score_item(query, item, weights=weights)
        out.append(item)
    out.sort(key=lambda x: x["rerank_score"], reverse=True)
    return out[: max(1, int(top_k))]
