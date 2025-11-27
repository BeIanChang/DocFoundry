import os
from typing import List, Dict, Optional
from sentence_transformers import SentenceTransformer
import chromadb

# simple local chroma client (new API)
CHROMA_DIR = os.environ.get('CHROMA_DIR', './chroma_db')
EMBED_MODEL_NAME = os.environ.get('EMBED_MODEL', 'all-MiniLM-L6-v2')
client = chromadb.PersistentClient(path=CHROMA_DIR)
collection = client.get_or_create_collection("documents")

# load a small model for embeddings — user can swap to OpenAI or others
EMBED_MODEL = SentenceTransformer(EMBED_MODEL_NAME)


def add_documents(docs: List[Dict]):
    """
    docs: list of {id: str, text: str, metadata: dict} — add to chroma.
    metadata is used for filtering (e.g., kb_id, document_id, version_id).
    """
    if not docs:
        return []
    ids = [d['id'] for d in docs]
    texts = [d['text'] for d in docs]
    metadata = [d.get('metadata') or {} for d in docs]
    embeddings = EMBED_MODEL.encode(texts, show_progress_bar=False).tolist()
    collection.add(ids=ids, documents=texts, embeddings=embeddings, metadatas=metadata)
    return ids


def query_documents(query: str, n_results: int = 5, kb_id: Optional[str] = None, document_id: Optional[str] = None):
    """Return top matches; optionally filter by kb_id and/or document_id."""
    emb = EMBED_MODEL.encode([query]).tolist()[0]
    where = {}
    if kb_id:
        where["kb_id"] = kb_id
    if document_id:
        where["document_id"] = document_id
    results = collection.query(query_embeddings=[emb], n_results=n_results, where=where or None)
    # results is a dict with ids/documents/scores/metadatas
    return results
