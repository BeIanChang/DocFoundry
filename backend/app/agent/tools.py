from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session

from app.embeddings import vector_store
from app.embeddings.llm import generate_answer
from app.db import models


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
        kb_ids: Optional[List[str]] = None,
        document_id: Optional[str] = None,
        document_ids: Optional[List[str]] = None,
    ) -> List[VectorSearchResult]:
        raw = vector_store.query_documents(
            query,
            n_results=top_k,
            kb_id=kb_id,
            kb_ids=kb_ids,
            document_id=document_id,
            document_ids=document_ids,
        )
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


@dataclass(frozen=True)
class KeywordSearchResult:
    chunk_id: Optional[str]
    text: str
    score: Optional[float]
    metadata: Dict[str, Any]
    matches: List[str]


class KeywordSearchTool:
    """
    Simple keyword search over stored chunks (SQL LIKE).
    This complements vector retrieval for exact terms (IDs, numbers, names).
    """

    def search(
        self,
        query: str,
        *,
        db: Session,
        top_k: int,
        kb_id: Optional[str] = None,
        kb_ids: Optional[List[str]] = None,
        document_id: Optional[str] = None,
        document_ids: Optional[List[str]] = None,
        project_ids: Optional[List[str]] = None,
        folder_id: Optional[str] = None,
        max_candidates: int = 200,
    ) -> List[KeywordSearchResult]:
        q = (query or "").strip()
        if not q:
            return []

        phrase = q.lower()
        tokens = [t.lower() for t in _tokenize(q)]
        patterns = [phrase] if phrase else []
        patterns.extend([t for t in tokens if t and t not in patterns])
        if not patterns:
            return []

        qry = (
            db.query(models.Chunk, models.DocumentVersion, models.Document)
            .join(models.DocumentVersion, models.DocumentVersion.id == models.Chunk.version_id)
            .join(models.Document, models.Document.id == models.DocumentVersion.document_id)
        )
        if kb_id:
            qry = qry.filter(models.Document.kb_id == kb_id)
        elif kb_ids:
            qry = qry.filter(models.Document.kb_id.in_(kb_ids))
        elif folder_id:
            qry = qry.filter(models.Document.folder_id == folder_id)
        elif project_ids:
            qry = qry.join(models.KnowledgeBase, models.KnowledgeBase.id == models.Document.kb_id).filter(
                models.KnowledgeBase.project_id.in_(project_ids)
            )
        if document_id:
            qry = qry.filter(models.Document.id == document_id)
        elif document_ids:
            qry = qry.filter(models.Document.id.in_(document_ids))

        # OR match any pattern (we'll rank later in Python)
        cond = None
        for p in patterns[:12]:
            c = models.Chunk.text.ilike(f"%{p}%")
            cond = c if cond is None else (cond | c)
        if cond is not None:
            qry = qry.filter(cond)

        rows = qry.order_by(models.Chunk.id.asc()).limit(int(max_candidates)).all()

        scored: List[KeywordSearchResult] = []
        for chunk, version, document in rows:
            text = chunk.text or ""
            lower = text.lower()
            matched = [p for p in patterns if p and p in lower]
            if not matched:
                continue
            match_score = 0
            for p in matched:
                match_score += lower.count(p)
            # small bonus for full-phrase match
            if phrase and phrase in lower and phrase not in tokens:
                match_score += 2
            scored.append(
                KeywordSearchResult(
                    chunk_id=chunk.id,
                    text=text,
                    score=float(match_score),
                    matches=matched[:12],
                    metadata={
                        "kb_id": document.kb_id,
                        "document_id": document.id,
                        "version_id": version.id,
                        "start_pos": chunk.start_pos,
                        "end_pos": chunk.end_pos,
                        "search": "keyword",
                        "matches": matched[:12],
                    },
                )
            )

        scored.sort(key=lambda r: (r.score is None, -(r.score or 0.0)))
        return scored[: max(1, int(top_k))]


@dataclass(frozen=True)
class GrepSearchResult:
    chunk_id: Optional[str]
    text: str
    score: Optional[float]
    metadata: Dict[str, Any]
    matches: List[Dict[str, Any]]


def _compile_grep_pattern(query: str) -> Optional[re.Pattern[str]]:
    q = (query or "").strip()
    if not q:
        return None

    source = q
    flags = re.IGNORECASE | re.MULTILINE
    if q.startswith("re:"):
        source = q[3:].strip()
    elif len(q) > 2 and q.startswith("/") and q.endswith("/"):
        source = q[1:-1]
    else:
        source = re.escape(q)

    if not source:
        return None

    try:
        return re.compile(source, flags)
    except re.error:
        return None


