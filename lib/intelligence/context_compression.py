#!/usr/bin/env python3
"""Context compression — drop low-score, never drop critical constraints."""
from __future__ import annotations

from typing import Any, Optional

NEVER_DROP_PREFIXES = (
    "task goal",
    "security",
    "policy",
    "approval",
    "critical",
    "acceptance",
    "constraint",
)


def estimate_tokens(text: str, cpt: int = 4) -> int:
    if not text:
        return 0
    return max(1, (len(text) + cpt - 1) // cpt)


def _is_critical(item: str) -> bool:
    low = (item or "").lower()
    return any(low.startswith(p) or p in low for p in NEVER_DROP_PREFIXES)


def compress_package(
    package: dict[str, Any],
    *,
    token_budget: int = 4000,
    chars_per_token: int = 4,
) -> dict[str, Any]:
    """Compress a context package dict to fit token_budget. Preserves criticals."""
    before = estimate_tokens(str(package), chars_per_token)
    out = dict(package)
    constraints = list(out.get("constraints") or [])
    critical = [c for c in constraints if _is_critical(c)]
    soft = [c for c in constraints if not _is_critical(c)]

    hits = list(out.get("hits") or out.get("code_hits") or [])
    hits = sorted(hits, key=lambda h: -(h.get("rerank_score") or h.get("score") or 0))

    # iterative drop
    def pack_size(h_list, soft_c) -> int:
        trial = {**out, "hits": h_list, "code_hits": h_list, "constraints": critical + soft_c}
        return estimate_tokens(str(trial), chars_per_token)

    while hits and pack_size(hits, soft) > token_budget:
        hits.pop()  # drop lowest (end of sorted desc → pop last)
    while soft and pack_size(hits, soft) > token_budget:
        soft.pop()

    # truncate previews
    for h in hits:
        prev = h.get("text_preview") or h.get("content") or ""
        if estimate_tokens(prev, chars_per_token) > 300:
            h["text_preview"] = prev[:1200]
            h["content"] = prev[:1200]

    out["hits"] = hits
    out["code_hits"] = hits
    out["constraints"] = critical + soft
    out["compression"] = {
        "tokens_before": before,
        "tokens_after": pack_size(hits, soft),
        "budget": token_budget,
        "dropped_hits": max(0, len(package.get("hits") or package.get("code_hits") or []) - len(hits)),
        "critical_retained": len(critical),
    }
    return out
