from __future__ import annotations

from dataclasses import dataclass
from math import ceil
import re
from typing import Any, Dict, List, Optional, Tuple

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.agent.schemas import AgentCitation, AgentQueryRequest, AgentQueryResponse
from app.agent.tools import AnswerTool, VectorSearchTool
from app.db import models
from app.embeddings.llm import chat


@dataclass(frozen=True)
class AgentScope:
    project_id: Optional[str] = None
    kb_id: Optional[str] = None
    document_id: Optional[str] = None

    def to_json(self) -> Dict[str, Any]:
        return {
            "project_id": self.project_id,
            "kb_id": self.kb_id,
            "document_id": self.document_id,
        }


def _preview(text: str, n: int = 240) -> str:
    t = (text or "").replace("\n", " ").strip()
    return t[:n] + ("..." if len(t) > n else "")


class AgentOrchestrator:
    def __init__(self, *, search_tool: VectorSearchTool | None = None, answer_tool: AnswerTool | None = None):
        self.search_tool = search_tool or VectorSearchTool()
        self.answer_tool = answer_tool or AnswerTool()

    def run(self, req: AgentQueryRequest, *, db: Session, user: Dict[str, Any]) -> AgentQueryResponse:
        scope = AgentScope(project_id=req.project_id, kb_id=req.kb_id, document_id=req.document_id)
        self._validate_scope(scope, db=db)

        run = models.AgentRun(
            user_id=user.get("id"),
            message=req.message,
            scope=scope.to_json(),
            mode=req.mode,
            status="running",
        )
        db.add(run)
        db.commit()
        db.refresh(run)

        steps_out: List[Dict[str, Any]] = []
        self._add_step(db, run_id=run.id, idx=0, kind="interpret", payload={"scope": scope.to_json(), "mode": req.mode})

        intent = self._detect_intent(req.message)
        if intent == "list_documents":
            answer_text, citations = self._answer_list_documents(req.message, scope=scope, db=db)
            self._add_step(
                db,
                run_id=run.id,
                idx=1,
                kind="tool_call",
                payload={"tool": "list_documents", "input": {"scope": scope.to_json()}, "output": {"count": len(citations)}},
            )
            self._add_step(
                db,
                run_id=run.id,
                idx=2,
                kind="synthesize",
                payload={"provider": "db", "model": None, "answer_preview": _preview(answer_text, 320), "citations": len(citations)},
            )
            verified, verify_note = self._verify(answer_text, citations)
            self._add_step(db, run_id=run.id, idx=3, kind="verify", payload={"ok": verified, "note": verify_note})

            run.status = "completed" if verified else "needs_review"
            run.final_answer = answer_text
            run.provider = "db"
            run.model = None
            run.citations = [c.dict() for c in citations]
            db.add(run)
            db.commit()

            if req.return_steps:
                steps_out = self._read_steps(db, run_id=run.id)

            return AgentQueryResponse(
                run_id=run.id,
                answer=answer_text,
                provider="db",
                model=None,
                citations=citations,
                steps=steps_out if req.return_steps else None,
            )

        # If user scoped to a KB but not a specific document, try selecting relevant documents
        selected_doc_ids: List[str] = []
        if scope.kb_id and not scope.document_id:
            selected_doc_ids = self._route_documents(req.message, kb_id=scope.kb_id, db=db)
            self._add_step(
                db,
                run_id=run.id,
                idx=1,
                kind="tool_call",
                payload={
                    "tool": "document_router",
                    "input": {"query": req.message, "kb_id": scope.kb_id},
                    "output": {"selected_document_ids": selected_doc_ids, "count": len(selected_doc_ids)},
                },
            )
        else:
            self._add_step(
                db,
                run_id=run.id,
                idx=1,
                kind="tool_call",
                payload={
                    "tool": "document_router",
                    "input": {"query": req.message, "kb_id": scope.kb_id, "document_id": scope.document_id},
                    "output": {"skipped": True},
                },
            )

        top_k = max(1, int(req.top_k or 5))
        contexts = self._retrieve(req.message, top_k=top_k, kb_id=scope.kb_id, document_id=scope.document_id, routed_doc_ids=selected_doc_ids)
        self._add_step(
            db,
            run_id=run.id,
            idx=2,
            kind="tool_call",
            payload={
                "tool": "vector_search",
                "input": {
                    "query": req.message,
                    "top_k": top_k,
                    "kb_id": scope.kb_id,
                    "document_id": scope.document_id,
                    "routed_document_ids": selected_doc_ids or None,
                },
                "output": {"matches": len(contexts), "top": [{"chunk_id": c.chunk_id, "score": c.score} for c in contexts[:5]]},
            },
        )

        citations = [
            AgentCitation(
                chunk_id=c.chunk_id,
                score=c.score,
                metadata=c.metadata or {},
                text_preview=_preview(c.text),
            )
            for c in contexts
        ]

        if not contexts:
            answer_text = (
                "I couldn't find any matching chunks for your request in the current scope. "
                "Try uploading relevant documents, increasing `top_k`, or widening the scope."
            )
            provider = None
            model = None
        else:
            llm_contexts = [
                {"chunk_id": c.chunk_id, "text": c.text, "score": c.score, "metadata": c.metadata or {}}
                for c in contexts[: max(1, int(req.top_k or 5))]
            ]
            llm_resp = self.answer_tool.answer(req.message, llm_contexts)
            answer_text = llm_resp.get("answer") or ""
            provider = llm_resp.get("provider")
            model = llm_resp.get("model")

        self._add_step(
            db,
            run_id=run.id,
            idx=3,
            kind="synthesize",
            payload={"provider": provider, "model": model, "answer_preview": _preview(answer_text, 320), "citations": len(citations)},
        )

        verified, verify_note = self._verify(answer_text, citations)
        self._add_step(db, run_id=run.id, idx=4, kind="verify", payload={"ok": verified, "note": verify_note})

        run.status = "completed" if verified else "needs_review"
        run.final_answer = answer_text
        run.provider = provider
        run.model = model
        run.citations = [c.dict() for c in citations]
        db.add(run)
        db.commit()

        if req.return_steps:
            steps_out = self._read_steps(db, run_id=run.id)

        return AgentQueryResponse(
            run_id=run.id,
            answer=answer_text,
            provider=provider,
            model=model,
            citations=citations,
            steps=steps_out if req.return_steps else None,
        )

    def _detect_intent(self, message: str) -> str:
        q = (message or "").strip().lower()
        if not q:
            return "answer"
        if re.search(r"\b(list|show|what are|what's)\b.*\b(documents|docs)\b", q):
            return "list_documents"
        if re.search(r"\b(documents|docs)\b.*\b(list|show)\b", q):
            return "list_documents"
        return "answer"

    def _answer_list_documents(self, message: str, *, scope: AgentScope, db: Session) -> Tuple[str, List[AgentCitation]]:
        # If a specific document is selected, return its profile.
        if scope.document_id:
            doc = db.get(models.Document, scope.document_id)
            if not doc:
                return ("No document found for the selected scope.", [AgentCitation(chunk_id=None, metadata={"source": "db", "kind": "missing_document"})])
            ver = (
                db.query(models.DocumentVersion)
                .filter(models.DocumentVersion.document_id == doc.id)
                .order_by(models.DocumentVersion.version_number.desc())
                .first()
            )
            prof = None
            if ver:
                prof = (
                    db.query(models.DocumentProfile)
                    .filter(models.DocumentProfile.version_id == ver.id)
                    .order_by(models.DocumentProfile.created_at.desc())
                    .first()
                )
            summary = (getattr(prof, "summary", None) or "").strip()
            parts = [f"Selected document: {doc.title or '(untitled)'}", f"document_id: {doc.id}"]
            if getattr(prof, "doc_type", None):
                parts.append(f"type: {prof.doc_type}")
            if getattr(prof, "year_start", None) or getattr(prof, "year_end", None):
                parts.append(f"years: {prof.year_start or '?'}–{prof.year_end or '?'}")
            if summary:
                parts.append("")
                parts.append("Summary:")
                parts.append(summary)
            answer = "\n".join(parts)
            cite = AgentCitation(
                chunk_id=None,
                score=None,
                metadata={"source": "db", "kind": "document_profile", "document_id": doc.id, "version_id": getattr(ver, "id", None)},
                text_preview=_preview(summary) if summary else None,
            )
            return answer, [cite]

        if not scope.kb_id:
            answer = "To list documents, select a Knowledge Base (KB) first (or provide kb_id)."
            cite = AgentCitation(chunk_id=None, metadata={"source": "db", "kind": "missing_kb"}, text_preview=None)
            return answer, [cite]

        docs = (
            db.query(models.Document)
            .filter(models.Document.kb_id == scope.kb_id)
            .order_by(models.Document.created_at.desc())
            .all()
        )
        if not docs:
            answer = "No documents found in this KB yet."
            cite = AgentCitation(chunk_id=None, metadata={"source": "db", "kind": "document_list", "kb_id": scope.kb_id, "count": 0})
            return answer, [cite]

        lines = [f"Documents in KB {scope.kb_id} ({len(docs)}):"]
        cites: List[AgentCitation] = []
        for d in docs[:50]:
            ver = (
                db.query(models.DocumentVersion)
                .filter(models.DocumentVersion.document_id == d.id)
                .order_by(models.DocumentVersion.version_number.desc())
                .first()
            )
            prof = None
            if ver:
                prof = (
                    db.query(models.DocumentProfile)
                    .filter(models.DocumentProfile.version_id == ver.id)
                    .order_by(models.DocumentProfile.created_at.desc())
                    .first()
                )
            doc_type = getattr(prof, "doc_type", None)
            tags = getattr(prof, "tags", None) or []
            summary = (getattr(prof, "summary", None) or "").strip()
            label = d.title or "(untitled)"
            suffix = []
            if doc_type:
                suffix.append(doc_type)
            if tags:
                suffix.append(",".join([str(t) for t in tags[:3]]))
            extra = f" — {' · '.join(suffix)}" if suffix else ""
            lines.append(f"- {label}{extra} (document_id={d.id})")
            cites.append(
                AgentCitation(
                    chunk_id=None,
                    score=None,
                    metadata={"source": "db", "kind": "document_profile", "document_id": d.id, "version_id": getattr(ver, "id", None)},
                    text_preview=_preview(summary) if summary else None,
                )
            )

        answer = "\n".join(lines)
        return answer, cites

    def _retrieve(
        self,
        query: str,
        *,
        top_k: int,
        kb_id: Optional[str],
        document_id: Optional[str],
        routed_doc_ids: List[str],
    ):
        if document_id:
            return self.search_tool.search(query, top_k=top_k, kb_id=kb_id, document_id=document_id)
        if routed_doc_ids:
            per_doc_k = max(1, int(ceil(top_k / max(1, len(routed_doc_ids)))))
            all_ctx = []
            for doc_id in routed_doc_ids[:8]:
                all_ctx.extend(self.search_tool.search(query, top_k=per_doc_k, kb_id=kb_id, document_id=doc_id))
            all_ctx.sort(key=lambda c: (c.score is None, c.score))
            return all_ctx[:top_k]
        return self.search_tool.search(query, top_k=top_k, kb_id=kb_id, document_id=None)

    def _route_documents(self, query: str, *, kb_id: str, db: Session) -> List[str]:
        docs = db.query(models.Document).filter(models.Document.kb_id == kb_id).order_by(models.Document.created_at.desc()).all()
        if not docs:
            return []

        candidates: List[Dict[str, Any]] = []
        for d in docs[:30]:
            ver = (
                db.query(models.DocumentVersion)
                .filter(models.DocumentVersion.document_id == d.id)
                .order_by(models.DocumentVersion.version_number.desc())
                .first()
            )
            prof = None
            if ver:
                prof = (
                    db.query(models.DocumentProfile)
                    .filter(models.DocumentProfile.version_id == ver.id)
                    .order_by(models.DocumentProfile.created_at.desc())
                    .first()
                )
            candidates.append(
                {
                    "document_id": d.id,
                    "title": d.title or "",
                    "doc_type": getattr(prof, "doc_type", None),
                    "tags": getattr(prof, "tags", None) or [],
                    "summary": _preview(getattr(prof, "summary", "") or "", 240),
                }
            )

        # If we don't have any profiles yet, routing doesn't add much value.
        if not any(c.get("summary") for c in candidates):
            return []

        # Ask the LLM to pick relevant docs (best-effort). Fall back to a simple heuristic.
        try:
            messages = [
                {
                    "role": "system",
                    "content": "Select which documents are most likely to contain the answer. Return ONLY JSON: {\"document_ids\": [..]}.",
                },
                {
                    "role": "user",
                    "content": f"Question: {query}\n\nCandidates:\n{candidates}\n\nPick up to 5 document_ids.",
                },
            ]
            resp = chat(messages, temperature=0.0, max_tokens=256)
            content = (resp.get("content") or "").strip()
            start = content.find("{")
            end = content.rfind("}")
            if start != -1 and end != -1 and end > start:
                import json

                obj = json.loads(content[start : end + 1])
                ids = obj.get("document_ids") or []
                ids = [i for i in ids if isinstance(i, str)]
                allowed = {c["document_id"] for c in candidates}
                picked = [i for i in ids if i in allowed][:5]
                if picked:
                    return picked
        except Exception:
            pass

        # Heuristic fallback: prefer finance-tagged/typed docs if query looks financial; else newest docs.
        q = query.lower()
        is_finance = any(k in q for k in ["net profit", "profit", "revenue", "income", "ebitda", "cash flow", "p&l", "balance sheet"])
        if is_finance:
            scored = []
            for c in candidates:
                score = 0
                if (c.get("doc_type") or "").startswith("financial"):
                    score += 3
                if "finance" in (c.get("tags") or []):
                    score += 2
                t = (c.get("title") or "").lower()
                if any(k in t for k in ["annual", "financial", "statement", "report", "income"]):
                    score += 1
                scored.append((score, c["document_id"]))
            scored.sort(key=lambda x: x[0], reverse=True)
            picked = [d for s, d in scored if s > 0][:5]
            return picked

        return [c["document_id"] for c in candidates[:3]]

    def _validate_scope(self, scope: AgentScope, *, db: Session) -> None:
        if scope.project_id:
            proj = db.get(models.Project, scope.project_id)
            if not proj:
                raise HTTPException(status_code=404, detail="project not found")
        if scope.kb_id:
            kb = db.get(models.KnowledgeBase, scope.kb_id)
            if not kb:
                raise HTTPException(status_code=404, detail="knowledge base not found")
            if scope.project_id and kb.project_id and kb.project_id != scope.project_id:
                raise HTTPException(status_code=400, detail="kb_id does not belong to project_id")
        if scope.document_id:
            doc = db.get(models.Document, scope.document_id)
            if not doc:
                raise HTTPException(status_code=404, detail="document not found")
            if scope.kb_id and doc.kb_id and doc.kb_id != scope.kb_id:
                raise HTTPException(status_code=400, detail="document_id does not belong to kb_id")

    def _verify(self, answer: str, citations: List[AgentCitation]) -> Tuple[bool, str]:
        if not answer.strip():
            return False, "empty answer"
        if not citations:
            return False, "no citations"
        return True, "ok"

    def _add_step(self, db: Session, *, run_id: str, idx: int, kind: str, payload: Dict[str, Any]) -> None:
        step = models.AgentStep(run_id=run_id, idx=idx, kind=kind, payload=payload)
        db.add(step)
        db.commit()

    def _read_steps(self, db: Session, *, run_id: str) -> List[Dict[str, Any]]:
        steps = (
            db.query(models.AgentStep)
            .filter(models.AgentStep.run_id == run_id)
            .order_by(models.AgentStep.idx.asc(), models.AgentStep.created_at.asc())
            .all()
        )
        return [
            {"index": s.idx, "kind": s.kind, "payload": s.payload or {}, "created_at": s.created_at}
            for s in steps
        ]
