from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from app.embeddings import vector_store
from app.embeddings.llm import generate_answer


@dataclass(frozen=True)
class VectorSearchResult:
    chunk_id: Optional[str]
    text: str
    score: Optional[float]
    metadata: Dict[str, Any]


class VectorSearchTool:
    def search(
        self,
        query: str,
        *,
        top_k: int,
        kb_id: Optional[str] = None,
        document_id: Optional[str] = None,
    ) -> List[VectorSearchResult]:
        raw = vector_store.query_documents(query, n_results=top_k, kb_id=kb_id, document_id=document_id)
        contexts: List[VectorSearchResult] = []

        metadatas = raw.get("metadatas") or []
        documents = raw.get("documents") or []
        ids = raw.get("ids") or []
        distances = raw.get("distances") or []

        for idx, doc_list in enumerate(documents):
            for j, text in enumerate(doc_list):
                meta = metadatas[idx][j] if idx < len(metadatas) and j < len(metadatas[idx]) else {}
                contexts.append(
                    VectorSearchResult(
                        chunk_id=ids[idx][j] if idx < len(ids) and j < len(ids[idx]) else None,
                        text=text,
                        score=distances[idx][j] if idx < len(distances) and j < len(distances[idx]) else None,
                        metadata=meta or {},
                    )
                )
        return contexts


class AnswerTool:
    def answer(self, query: str, contexts: List[Dict[str, Any]]) -> Dict[str, Any]:
        return generate_answer(query, contexts)

