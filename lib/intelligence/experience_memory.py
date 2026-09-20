#!/usr/bin/env python3
"""Experience memory — record what worked/failed after tasks."""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any, Optional

_HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(_HERE.parent))

from intelligence.embeddings import embed, pack_vector  # noqa: E402
from intelligence import EMBEDDING_MODEL, EMBEDDING_VERSION  # noqa: E402
from storage import db as dbmod  # noqa: E402


def ensure_schema(conn) -> None:
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS experience (
            id TEXT PRIMARY KEY,
            task_id TEXT,
            task_type TEXT,
            provider TEXT,
            model TEXT,
            agent TEXT,
            outcome TEXT,
            runtime_seconds REAL,
            cost REAL,
            retries INTEGER DEFAULT 0,
            review_pass INTEGER,
            notes TEXT,
            meta_json TEXT DEFAULT '{}',
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS vector_memories (
            id TEXT PRIMARY KEY,
            scope_type TEXT NOT NULL,
            scope_id TEXT,
            memory_type TEXT NOT NULL,
            content TEXT NOT NULL,
            summary TEXT,
            vector_id TEXT,
            importance REAL NOT NULL DEFAULT 0.5,
            confidence REAL NOT NULL DEFAULT 0.5,
            provenance_json TEXT,
            usage_count INTEGER NOT NULL DEFAULT 0,
            last_used_at TEXT,
            pinned INTEGER NOT NULL DEFAULT 0,
            shareable INTEGER NOT NULL DEFAULT 0,
            project_id TEXT,
            content_hash TEXT,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        CREATE INDEX IF NOT EXISTS idx_experience_type ON experience(task_type);
        CREATE INDEX IF NOT EXISTS idx_vmem_scope ON vector_memories(scope_type, scope_id);
        CREATE INDEX IF NOT EXISTS idx_vmem_hash ON vector_memories(content_hash);
        """
    )


def record_experience(
    *,
    task_id: Optional[str] = None,
    task_type: str = "coding",
    provider: str = "stub",
    model: str = "default",
    agent: str = "coder",
    outcome: str = "success",
    runtime_seconds: float = 0.0,
    cost: float = 0.0,
    retries: int = 0,
    review_pass: Optional[bool] = None,
    notes: str = "",
    meta: Optional[dict] = None,
    db_path: Optional[str] = None,
) -> dict:
    eid = dbmod.new_id("exp_")
    with dbmod.connect(db_path) as conn:
        ensure_schema(conn)
        conn.execute(
            """
            INSERT INTO experience
              (id, task_id, task_type, provider, model, agent, outcome,
               runtime_seconds, cost, retries, review_pass, notes, meta_json, created_at)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """,
            (
                eid, task_id, task_type, provider, model, agent, outcome,
                runtime_seconds, cost, retries,
                None if review_pass is None else (1 if review_pass else 0),
                notes, json.dumps(meta or {}), dbmod.utc_now(),
            ),
        )
        conn.commit()
    return {"id": eid, "outcome": outcome, "provider": provider, "model": model}


def write_memory(
    content: str,
    *,
    scope_type: str = "project",
    scope_id: str = "",
    memory_type: str = "lesson",
    importance: float = 0.6,
    confidence: float = 0.7,
    provenance: Optional[dict] = None,
    project_id: Optional[str] = None,
    pinned: bool = False,
    shareable: bool = False,
    db_path: Optional[str] = None,
) -> dict:
    """Write vector memory with provenance + dedup."""
    if not provenance:
        raise ValueError("provenance required")
    import hashlib

    chash = hashlib.sha256(content.encode("utf-8")).hexdigest()
    with dbmod.connect(db_path) as conn:
        ensure_schema(conn)
        # exact hash dedup in same scope
        row = conn.execute(
            """
            SELECT id, usage_count, confidence FROM vector_memories
            WHERE content_hash = ? AND scope_type = ? AND IFNULL(scope_id,'') = ?
            """,
            (chash, scope_type, scope_id or ""),
        ).fetchone()
        if row:
            conn.execute(
                """
                UPDATE vector_memories SET usage_count = usage_count + 1,
                  confidence = MIN(1.0, confidence + 0.05),
                  last_used_at = ?
                WHERE id = ?
                """,
                (dbmod.utc_now(), row["id"]),
            )
            conn.commit()
            return {"id": row["id"], "deduplicated": True, "usage_count": row["usage_count"] + 1}

        mid = dbmod.new_id("vm_")
        vid = f"vec_{mid}"
        vec = embed(content)
        from intelligence.vector_store import ensure_tables

        ensure_tables(conn)
        now = dbmod.utc_now()
        conn.execute(
            """
            INSERT INTO vector_memories
              (id, scope_type, scope_id, memory_type, content, summary, vector_id,
               importance, confidence, provenance_json, usage_count, last_used_at,
               pinned, shareable, project_id, content_hash, created_at)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """,
            (
                mid, scope_type, scope_id, memory_type, content, content[:200], vid,
                importance, confidence, json.dumps(provenance), 0, now,
                1 if pinned else 0, 1 if shareable else 0, project_id, chash, now,
            ),
        )
        conn.execute(
            """
            INSERT INTO vector_embeddings
              (id, namespace, ref_type, ref_id, project_id, embedding_model,
               embedding_version, dim, vector_blob, text_preview, meta_json,
               created_at, updated_at)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)
            """,
            (
                vid, "memory", "memory", mid, project_id, EMBEDDING_MODEL, EMBEDDING_VERSION,
                len(vec), pack_vector(vec), content[:400],
                json.dumps({
                    "memory_type": memory_type,
                    "scope_type": scope_type,
                    "importance": importance,
                    "confidence": confidence,
                }),
                now, now,
            ),
        )
        conn.commit()
    return {"id": mid, "vector_id": vid, "deduplicated": False}


def list_memories(
    *,
    scope_type: Optional[str] = None,
    limit: int = 50,
    db_path: Optional[str] = None,
) -> list[dict]:
    with dbmod.connect(db_path) as conn:
        ensure_schema(conn)
        if scope_type:
            rows = conn.execute(
                "SELECT * FROM vector_memories WHERE scope_type = ? ORDER BY created_at DESC LIMIT ?",
                (scope_type, limit),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM vector_memories ORDER BY created_at DESC LIMIT ?",
                (limit,),
            ).fetchall()
    return [dict(r) for r in rows]


def list_experience(limit: int = 50, db_path: Optional[str] = None) -> list[dict]:
    with dbmod.connect(db_path) as conn:
        ensure_schema(conn)
        rows = conn.execute(
            "SELECT * FROM experience ORDER BY created_at DESC LIMIT ?", (limit,)
        ).fetchall()
    return [dict(r) for r in rows]


def main(argv=None) -> int:
    argv = list(argv or sys.argv[1:])
    if not argv:
        print("usage: experience_memory.py list|write CONTENT --provenance JSON", file=sys.stderr)
        return 2
    if argv[0] == "list":
        print(json.dumps(list_memories(), indent=2, default=str))
        return 0
    if argv[0] == "write":
        content = " ".join(argv[1:])
        print(json.dumps(
            write_memory(content, provenance={"manual": True, "source": "cli"}),
            indent=2,
        ))
        return 0
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
