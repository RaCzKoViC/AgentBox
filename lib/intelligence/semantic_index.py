#!/usr/bin/env python3
"""Semantic project index — scan, chunk, embed, store (local-first)."""
from __future__ import annotations

import hashlib
import json
import os
import re
import sys
from pathlib import Path
from typing import Any, Optional

_HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(_HERE.parent))

from intelligence import EMBEDDING_MODEL, EMBEDDING_VERSION  # noqa: E402
from intelligence.embeddings import embed, pack_vector  # noqa: E402
from intelligence import vector_store as vstore  # noqa: E402
from storage import db as dbmod  # noqa: E402

INDEX_EXTS = {
    ".py", ".rs", ".ts", ".tsx", ".js", ".jsx", ".go", ".c", ".h", ".cpp", ".hpp",
    ".java", ".kt", ".swift", ".sh", ".md", ".toml", ".yaml", ".yml", ".json",
    ".sql", ".html", ".css", ".txt",
}
SKIP_DIRS = {
    ".git", "node_modules", "target", "dist", "build", "__pycache__", "venv",
    ".venv", ".tox", ".mypy_cache", ".pytest_cache", "vendor", ".idea", ".vscode",
}
SECRET_NAMES = {
    ".env", ".env.local", ".env.production", "credentials.json", "secrets.yaml",
    "id_rsa", "id_ed25519", ".netrc",
}
SECRET_PATTERNS = re.compile(
    r"(api[_-]?key|secret|password|token|private[_-]?key)\s*[=:]\s*['\"]?[^\s'\"]{8,}",
    re.I,
)
MAX_FILE_BYTES = 400_000


