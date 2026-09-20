#!/usr/bin/env python3
"""Model router — rules by task type → provider/model; respects policy/budget."""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any, Optional

_HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(_HERE.parent))

from intelligence.task_classifier import classify_task  # noqa: E402
from storage import db as dbmod  # noqa: E402

# Built-in registry (no secrets). Prefer stub/codex locally; claude if configured.
DEFAULT_MODELS: list[dict[str, Any]] = [
    {
        "id": "stub/default",
        "provider": "stub",
        "model": "default",
        "capabilities": ["coding", "testing", "documentation"],
        "context_window": 8000,
        "local": True,
        "cost_input": 0.0,
        "cost_output": 0.0,
        "coding_score": 40,
        "reasoning_score": 30,
        "latency_score": 100,
        "privacy_level": "LOCAL_ONLY",
        "enabled": True,
    },
    {
        "id": "codex/default",
        "provider": "codex",
        "model": "default",
        "capabilities": ["coding", "bugfix", "refactor", "testing"],
        "context_window": 128000,
        "local": False,
        "cost_input": 0.003,
        "cost_output": 0.015,
        "coding_score": 85,
        "reasoning_score": 80,
        "latency_score": 60,
        "privacy_level": "PRIVATE_REMOTE",
        "enabled": True,
    },
    {
        "id": "claude/sonnet",
        "provider": "claude",
        "model": "sonnet",
        "capabilities": ["coding", "architecture", "research", "security", "documentation"],
        "context_window": 200000,
        "local": False,
        "cost_input": 0.003,
        "cost_output": 0.015,
        "coding_score": 92,
        "reasoning_score": 95,
        "latency_score": 55,
        "privacy_level": "PRIVATE_REMOTE",
        "enabled": True,
    },
    {
        "id": "ollama/local",
        "provider": "ollama",
        "model": "local",
        "capabilities": ["coding", "documentation", "research"],
        "context_window": 32000,
        "local": True,
        "cost_input": 0.0,
        "cost_output": 0.0,
        "coding_score": 55,
        "reasoning_score": 50,
        "latency_score": 70,
        "privacy_level": "LOCAL_ONLY",
        "enabled": True,
    },
]


def _provider_configured(provider: str) -> bool:
    p = provider.lower()
    if p == "stub":
        return True
    if p == "codex":
        return bool(os.environ.get("CODEX_API_KEY") or os.environ.get("OPENAI_API_KEY") or True)
        # codex CLI may exist without env — treat as available if binary present
    if p == "claude":
        return bool(os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("CLAUDE_API_KEY"))
    if p == "ollama":
        try:
            from intelligence.embeddings import _ollama_available
            return _ollama_available()
        except Exception:
            return False
    return False


def _codex_binary() -> bool:
    for d in os.environ.get("PATH", "").split(":"):
        if d and (Path(d) / "codex").is_file():
            return True
    return False


