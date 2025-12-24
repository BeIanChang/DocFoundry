import hashlib
import os
import struct
from typing import Dict, List, Optional

# Disable Chroma telemetry by default (avoids noisy PostHog version mismatches in dev).
os.environ.setdefault("ANONYMIZED_TELEMETRY", "False")

try:
    import chromadb  # type: ignore
except Exception:  # pragma: no cover
    chromadb = None

CHROMA_DIR = os.environ.get("CHROMA_DIR", "./chroma_db")
EMBED_MODEL_NAME = os.environ.get("EMBED_MODEL", "all-MiniLM-L6-v2")
EMBED_PROVIDER = os.environ.get("EMBED_PROVIDER", "auto").strip().lower()
FALLBACK_EMBED_DIM = int(os.environ.get("EMBED_DIM", "384"))

_client = None
_collection = None
_embedder = None
_embedder_kind = None


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


def _get_collection():
    global _client, _collection
    if _collection is not None:
        return _collection
    if chromadb is None:
        raise RuntimeError("chromadb is not available (install backend requirements)")
    _client = chromadb.PersistentClient(path=CHROMA_DIR)
    _collection = _client.get_or_create_collection("documents")
    return _collection


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


def add_documents(docs: List[Dict]):
    """
    docs: list of {id: str, text: str, metadata: dict} — add to chroma.
    metadata is used for filtering (e.g., kb_id, document_id, version_id).
    """
    if not docs:
        return []
    collection = _get_collection()
    embedder = _get_embedder()
    ids = [d['id'] for d in docs]
    texts = [d['text'] for d in docs]
    metadata = [d.get('metadata') or {} for d in docs]
    embeddings = embedder.encode(texts, show_progress_bar=False)
    if hasattr(embeddings, "tolist"):
        embeddings = embeddings.tolist()
    collection.add(ids=ids, documents=texts, embeddings=embeddings, metadatas=metadata)
    return ids


def query_documents(query: str, n_results: int = 5, kb_id: Optional[str] = None, document_id: Optional[str] = None):
    """Return top matches; optionally filter by kb_id and/or document_id."""
    collection = _get_collection()
    embedder = _get_embedder()
    embeddings = embedder.encode([query], show_progress_bar=False)
    if hasattr(embeddings, "tolist"):
        embeddings = embeddings.tolist()
    emb = embeddings[0]
    filters = []
    if kb_id:
        filters.append({"kb_id": kb_id})
    if document_id:
        filters.append({"document_id": document_id})
    # Chroma (new API) expects a single logical operator; use $and when multiple filters
    where = None
    if len(filters) == 1:
        where = filters[0]
    elif len(filters) > 1:
        where = {"$and": filters}

    results = collection.query(query_embeddings=[emb], n_results=n_results, where=where)
    # results is a dict with ids/documents/scores/metadatas
    return results


def embedder_info() -> Dict[str, Optional[str]]:
    _get_embedder()
    return {
        "kind": _embedder_kind,
        "provider": EMBED_PROVIDER,
        "model": EMBED_MODEL_NAME if _embedder_kind == "sentence-transformers" else None,
    }
