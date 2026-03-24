import hashlib
import math
import os
import struct
from typing import Dict, List, Optional, Tuple

from sqlalchemy import text
from sqlalchemy.engine import Engine

from app.db.session import get_engine

EMBED_MODEL_NAME = os.environ.get("EMBED_MODEL", "all-MiniLM-L6-v2")
EMBED_PROVIDER = os.environ.get("EMBED_PROVIDER", "auto").strip().lower()
FALLBACK_EMBED_DIM = int(os.environ.get("EMBED_DIM", "384"))

_embedder = None
_embedder_kind = None
_schema_ready = False


class _HashEmbedder:
    def __init__(self, dim: int):
        self.dim = dim

    def encode(self, texts: List[str], show_progress_bar: bool = False):  # noqa: ARG002
        return [_hash_embed(t, dim=self.dim) for t in texts]


def _hash_embed(text: str, dim: int) -> List[float]:
    if dim <= 0:
        raise ValueError("EMBED_DIM must be > 0")
    seed = hashlib.sha256(text.encode("utf-8")).digest()
    out: List[float] = []
    counter = 0
    while len(out) < dim:
        block = hashlib.sha256(seed + counter.to_bytes(4, "little")).digest()
        counter += 1
        for i in range(0, len(block), 4):
            if len(out) >= dim:
                break
            (val,) = struct.unpack("<i", block[i : i + 4])
            out.append(val / 2147483648.0)
    return out


def _get_embedder():
    global _embedder, _embedder_kind
    if _embedder is not None:
        return _embedder
    if EMBED_PROVIDER in {"hash", "fallback"}:
        _embedder = _HashEmbedder(dim=FALLBACK_EMBED_DIM)
        _embedder_kind = "hash-fallback"
        return _embedder
    try:
        from sentence_transformers import SentenceTransformer  # type: ignore

        _embedder = SentenceTransformer(EMBED_MODEL_NAME)
        _embedder_kind = "sentence-transformers"
        return _embedder
    except Exception:
        if EMBED_PROVIDER in {"sentence-transformers", "st"}:
            raise
    _embedder = _HashEmbedder(dim=FALLBACK_EMBED_DIM)
    _embedder_kind = "hash-fallback"
    return _embedder


def _ensure_schema(engine: Engine):
    global _schema_ready
    if _schema_ready:
        return
    if engine.dialect.name != "postgresql":
        _schema_ready = True
        return
    with engine.begin() as conn:
        try:
            conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
        except Exception as exc:
            raise RuntimeError(f"failed to enable pgvector extension: {exc}") from exc
        conn.execute(
            text(
                """
                CREATE TABLE IF NOT EXISTS vector_embeddings (
                    chunk_id TEXT PRIMARY KEY,
                    kb_id TEXT,
                    document_id TEXT,
                    metadata JSONB,
                    embedding VECTOR(:dim)
                )
                """
            ),
            {"dim": FALLBACK_EMBED_DIM},
        )
        conn.execute(text("CREATE INDEX IF NOT EXISTS vector_embeddings_kb_idx ON vector_embeddings (kb_id)"))
        conn.execute(text("CREATE INDEX IF NOT EXISTS vector_embeddings_doc_idx ON vector_embeddings (document_id)"))
    _schema_ready = True


def _build_filters(
    kb_id: Optional[str],
    kb_ids: Optional[List[str]],
    document_id: Optional[str],
    document_ids: Optional[List[str]],
) -> Tuple[str, Dict[str, object]]:
    clauses = []
    params: Dict[str, object] = {}
    if kb_id:
        clauses.append("ve.kb_id = :kb_id")
        params["kb_id"] = kb_id
    elif kb_ids:
        clauses.append("ve.kb_id = ANY(:kb_ids)")
        params["kb_ids"] = kb_ids
    if document_id:
        clauses.append("ve.document_id = :document_id")
        params["document_id"] = document_id
    elif document_ids:
        clauses.append("ve.document_id = ANY(:document_ids)")
        params["document_ids"] = document_ids
    if not clauses:
        return "", params
    return "WHERE " + " AND ".join(clauses), params


def add_documents(docs: List[Dict]):
    """
    docs: list of {id: str, text: str, metadata: dict} — add to pgvector.
    metadata is used for filtering (e.g., kb_id, document_id, version_id).
    """
    if not docs:
        return []
    engine = get_engine()
    if engine.dialect.name != "postgresql":
        return [d["id"] for d in docs]
    _ensure_schema(engine)
    embedder = _get_embedder()
    ids = [d["id"] for d in docs]
    texts = [d["text"] for d in docs]
    metas = [d.get("metadata") or {} for d in docs]
    embeddings = embedder.encode(texts, show_progress_bar=False)
    if hasattr(embeddings, "tolist"):
        embeddings = embeddings.tolist()
    rows = []
    for idx, cid in enumerate(ids):
        meta = metas[idx] or {}
        emb = embeddings[idx]
        emb_str = "[" + ",".join(f"{x:.6f}" for x in emb) + "]"
        rows.append(
            {
                "chunk_id": cid,
                "kb_id": meta.get("kb_id"),
                "document_id": meta.get("document_id"),
                "metadata": meta,
                "embedding": emb_str,
            }
        )
    with engine.begin() as conn:
        conn.execute(
            text(
                """
                INSERT INTO vector_embeddings (chunk_id, kb_id, document_id, metadata, embedding)
                VALUES (:chunk_id, :kb_id, :document_id, :metadata, CAST(:embedding AS vector))
                ON CONFLICT (chunk_id) DO UPDATE
                SET kb_id = EXCLUDED.kb_id,
                    document_id = EXCLUDED.document_id,
                    metadata = EXCLUDED.metadata,
                    embedding = EXCLUDED.embedding
                """
            ),
            rows,
        )
    return ids