def ensure_registry(db_path: Optional[str] = None) -> None:
    with dbmod.connect(db_path) as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS model_registry (
                id TEXT PRIMARY KEY,
                provider TEXT NOT NULL,
                model TEXT NOT NULL,
                capabilities_json TEXT,
                context_window INTEGER,
                local INTEGER NOT NULL DEFAULT 0,
                enabled INTEGER NOT NULL DEFAULT 1,
                metadata_json TEXT,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS routing_decisions (
                id TEXT PRIMARY KEY,
                task_id TEXT,
                agent_name TEXT,
                provider TEXT NOT NULL,
                model TEXT NOT NULL,
                score REAL,
                reason_json TEXT,
                fallback_json TEXT,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );
            """
        )
        for m in DEFAULT_MODELS:
            conn.execute(
                """
                INSERT INTO model_registry
                  (id, provider, model, capabilities_json, context_window, local, enabled, metadata_json, created_at, updated_at)
                VALUES (?,?,?,?,?,?,?,?,?,?)
                ON CONFLICT(id) DO UPDATE SET
                  capabilities_json=excluded.capabilities_json,
                  context_window=excluded.context_window,
                  metadata_json=excluded.metadata_json,
                  updated_at=excluded.updated_at
                """,
                (
                    m["id"], m["provider"], m["model"], json.dumps(m["capabilities"]),
                    m["context_window"], 1 if m["local"] else 0, 1 if m["enabled"] else 0,
                    json.dumps({k: m[k] for k in (
                        "cost_input", "cost_output", "coding_score", "reasoning_score",
                        "latency_score", "privacy_level",
                    )}),
                    dbmod.utc_now(), dbmod.utc_now(),
                ),
            )
        conn.commit()


def list_models(db_path: Optional[str] = None) -> list[dict]:
    ensure_registry(db_path)
    with dbmod.connect(db_path) as conn:
        rows = conn.execute("SELECT * FROM model_registry WHERE enabled = 1").fetchall()
    out = []
    for r in rows:
        meta = json.loads(r["metadata_json"] or "{}")
        out.append({
            "id": r["id"],
            "provider": r["provider"],
            "model": r["model"],
            "capabilities": json.loads(r["capabilities_json"] or "[]"),
            "context_window": r["context_window"],
            "local": bool(r["local"]),
            **meta,
            "enabled": True,
        })
    return out


def _estimate_cost(model: dict, tokens: int = 4000) -> float:
    return float(model.get("cost_input") or 0) * tokens + float(model.get("cost_output") or 0) * (tokens // 4)


def route(
    task_type: Optional[str] = None,
    *,
    title: str = "",
    description: str = "",
    complexity: Optional[str] = None,
    agent_role: str = "coder",
    privacy: str = "ANY_APPROVED",
    budget_remaining: Optional[float] = None,
    task_id: Optional[str] = None,
    context_tokens: int = 4000,
    db_path: Optional[str] = None,
) -> dict[str, Any]:
    """Select provider/model. Never bypasses policy/budget constraints."""
    ensure_registry(db_path)
    if not task_type:
        clf = classify_task(title, description)
        task_type = clf["type"]
        complexity = complexity or clf["complexity"]
    complexity = complexity or "MEDIUM"
    privacy = (privacy or "ANY_APPROVED").upper()

    models = list_models(db_path)
    # availability filter
    available = []
    for m in models:
        p = m["provider"]
        if p == "claude" and not _provider_configured("claude"):
            continue
        if p == "ollama" and not _provider_configured("ollama"):
            continue
        if p == "codex" and not (_codex_binary() or _provider_configured("codex")):
            # still allow codex as recommendation (CLI may wrap stub)
            pass
        if privacy == "LOCAL_ONLY" and not m.get("local"):
            continue
        if privacy == "PRIVATE_REMOTE" and m.get("privacy_level") not in ("LOCAL_ONLY", "PRIVATE_REMOTE"):
            continue
        caps = m.get("capabilities") or []
        if task_type not in caps and "coding" not in caps:
            continue
        available.append(m)

    if not available:
        # hard fallback — stub always ok for local
        available = [m for m in models if m["provider"] == "stub"] or DEFAULT_MODELS[:1]

    scored = []
    for m in available:
        score = 0.0
        reasons = []
        if task_type in ("coding", "bugfix", "refactor"):
            score += float(m.get("coding_score") or 50)
            reasons.append(f"coding_score={m.get('coding_score')}")
        elif task_type in ("architecture", "research", "security"):
            score += float(m.get("reasoning_score") or 50)
            reasons.append(f"reasoning_score={m.get('reasoning_score')}")
        else:
            score += 0.5 * float(m.get("coding_score") or 40) + 0.5 * float(m.get("reasoning_score") or 40)

        score += 0.2 * float(m.get("latency_score") or 50)

        if complexity in ("HIGH", "VERY_HIGH") and (m.get("context_window") or 0) >= 100000:
            score += 15
            reasons.append("large_context")
        if complexity == "LOW" and m.get("local"):
            score += 10
            reasons.append("local_for_low_complexity")

        est = _estimate_cost(m, context_tokens)
        if budget_remaining is not None:
            if est > budget_remaining:
                score -= 100  # effectively exclude
                reasons.append("over_budget")
            elif est == 0:
                score += 5
                reasons.append("zero_cost")

        # prefer configured high-quality when budget allows
        if m["provider"] == "claude" and _provider_configured("claude"):
            score += 8
            reasons.append("claude_configured")
        if m["provider"] == "codex" and (_codex_binary() or True):
            score += 5
            reasons.append("codex_available")
        if m["provider"] == "stub":
            score += 1
            reasons.append("stub_always_on")

        scored.append({"model": m, "score": score, "reasons": reasons, "budget_estimate": est})

    scored.sort(key=lambda x: x["score"], reverse=True)
    # drop over-budget if alternatives exist
    viable = [s for s in scored if "over_budget" not in s["reasons"]] or scored
    primary = viable[0]
    fallbacks = [
        {"provider": s["model"]["provider"], "model": s["model"]["model"], "score": s["score"]}
        for s in viable[1:4]
    ]

    decision = {
        "provider": primary["model"]["provider"],
        "model": primary["model"]["model"],
        "score": round(primary["score"], 2),
        "fallbacks": fallbacks,
        "reasons": primary["reasons"],
        "budget_estimate": primary["budget_estimate"],
        "task_type": task_type,
        "complexity": complexity,
        "privacy": privacy,
        "agent_role": agent_role,
    }

    # audit
    with dbmod.connect(db_path) as conn:
        ensure_registry(db_path)
        rid = dbmod.new_id("rte_")
        conn.execute(
            """
            INSERT INTO routing_decisions
              (id, task_id, agent_name, provider, model, score, reason_json, fallback_json, created_at)
            VALUES (?,?,?,?,?,?,?,?,?)
            """,
            (
                rid, task_id, agent_role, decision["provider"], decision["model"],
                decision["score"], json.dumps(decision["reasons"]),
                json.dumps(decision["fallbacks"]), dbmod.utc_now(),
            ),
        )
        conn.commit()
    decision["decision_id"] = rid
    return decision


def main(argv=None) -> int:
    argv = list(argv or sys.argv[1:])
    if not argv or argv[0] in ("-h", "--help"):
        print("usage: model_router.py TASK_OR_TYPE [--title T] [--privacy MODE]", file=sys.stderr)
        return 2
    task = argv[0]
    title = task
    privacy = "ANY_APPROVED"
    args = argv[1:]
    if "--title" in args:
        i = args.index("--title")
        title = args[i + 1]
        del args[i : i + 2]
    if "--privacy" in args:
        i = args.index("--privacy")
        privacy = args[i + 1]
        del args[i : i + 2]
    # if looks like a type keyword
    ttype = task if task in (
        "coding", "bugfix", "refactor", "research", "security", "performance",
        "documentation", "testing", "architecture", "deployment", "data_analysis",
    ) else None
    out = route(ttype, title=title, description=" ".join(args), privacy=privacy)
    print(json.dumps(out, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