class GrepSearchTool:
    """
    Regex/grep-style search over chunk text.

    Query modes:
    - plain text: "net profit" (escaped literal)
    - explicit regex: "re:net\s+profit\s+\d{4}"
    - slash regex: "/net\\s+profit\\s+\\d{4}/"
    """

    def search(
        self,
        query: str,
        *,
        db: Session,
        top_k: int,
        kb_id: Optional[str] = None,
        kb_ids: Optional[List[str]] = None,
        document_id: Optional[str] = None,
        document_ids: Optional[List[str]] = None,
        project_ids: Optional[List[str]] = None,
        folder_id: Optional[str] = None,
        max_candidates: int = 300,
    ) -> List[GrepSearchResult]:
        pattern = _compile_grep_pattern(query)
        if pattern is None:
            return []

        qry = (
            db.query(models.Chunk, models.DocumentVersion, models.Document)
            .join(models.DocumentVersion, models.DocumentVersion.id == models.Chunk.version_id)
            .join(models.Document, models.Document.id == models.DocumentVersion.document_id)
        )
        if kb_id:
            qry = qry.filter(models.Document.kb_id == kb_id)
        elif kb_ids:
            qry = qry.filter(models.Document.kb_id.in_(kb_ids))
        elif folder_id:
            qry = qry.filter(models.Document.folder_id == folder_id)
        elif project_ids:
            qry = qry.join(models.KnowledgeBase, models.KnowledgeBase.id == models.Document.kb_id).filter(
                models.KnowledgeBase.project_id.in_(project_ids)
            )
        if document_id:
            qry = qry.filter(models.Document.id == document_id)
        elif document_ids:
            qry = qry.filter(models.Document.id.in_(document_ids))

        rows = qry.order_by(models.Chunk.id.asc()).limit(int(max_candidates)).all()

        scored: List[GrepSearchResult] = []
        for chunk, version, document in rows:
            text = chunk.text or ""
            if not text:
                continue
            hits = []
            for idx, m in enumerate(pattern.finditer(text)):
                if idx >= 20:
                    break
                hits.append({"match": m.group(0), "start": m.start(), "end": m.end()})
            if not hits:
                continue

            score = float(len(hits))
            scored.append(
                GrepSearchResult(
                    chunk_id=chunk.id,
                    text=text,
                    score=score,
                    matches=hits,
                    metadata={
                        "kb_id": document.kb_id,
                        "document_id": document.id,
                        "version_id": version.id,
                        "start_pos": chunk.start_pos,
                        "end_pos": chunk.end_pos,
                        "search": "grep",
                        "pattern": pattern.pattern,
                    },
                )
            )

        scored.sort(key=lambda r: (r.score is None, -(r.score or 0.0)))
        return scored[: max(1, int(top_k))]


def _tokenize(q: str) -> List[str]:
    import re

    # keep short tokens out to reduce noise
    parts = re.findall(r"[A-Za-z0-9][A-Za-z0-9_\\-\\.]{2,}", q)
    return parts[:24]


@dataclass(frozen=True)
class WebSearchResult:
    chunk_id: Optional[str]
    text: str
    score: Optional[float]
    metadata: Dict[str, Any]


class WebSearchTool:
    """
    Google Custom Search API wrapper.
    Returns results as context items for the agent.
    """

    def search(self, query: str, *, api_key: str, cse_id: str, top_k: int = 5) -> List[WebSearchResult]:
        import requests

        q = (query or "").strip()
        if not q:
            return []
        if not api_key or not cse_id:
            return []

        params = {"q": q, "key": api_key, "cx": cse_id, "num": max(1, min(int(top_k), 10))}
        resp = requests.get("https://www.googleapis.com/customsearch/v1", params=params, timeout=20)
        resp.raise_for_status()
        data = resp.json()
        items = data.get("items") or []

        results: List[WebSearchResult] = []
        for it in items[: top_k]:
            title = (it.get("title") or "").strip()
            snippet = (it.get("snippet") or "").strip()
            link = (it.get("link") or "").strip()
            text = "\n".join([p for p in [title, snippet, link] if p])
            results.append(
                WebSearchResult(
                    chunk_id=None,
                    text=text,
                    score=None,
                    metadata={"source": "web", "title": title, "snippet": snippet, "url": link},
                )
            )
        return results


class AnswerTool:
    def answer(self, query: str, contexts: List[Dict[str, Any]]) -> Dict[str, Any]:
        return generate_answer(query, contexts)
