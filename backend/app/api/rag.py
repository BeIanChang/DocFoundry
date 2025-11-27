from typing import List, Optional
from fastapi import APIRouter, HTTPException, Depends

from app.embeddings import vector_store
from app.embeddings.llm import generate_answer
from app.db import models
from app.db.session import get_session

router = APIRouter(prefix="/rag", tags=["rag"])


@router.post("/query")
def rag_query(payload: dict, db=Depends(get_session)):
    """
    Minimal RAG endpoint.
    body: {"query": "...", "kb_id": "...", "document_id": "...", "top_k": 5}
    """
    query = payload.get("query")
    if not query:
        raise HTTPException(status_code=400, detail="query is required")
    kb_id: Optional[str] = payload.get("kb_id")
    doc_id: Optional[str] = payload.get("document_id")
    top_k: int = int(payload.get("top_k") or 5)

    # optionally validate kb/doc existence
    if kb_id:
        kb = db.get(models.KnowledgeBase, kb_id)
        if not kb:
            raise HTTPException(status_code=404, detail="knowledge base not found")
    if doc_id:
        doc = db.get(models.Document, doc_id)
        if not doc:
            raise HTTPException(status_code=404, detail="document not found")

    try:
        results = vector_store.query_documents(query, n_results=top_k, kb_id=kb_id, document_id=doc_id)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"vector search failed: {exc}")

    # assemble contexts
    contexts: List[dict] = []
    metadatas = results.get("metadatas") or []
    documents = results.get("documents") or []
    ids = results.get("ids") or []
    distances = results.get("distances") or []
    for idx, doc_list in enumerate(documents):
        # chroma returns lists within lists
        for j, text in enumerate(doc_list):
            meta = metadatas[idx][j] if idx < len(metadatas) and j < len(metadatas[idx]) else {}
            contexts.append({
                "chunk_id": ids[idx][j] if idx < len(ids) and j < len(ids[idx]) else None,
                "text": text,
                "score": distances[idx][j] if idx < len(distances) and j < len(distances[idx]) else None,
                "metadata": meta,
            })

    llm_resp = generate_answer(query, contexts)

    return {
        "query": query,
        "kb_id": kb_id,
        "document_id": doc_id,
        "top_k": top_k,
        "answer": llm_resp.get("answer"),
        "provider": llm_resp.get("provider"),
        "sources": contexts,
    }