def ensure_schema(conn) -> None:
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS semantic_indexes (
            id TEXT PRIMARY KEY,
            project_id TEXT NOT NULL,
            embedding_model TEXT NOT NULL,
            embedding_version TEXT,
            index_version INTEGER NOT NULL DEFAULT 1,
            status TEXT NOT NULL DEFAULT 'new',
            last_commit TEXT,
            files_count INTEGER NOT NULL DEFAULT 0,
            chunks_count INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS semantic_chunks (
            id TEXT PRIMARY KEY,
            project_id TEXT NOT NULL,
            file_path TEXT NOT NULL,
            symbol TEXT,
            symbol_type TEXT,
            language TEXT,
            start_line INTEGER,
            end_line INTEGER,
            content_hash TEXT NOT NULL,
            content TEXT,
            vector_id TEXT,
            metadata_json TEXT,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        CREATE INDEX IF NOT EXISTS idx_sem_chunks_project ON semantic_chunks(project_id);
        CREATE INDEX IF NOT EXISTS idx_sem_chunks_file ON semantic_chunks(project_id, file_path);
        CREATE INDEX IF NOT EXISTS idx_sem_chunks_hash ON semantic_chunks(content_hash);
        CREATE INDEX IF NOT EXISTS idx_sem_indexes_project ON semantic_indexes(project_id);
        """
    )
    vstore.ensure_tables(conn)


def project_id_from_path(path: str | Path) -> str:
    p = Path(path).resolve()
    return hashlib.sha1(str(p).encode()).hexdigest()[:12]


def _looks_secret(path: Path, text: str) -> bool:
    name = path.name.lower()
    if name in SECRET_NAMES or name.endswith(".pem") or name.endswith(".key"):
        return True
    if name.startswith(".env"):
        return True
    # sample first 4k only
    sample = text[:4000]
    if SECRET_PATTERNS.search(sample) and ("BEGIN PRIVATE KEY" in sample or "AKIA" in sample):
        return True
    if "BEGIN PRIVATE KEY" in sample or "BEGIN RSA PRIVATE KEY" in sample:
        return True
    return False


def _lang_for(path: Path) -> str:
    return path.suffix.lstrip(".").lower() or "txt"


def _chunk_python(text: str, path: str) -> list[dict]:
    lines = text.splitlines()
    chunks: list[dict] = []
    # module docstring / header
    if lines:
        header_end = min(40, len(lines))
        chunks.append({
            "symbol": Path(path).stem,
            "symbol_type": "module",
            "start_line": 1,
            "end_line": header_end,
            "content": "\n".join(lines[:header_end]),
        })
    # def/class blocks
    starts: list[tuple[int, str, str]] = []
    for i, line in enumerate(lines):
        m = re.match(r"^(def|class|async def)\s+([A-Za-z_][A-Za-z0-9_]*)", line)
        if m:
            starts.append((i, m.group(2), "function" if "def" in m.group(1) else "class"))
    for idx, (start, sym, stype) in enumerate(starts):
        end = starts[idx + 1][0] if idx + 1 < len(starts) else len(lines)
        # expand end by indentation heuristic — already using next def
        body = "\n".join(lines[start:end])
        if len(body.strip()) < 8:
            continue
        chunks.append({
            "symbol": sym,
            "symbol_type": stype,
            "start_line": start + 1,
            "end_line": end,
            "content": body[:8000],
        })
    if not starts and len(lines) > 40:
        # sliding windows
        for i in range(0, len(lines), 80):
            part = "\n".join(lines[i : i + 80])
            chunks.append({
                "symbol": f"block_{i+1}",
                "symbol_type": "section",
                "start_line": i + 1,
                "end_line": min(i + 80, len(lines)),
                "content": part,
            })
    return chunks


def _chunk_markdown(text: str, path: str) -> list[dict]:
    parts = re.split(r"(?m)^(#{1,3}\s+.+)$", text)
    chunks: list[dict] = []
    if len(parts) == 1:
        for i in range(0, len(text), 2000):
            chunks.append({
                "symbol": Path(path).stem,
                "symbol_type": "doc",
                "start_line": 1,
                "end_line": text.count("\n") + 1,
                "content": text[i : i + 2000],
            })
        return chunks
    heading = Path(path).stem
    buf = ""
    line_est = 1
    for p in parts:
        if re.match(r"^#{1,3}\s+", p or ""):
            if buf.strip():
                chunks.append({
                    "symbol": heading[:80],
                    "symbol_type": "heading",
                    "start_line": line_est,
                    "end_line": line_est + buf.count("\n"),
                    "content": buf[:6000],
                })
            heading = p.lstrip("#").strip()
            buf = p + "\n"
        else:
            buf += p or ""
    if buf.strip():
        chunks.append({
            "symbol": heading[:80],
            "symbol_type": "heading",
            "start_line": line_est,
            "end_line": line_est + buf.count("\n"),
            "content": buf[:6000],
        })
    return chunks


def _chunk_generic(text: str, path: str) -> list[dict]:
    lines = text.splitlines()
    chunks = []
    size = 100
    for i in range(0, max(1, len(lines)), size):
        part = "\n".join(lines[i : i + size])
        if not part.strip():
            continue
        chunks.append({
            "symbol": f"{Path(path).name}:{i+1}",
            "symbol_type": "section",
            "start_line": i + 1,
            "end_line": min(i + size, len(lines)),
            "content": part[:8000],
        })
    return chunks


def chunk_file(path: Path, text: str) -> list[dict]:
    lang = _lang_for(path)
    if lang == "py":
        return _chunk_python(text, str(path))
    if lang == "md":
        return _chunk_markdown(text, str(path))
    return _chunk_generic(text, str(path))


def scan_project(root: Path) -> list[Path]:
    files: list[Path] = []
    root = root.resolve()
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS and not d.startswith(".")]
        for fn in filenames:
            p = Path(dirpath) / fn
            if p.suffix.lower() not in INDEX_EXTS:
                continue
            if fn in SECRET_NAMES or fn.startswith(".env"):
                continue
            try:
                if p.stat().st_size > MAX_FILE_BYTES:
                    continue
            except OSError:
                continue
            files.append(p)
    return files


def _content_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8", errors="ignore")).hexdigest()


def index_project(
    project_path: str | Path,
    *,
    project_id: Optional[str] = None,
    db_path: Optional[str] = None,
    force: bool = False,
) -> dict[str, Any]:
    root = Path(project_path).resolve()
    if not root.is_dir():
        raise FileNotFoundError(f"project not found: {root}")
    pid = project_id or project_id_from_path(root)
    files = scan_project(root)
    now = dbmod.utc_now()
    idx_id = f"idx_{pid}"
    chunks_written = 0
    files_indexed = 0
    skipped_secret = 0
    reused = 0

    with dbmod.connect(db_path) as conn:
        ensure_schema(conn)
        conn.execute(
            """
            INSERT INTO semantic_indexes
              (id, project_id, embedding_model, embedding_version, index_version, status,
               files_count, chunks_count, created_at, updated_at)
            VALUES (?,?,?,?,?,?,?,?,?,?)
            ON CONFLICT(id) DO UPDATE SET
              status='indexing', updated_at=excluded.updated_at,
              embedding_model=excluded.embedding_model
            """,
            (idx_id, pid, EMBEDDING_MODEL, EMBEDDING_VERSION, 1, "indexing", 0, 0, now, now),
        )
        if force:
            old = conn.execute(
                "SELECT id, vector_id FROM semantic_chunks WHERE project_id = ?", (pid,)
            ).fetchall()
            for r in old:
                if r["vector_id"]:
                    conn.execute("DELETE FROM vector_embeddings WHERE id = ?", (r["vector_id"],))
            conn.execute("DELETE FROM semantic_chunks WHERE project_id = ?", (pid,))

        existing = {
            (r["file_path"], r["content_hash"]): r["id"]
            for r in conn.execute(
                "SELECT id, file_path, content_hash FROM semantic_chunks WHERE project_id = ?",
                (pid,),
            ).fetchall()
        }

        for fp in files:
            try:
                text = fp.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            if _looks_secret(fp, text):
                skipped_secret += 1
                continue
            rel = str(fp.relative_to(root))
            lang = _lang_for(fp)
            file_chunks = chunk_file(fp, text)
            files_indexed += 1
            for ch in file_chunks:
                content = ch["content"]
                chash = _content_hash(content)
                key = (rel, chash)
                if key in existing and not force:
                    reused += 1
                    continue
                cid = dbmod.new_id("chk_")
                vid = f"vec_{cid}"
                vec = embed(f"{rel} {ch.get('symbol','')}\n{content}")
                meta = {
                    "file_path": rel,
                    "symbol": ch.get("symbol"),
                    "symbol_type": ch.get("symbol_type"),
                    "language": lang,
                    "start_line": ch.get("start_line"),
                    "end_line": ch.get("end_line"),
                }
                conn.execute(
                    """
                    INSERT INTO semantic_chunks
                      (id, project_id, file_path, symbol, symbol_type, language,
                       start_line, end_line, content_hash, content, vector_id,
                       metadata_json, created_at, updated_at)
                    VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                    """,
                    (
                        cid, pid, rel, ch.get("symbol"), ch.get("symbol_type"), lang,
                        ch.get("start_line"), ch.get("end_line"), chash, content[:12000],
                        vid, json.dumps(meta), now, now,
                    ),
                )
                conn.execute(
                    """
                    INSERT INTO vector_embeddings
                      (id, namespace, ref_type, ref_id, project_id, embedding_model,
                       embedding_version, dim, vector_blob, text_preview, meta_json,
                       created_at, updated_at)
                    VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)
                    ON CONFLICT(id) DO UPDATE SET
                      vector_blob=excluded.vector_blob, updated_at=excluded.updated_at,
                      text_preview=excluded.text_preview, meta_json=excluded.meta_json
                    """,
                    (
                        vid, "code", "chunk", cid, pid, EMBEDDING_MODEL, EMBEDDING_VERSION,
                        len(vec), pack_vector(vec), content[:400], json.dumps(meta), now, now,
                    ),
                )
                chunks_written += 1

        total_chunks = conn.execute(
            "SELECT COUNT(*) FROM semantic_chunks WHERE project_id = ?", (pid,)
        ).fetchone()[0]
        conn.execute(
            """
            UPDATE semantic_indexes SET status='ready', files_count=?, chunks_count=?,
              updated_at=? WHERE id=?
            """,
            (files_indexed, total_chunks, now, idx_id),
        )
        conn.commit()

    return {
        "ok": True,
        "project_id": pid,
        "project_path": str(root),
        "index_id": idx_id,
        "files": files_indexed,
        "chunks_written": chunks_written,
        "chunks_total": total_chunks,
        "reused": reused,
        "skipped_secret": skipped_secret,
        "embedding_model": EMBEDDING_MODEL,
        "status": "ready",
    }


def status(project: Optional[str] = None, db_path: Optional[str] = None) -> dict:
    with dbmod.connect(db_path) as conn:
        ensure_schema(conn)
        if project:
            # accept path or id
            p = Path(project)
            pid = project_id_from_path(p) if p.exists() else project
            rows = conn.execute(
                "SELECT * FROM semantic_indexes WHERE project_id = ?", (pid,)
            ).fetchall()
        else:
            rows = conn.execute("SELECT * FROM semantic_indexes ORDER BY updated_at DESC").fetchall()
        indexes = [dict(r) for r in rows]
        chunks = conn.execute("SELECT COUNT(*) FROM semantic_chunks").fetchone()[0]
    vs = vstore.stats(db_path=db_path)
    return {
        "indexes": indexes,
        "chunks_total": chunks,
        "vector_store": vs,
        "embedding": {"model": EMBEDDING_MODEL, "version": EMBEDDING_VERSION},
    }


def search(
    query: str,
    *,
    project_id: Optional[str] = None,
    top_k: int = 10,
    db_path: Optional[str] = None,
) -> list[dict]:
    from intelligence.retrieval import retrieve_context

    pack = retrieve_context(
        query, project_id=project_id, top_k=top_k, db_path=db_path, sources=["code"]
    )
    return pack.get("hits") or []


def main(argv=None) -> int:
    argv = list(argv or sys.argv[1:])
    if not argv or argv[0] in ("-h", "--help"):
        print("usage: semantic_index.py index PATH | status [PROJECT] | search Q [--project ID]", file=sys.stderr)
        return 2
    cmd = argv[0]
    if cmd == "index":
        force = "--force" in argv
        path = next((a for a in argv[1:] if not a.startswith("-")), None)
        if not path:
            print("need PATH", file=sys.stderr)
            return 2
        print(json.dumps(index_project(path, force=force), indent=2))
        return 0
    if cmd == "status":
        proj = argv[1] if len(argv) > 1 else None
        print(json.dumps(status(proj), indent=2, default=str))
        return 0
    if cmd == "search":
        top_k = 10
        args = argv[1:]
        project_id = None
        if "--project" in args:
            i = args.index("--project")
            project_id = args[i + 1]
            args = args[:i] + args[i + 2 :]
        if "--top-k" in args:
            i = args.index("--top-k")
            top_k = int(args[i + 1])
            args = args[:i] + args[i + 2 :]
        q = " ".join(args)
        print(json.dumps(search(q, project_id=project_id, top_k=top_k), indent=2, default=str))
        return 0
    print("unknown", file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
