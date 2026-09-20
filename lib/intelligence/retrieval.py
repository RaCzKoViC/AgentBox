#!/usr/bin/env python3
"""Hybrid retrieval — semantic code + vector memory + keyword."""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any, Optional

_HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(_HERE.parent))

from intelligence.embeddings import embed  # noqa: E402
from intelligence import vector_store as vstore  # noqa: E402
from intelligence.reranker import rerank, keyword_overlap  # noqa: E402
from storage import db as dbmod  # noqa: E402


def _keyword_chunks(query: str, project_id: Optional[str], limit: int, db_path: Optional[str]) -> list[dict]:
    with dbmod.connect(db_path) as conn:
        try:
            if project_id:
                rows = conn.execute(
                    "SELECT * FROM semantic_chunks WHERE project_id = ? ORDER BY updated_at DESC LIMIT 200",
                    (project_id,),
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM semantic_chunks ORDER BY updated_at DESC LIMIT 200"
                ).fetchall()
        except Exception:
            return []
    hits = []
    for r in rows:
        text = r["content"] or ""
        ov = keyword_overlap(query, f"{r['file_path']} {r['symbol'] or ''} {text}")
        if ov <= 0:
            continue
        hits.append({
            "id": r["id"],
            "score": ov * 0.6,
            "source": "keyword",
            "file_path": r["file_path"],
            "symbol": r["symbol"],
            "symbol_type": r["symbol_type"],
            "text_preview": text[:400],
            "content": text[:2000],
            "project_id": r["project_id"],
            "start_line": r["start_line"],
            "end_line": r["end_line"],
        })
    hits.sort(key=lambda x: x["score"], reverse=True)
    return hits[:limit]


def retrieve_context(
    query: str,
    *,
    project_id: Optional[str] = None,
    task_id: Optional[str] = None,
    agent_name: Optional[str] = None,
    top_k: int = 20,
    filters: Optional[dict] = None,
    sources: Optional[list[str]] = None,
    db_path: Optional[str] = None,
) -> dict[str, Any]:
    sources = sources or ["code", "memory"]
    filters = filters or {}
    candidates: list[dict] = []

    if "code" in sources:
        qvec = embed(query)
        vec_hits = vstore.query(
            qvec,
            top_k=max(top_k * 3, 30),
            namespace="code",
            project_id=project_id,
            ref_type="chunk",
            db_path=db_path,
        )
        # enrich from chunks table
        chunk_ids = [h["ref_id"] for h in vec_hits if h.get("ref_id")]
        chunk_map: dict[str, dict] = {}
        if chunk_ids:
            with dbmod.connect(db_path) as conn:
                placeholders = ",".join("?" * len(chunk_ids))
                try:
                    rows = conn.execute(
                        f"SELECT * FROM semantic_chunks WHERE id IN ({placeholders})",
                        chunk_ids,
                    ).fetchall()
                    chunk_map = {r["id"]: dict(r) for r in rows}
                except Exception:
                    chunk_map = {}
        for h in vec_hits:
            ch = chunk_map.get(h.get("ref_id") or "", {})
            meta = h.get("meta") or {}
            candidates.append({
                "id": h["id"],
                "score": h["score"],
                "source": "semantic",
                "file_path": ch.get("file_path") or meta.get("file_path"),
                "symbol": ch.get("symbol") or meta.get("symbol"),
                "symbol_type": ch.get("symbol_type") or meta.get("symbol_type"),
                "text_preview": h.get("text_preview") or (ch.get("content") or "")[:400],
                "content": (ch.get("content") or h.get("text_preview") or "")[:2000],
                "project_id": h.get("project_id") or project_id,
                "start_line": ch.get("start_line"),
                "end_line": ch.get("end_line"),
                "importance": 0.55,
                "confidence": 0.7,
            })
        candidates.extend(_keyword_chunks(query, project_id, top_k * 2, db_path))

    if "memory" in sources:
        mem_hits = vstore.query(
            embed(query),
            top_k=max(top_k, 10),
            namespace="memory",
            project_id=project_id,
            db_path=db_path,
        )
        for h in mem_hits:
            meta = h.get("meta") or {}
            candidates.append({
                "id": h["id"],
                "score": h["score"],
                "source": "memory",
                "memory_type": meta.get("memory_type"),
                "scope": meta.get("scope_type"),
                "text_preview": h.get("text_preview"),
                "content": h.get("text_preview"),
                "importance": float(meta.get("importance") or 0.5),
                "confidence": float(meta.get("confidence") or 0.5),
                "project_id": h.get("project_id"),
            })

    # dedupe by id / file+symbol
    seen = set()
    uniq = []
    for c in candidates:
        key = c.get("id") or f"{c.get('file_path')}:{c.get('symbol')}:{c.get('text_preview','')[:40]}"
        if key in seen:
            continue
        seen.add(key)
        uniq.append(c)

    ranked = rerank(query, uniq, top_k=top_k)
    return {
        "query": query,
        "project_id": project_id,
        "task_id": task_id,
        "agent_name": agent_name,
        "hits": ranked,
        "count": len(ranked),
    }


def main(argv=None) -> int:
    argv = list(argv or sys.argv[1:])
    if not argv:
        print("usage: retrieval.py QUERY [--project ID] [--top-k N]", file=sys.stderr)
        return 2
    top_k = 10
    project_id = None
    args = list(argv)
    if "--project" in args:
        i = args.index("--project")
        project_id = args[i + 1]
        del args[i : i + 2]
    if "--top-k" in args:
        i = args.index("--top-k")
        top_k = int(args[i + 1])
        del args[i : i + 2]
    q = " ".join(args)
    print(json.dumps(retrieve_context(q, project_id=project_id, top_k=top_k), indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