def query_documents(
    query: str,
    n_results: int = 5,
    kb_id: Optional[str] = None,
    kb_ids: Optional[List[str]] = None,
    document_id: Optional[str] = None,
    document_ids: Optional[List[str]] = None,
):
    """Return top matches; optionally filter by kb_id and/or document_id."""
    engine = get_engine()
    if engine.dialect.name != "postgresql":
        return _query_documents_sqlite(
            query,
            n_results=n_results,
            kb_id=kb_id,
            kb_ids=kb_ids,
            document_id=document_id,
            document_ids=document_ids,
        )
    _ensure_schema(engine)
    embedder = _get_embedder()
    embeddings = embedder.encode([query], show_progress_bar=False)
    if hasattr(embeddings, "tolist"):
        embeddings = embeddings.tolist()
    emb = embeddings[0]
    emb_str = "[" + ",".join(f"{x:.6f}" for x in emb) + "]"
    where_sql, params = _build_filters(kb_id, kb_ids, document_id, document_ids)
    params["query_embedding"] = emb_str
    params["limit"] = max(1, int(n_results))
    sql = f"""
        SELECT ve.chunk_id, c.text, ve.metadata, (ve.embedding <=> CAST(:query_embedding AS vector)) AS distance
        FROM vector_embeddings ve
        JOIN chunks c ON c.id = ve.chunk_id
        {where_sql}
        ORDER BY distance ASC
        LIMIT :limit
    """
    with engine.begin() as conn:
        rows = conn.execute(text(sql), params).fetchall()
    ids = [r[0] for r in rows]
    documents = [r[1] for r in rows]
    metadatas = [r[2] or {} for r in rows]
    distances = [float(r[3]) if r[3] is not None else None for r in rows]
    return {"ids": [ids], "documents": [documents], "metadatas": [metadatas], "distances": [distances]}


def embedder_info() -> Dict[str, Optional[str]]:
    _get_embedder()
    return {
        "kind": _embedder_kind,
        "provider": EMBED_PROVIDER,
        "model": EMBED_MODEL_NAME if _embedder_kind == "sentence-transformers" else None,
    }


def delete_documents(ids: List[str]) -> int:
    """Best-effort delete by IDs from pgvector."""
    if not ids:
        return 0
    engine = get_engine()
    if engine.dialect.name != "postgresql":
        return len(ids)
    _ensure_schema(engine)
    with engine.begin() as conn:
        conn.execute(text("DELETE FROM vector_embeddings WHERE chunk_id = ANY(:ids)"), {"ids": ids})
    return len(ids)


def _cosine_distance(a: List[float], b: List[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(y * y for y in b))
    if norm_a == 0.0 or norm_b == 0.0:
        return 1.0
    cosine = max(-1.0, min(1.0, dot / (norm_a * norm_b)))
    return 1.0 - cosine


def _query_documents_sqlite(
    query: str,
    *,
    n_results: int,
    kb_id: Optional[str],
    kb_ids: Optional[List[str]],
    document_id: Optional[str],
    document_ids: Optional[List[str]],
):
    engine = get_engine()
    embedder = _get_embedder()
    query_emb = embedder.encode([query], show_progress_bar=False)
    if hasattr(query_emb, "tolist"):
        query_emb = query_emb.tolist()
    query_vec = query_emb[0]

    clauses = []
    params: Dict[str, object] = {}
    if kb_id:
        clauses.append("d.kb_id = :kb_id")
        params["kb_id"] = kb_id
    elif kb_ids:
        placeholders = []
        for idx, value in enumerate(kb_ids):
            key = f"kb_{idx}"
            placeholders.append(f":{key}")
            params[key] = value
        clauses.append(f"d.kb_id IN ({', '.join(placeholders)})")
    if document_id:
        clauses.append("d.id = :document_id")
        params["document_id"] = document_id
    elif document_ids:
        placeholders = []
        for idx, value in enumerate(document_ids):
            key = f"doc_{idx}"
            placeholders.append(f":{key}")
            params[key] = value
        clauses.append(f"d.id IN ({', '.join(placeholders)})")

    where_sql = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    sql = f"""
        SELECT c.id, c.text, d.kb_id, d.id, dv.id, c.start_pos, c.end_pos
        FROM chunks c
        JOIN document_versions dv ON dv.id = c.version_id
        JOIN documents d ON d.id = dv.document_id
        {where_sql}
    """
    with engine.begin() as conn:
        rows = conn.execute(text(sql), params).fetchall()

    scored = []
    texts = [r[1] or "" for r in rows]
    if not texts:
        return {"ids": [[]], "documents": [[]], "metadatas": [[]], "distances": [[]]}
    embeddings = embedder.encode(texts, show_progress_bar=False)
    if hasattr(embeddings, "tolist"):
        embeddings = embeddings.tolist()
    for row, emb in zip(rows, embeddings):
        scored.append(
            (
                row[0],
                row[1],
                {
                    "kb_id": row[2],
                    "document_id": row[3],
                    "version_id": row[4],
                    "start_pos": row[5],
                    "end_pos": row[6],
                },
                _cosine_distance(query_vec, emb),
            )
        )
    scored.sort(key=lambda item: item[3])
    top = scored[: max(1, int(n_results))]
    return {
        "ids": [[item[0] for item in top]],
        "documents": [[item[1] for item in top]],
        "metadatas": [[item[2] for item in top]],
        "distances": [[item[3] for item in top]],
    }
