#!/usr/bin/env python3
"""Local-first embeddings: hash bag-of-words (default), optional numpy / Ollama."""
from __future__ import annotations

import hashlib
import math
import os
import re
import struct
import urllib.error
import urllib.request
from typing import Optional

from intelligence import EMBEDDING_DIM, EMBEDDING_MODEL, EMBEDDING_VERSION

_TOKEN_RE = re.compile(r"[a-zA-Z_][a-zA-Z0-9_]{1,48}|[а-яА-ЯёЁąćęłńóśźżĄĆĘŁŃÓŚŹŻ]{2,32}|\d+")

_HAS_NUMPY = False
try:
    import numpy as np  # type: ignore

    _HAS_NUMPY = True
except ImportError:
    np = None  # type: ignore


def model_info() -> dict:
    provider = os.environ.get("AGENTBOX_EMBED_PROVIDER", "local")
    return {
        "id": EMBEDDING_MODEL,
        "provider": provider,
        "dimension": EMBEDDING_DIM,
        "version": EMBEDDING_VERSION,
        "local": True,
        "numpy": _HAS_NUMPY,
        "ollama_available": _ollama_available(),
    }


def _ollama_available() -> bool:
    base = os.environ.get("OLLAMA_HOST", "http://127.0.0.1:11434")
    try:
        req = urllib.request.Request(f"{base.rstrip('/')}/api/tags", method="GET")
        with urllib.request.urlopen(req, timeout=0.4) as resp:
            return resp.status == 200
    except Exception:
        return False


def tokenize(text: str) -> list[str]:
    if not text:
        return []
    return [t.lower() for t in _TOKEN_RE.findall(text)]


def _hash_bucket(token: str, dim: int) -> int:
    h = hashlib.blake2b(token.encode("utf-8", errors="ignore"), digest_size=8).digest()
    return int.from_bytes(h, "little") % dim


def _sign(token: str) -> float:
    h = hashlib.md5(token.encode("utf-8", errors="ignore")).digest()
    return 1.0 if (h[0] & 1) == 0 else -1.0


def embed_local(text: str, dim: int = EMBEDDING_DIM) -> list[float]:
    """Deterministic hashing trick + bag-of-words; L2-normalized."""
    vec = [0.0] * dim
    toks = tokenize(text)
    if not toks:
        # empty → tiny deterministic unit vector from content hash
        h = hashlib.sha256((text or "").encode("utf-8")).digest()
        idx = int.from_bytes(h[:4], "little") % dim
        vec[idx] = 1.0
        return vec
    for t in toks:
        i = _hash_bucket(t, dim)
        vec[i] += _sign(t)
    # mild TF scaling
    n = len(toks)
    if n > 1:
        scale = 1.0 / math.sqrt(n)
        vec = [v * scale for v in vec]
    return _l2_normalize(vec)


def _l2_normalize(vec: list[float]) -> list[float]:
    if _HAS_NUMPY:
        a = np.asarray(vec, dtype=np.float32)
        n = float(np.linalg.norm(a))
        if n < 1e-12:
            return vec
        return (a / n).tolist()
    s = math.sqrt(sum(v * v for v in vec))
    if s < 1e-12:
        return vec
    return [v / s for v in vec]


def embed_ollama(text: str, model: Optional[str] = None) -> Optional[list[float]]:
    base = os.environ.get("OLLAMA_HOST", "http://127.0.0.1:11434")
    model = model or os.environ.get("OLLAMA_EMBED_MODEL", "nomic-embed-text")
    payload = json_dumps({"model": model, "prompt": text})
    try:
        req = urllib.request.Request(
            f"{base.rstrip('/')}/api/embeddings",
            data=payload.encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=5) as resp:
            data = json_loads(resp.read().decode("utf-8"))
        emb = data.get("embedding")
        if isinstance(emb, list) and emb:
            return _l2_normalize([float(x) for x in emb])
    except Exception:
        return None
    return None


def json_dumps(obj) -> str:
    import json

    return json.dumps(obj)


def json_loads(s: str):
    import json

    return json.loads(s)


def embed(text: str, model: Optional[str] = None) -> list[float]:
    """Public API — prefers local hash; optional Ollama if AGENTBOX_EMBED_PROVIDER=ollama."""
    provider = (model or os.environ.get("AGENTBOX_EMBED_PROVIDER") or "local").lower()
    if provider.startswith("ollama"):
        out = embed_ollama(text)
        if out:
            return out
    return embed_local(text)


def embed_batch(texts: list[str], model: Optional[str] = None) -> list[list[float]]:
    return [embed(t, model=model) for t in texts]


def pack_vector(vec: list[float]) -> bytes:
    return struct.pack(f"{len(vec)}f", *[float(x) for x in vec])


def unpack_vector(blob: bytes) -> list[float]:
    n = len(blob) // 4
    return list(struct.unpack(f"{n}f", blob))


def cosine(a: list[float], b: list[float]) -> float:
    if not a or not b:
        return 0.0
    n = min(len(a), len(b))
    if _HAS_NUMPY:
        aa = np.asarray(a[:n], dtype=np.float32)
        bb = np.asarray(b[:n], dtype=np.float32)
        denom = float(np.linalg.norm(aa) * np.linalg.norm(bb))
        if denom < 1e-12:
            return 0.0
        return float(np.dot(aa, bb) / denom)
    dot = sum(a[i] * b[i] for i in range(n))
    na = math.sqrt(sum(a[i] * a[i] for i in range(n)))
    nb = math.sqrt(sum(b[i] * b[i] for i in range(n)))
    if na < 1e-12 or nb < 1e-12:
        return 0.0
    return dot / (na * nb)


def main(argv=None) -> int:
    import json
    import sys

    argv = list(argv or sys.argv[1:])
    if not argv or argv[0] in ("-h", "--help"):
        print("usage: embeddings.py embed TEXT | info", file=sys.stderr)
        return 2
    if argv[0] == "info":
        print(json.dumps(model_info(), indent=2))
        return 0
    if argv[0] == "embed":
        text = " ".join(argv[1:]) or ""
        v = embed(text)
        print(json.dumps({"dim": len(v), "preview": v[:8], "model": EMBEDDING_MODEL}))
        return 0
    print("unknown", file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
