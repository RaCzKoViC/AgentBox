#!/usr/bin/env python3
"""SQLite vector store — float blobs + cosine (pure Python / optional numpy)."""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any, Optional

_HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(_HERE.parent))

from intelligence.embeddings import (  # noqa: E402
    EMBEDDING_DIM,
    cosine,
    embed,
    pack_vector,
    unpack_vector,
)
from storage import db as dbmod  # noqa: E402


def ensure_tables(conn) -> None:
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS vector_embeddings (
            id TEXT PRIMARY KEY,
            namespace TEXT NOT NULL DEFAULT 'default',
            ref_type TEXT NOT NULL,
            ref_id TEXT NOT NULL,
            project_id TEXT,
            embedding_model TEXT NOT NULL,
            embedding_version TEXT,
            dim INTEGER NOT NULL,
            vector_blob BLOB NOT NULL,
            text_preview TEXT,
            meta_json TEXT NOT NULL DEFAULT '{}',
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        CREATE INDEX IF NOT EXISTS idx_vec_ns ON vector_embeddings(namespace);
        CREATE INDEX IF NOT EXISTS idx_vec_ref ON vector_embeddings(ref_type, ref_id);
        CREATE INDEX IF NOT EXISTS idx_vec_project ON vector_embeddings(project_id);
        """
    )


def upsert(
    vector_id: str,
    vector: list[float],
    *,
    namespace: str = "default",
    ref_type: str = "chunk",
    ref_id: str = "",
    project_id: Optional[str] = None,
    embedding_model: str = "local-hash-bow",
    embedding_version: str = "1",
    text_preview: str = "",
    meta: Optional[dict] = None,
    db_path: Optional[str] = None,
) -> dict:
    blob = pack_vector(vector)
    now = dbmod.utc_now()
    with dbmod.connect(db_path) as conn:
        ensure_tables(conn)
        conn.execute(
            """
            INSERT INTO vector_embeddings
              (id, namespace, ref_type, ref_id, project_id, embedding_model, embedding_version,
               dim, vector_blob, text_preview, meta_json, created_at, updated_at)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)
            ON CONFLICT(id) DO UPDATE SET
              namespace=excluded.namespace,
              ref_type=excluded.ref_type,
              ref_id=excluded.ref_id,
              project_id=excluded.project_id,
              embedding_model=excluded.embedding_model,
              embedding_version=excluded.embedding_version,
              dim=excluded.dim,
              vector_blob=excluded.vector_blob,
              text_preview=excluded.text_preview,
              meta_json=excluded.meta_json,
              updated_at=excluded.updated_at
            """,
            (
                vector_id,
                namespace,
                ref_type,
                ref_id,
                project_id,
                embedding_model,
                embedding_version,
                len(vector),
                blob,
                (text_preview or "")[:500],
                json.dumps(meta or {}),
                now,
                now,
            ),
        )
        conn.commit()
    return {"id": vector_id, "dim": len(vector), "namespace": namespace}


def delete(vector_id: str, db_path: Optional[str] = None) -> bool:
    with dbmod.connect(db_path) as conn:
        ensure_tables(conn)
        cur = conn.execute("DELETE FROM vector_embeddings WHERE id = ?", (vector_id,))
        conn.commit()
        return cur.rowcount > 0


def delete_by_ref(ref_type: str, ref_id: str, db_path: Optional[str] = None) -> int:
    with dbmod.connect(db_path) as conn:
        ensure_tables(conn)
        cur = conn.execute(
            "DELETE FROM vector_embeddings WHERE ref_type = ? AND ref_id = ?",
            (ref_type, ref_id),
        )
        conn.commit()
        return cur.rowcount


def query(
    query_vec: list[float],
    *,
    top_k: int = 10,
    namespace: Optional[str] = None,
    project_id: Optional[str] = None,
    ref_type: Optional[str] = None,
    db_path: Optional[str] = None,
) -> list[dict[str, Any]]:
    """Brute-force cosine over SQLite blobs (fine for local projects)."""
    clauses = ["1=1"]
    args: list[Any] = []
    if namespace:
        clauses.append("namespace = ?")
        args.append(namespace)
    if project_id:
        clauses.append("project_id = ?")
        args.append(project_id)
    if ref_type:
        clauses.append("ref_type = ?")
        args.append(ref_type)
    sql = f"SELECT * FROM vector_embeddings WHERE {' AND '.join(clauses)}"
    with dbmod.connect(db_path) as conn:
        ensure_tables(conn)
        rows = conn.execute(sql, args).fetchall()
    scored: list[dict[str, Any]] = []
    for r in rows:
        vec = unpack_vector(r["vector_blob"])
        score = cosine(query_vec, vec)
        scored.append(
            {
                "id": r["id"],
                "score": score,
                "namespace": r["namespace"],
                "ref_type": r["ref_type"],
                "ref_id": r["ref_id"],
                "project_id": r["project_id"],
                "text_preview": r["text_preview"],
                "meta": json.loads(r["meta_json"] or "{}"),
                "embedding_model": r["embedding_model"],
            }
        )
    scored.sort(key=lambda x: x["score"], reverse=True)
    return scored[: max(1, int(top_k))]


def query_text(
    text: str,
    *,
    top_k: int = 10,
    namespace: Optional[str] = None,
    project_id: Optional[str] = None,
    ref_type: Optional[str] = None,
    db_path: Optional[str] = None,
) -> list[dict[str, Any]]:
    return query(
        embed(text),
        top_k=top_k,
        namespace=namespace,
        project_id=project_id,
        ref_type=ref_type,
        db_path=db_path,
    )


def stats(db_path: Optional[str] = None) -> dict[str, Any]:
    with dbmod.connect(db_path) as conn:
        ensure_tables(conn)
        total = conn.execute("SELECT COUNT(*) FROM vector_embeddings").fetchone()[0]
        by_ns = {
            r[0]: r[1]
            for r in conn.execute(
                "SELECT namespace, COUNT(*) FROM vector_embeddings GROUP BY namespace"
            ).fetchall()
        }
        by_proj = {
            (r[0] or ""): r[1]
            for r in conn.execute(
                "SELECT project_id, COUNT(*) FROM vector_embeddings GROUP BY project_id"
            ).fetchall()
        }
    return {
        "total": total,
        "by_namespace": by_ns,
        "by_project": by_proj,
        "dim": EMBEDDING_DIM,
        "backend": "sqlite+float_blobs",
    }


def rebuild(project_id: Optional[str] = None, db_path: Optional[str] = None) -> dict:
    """Delete vectors (optionally per project). Source of truth is chunks/files."""
    with dbmod.connect(db_path) as conn:
        ensure_tables(conn)
        if project_id:
            cur = conn.execute(
                "DELETE FROM vector_embeddings WHERE project_id = ?", (project_id,)
            )
        else:
            cur = conn.execute("DELETE FROM vector_embeddings")
        conn.commit()
        n = cur.rowcount
    return {"deleted": n, "project_id": project_id}


def main(argv=None) -> int:
    argv = list(argv or sys.argv[1:])
    if not argv or argv[0] in ("-h", "--help"):
        print("usage: vector_store.py stats|query TEXT [--top-k N]", file=sys.stderr)
        return 2
    if argv[0] == "stats":
        print(json.dumps(stats(), indent=2))
        return 0
    if argv[0] == "query":
        top_k = 10
        args = argv[1:]
        if "--top-k" in args:
            i = args.index("--top-k")
            top_k = int(args[i + 1])
            args = args[:i] + args[i + 2 :]
        q = " ".join(args)
        print(json.dumps(query_text(q, top_k=top_k), indent=2, default=str))
        return 0
    print("unknown", file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
