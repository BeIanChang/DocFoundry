from __future__ import annotations

from dataclasses import dataclass
from math import ceil
import re
from typing import Any, Dict, List, Optional, Tuple

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.agent.schemas import AgentCitation, AgentQueryRequest, AgentQueryResponse
import os
from app.agent.tools import AnswerTool, KeywordSearchTool, VectorSearchTool, WebSearchTool
from app.agent.planner import plan_next_step
from app.db import models
from app.embeddings.llm import chat


@dataclass(frozen=True)
class AgentScope:
    project_id: Optional[str] = None
    project_ids: Optional[List[str]] = None
    folder_id: Optional[str] = None
    kb_id: Optional[str] = None
    document_id: Optional[str] = None

    def to_json(self) -> Dict[str, Any]:
        return {
            "project_id": self.project_id,
            "project_ids": self.project_ids or [],
            "folder_id": self.folder_id,
            "kb_id": self.kb_id,
            "document_id": self.document_id,
        }


def _preview(text: str, n: int = 240) -> str:
    t = (text or "").replace("\n", " ").strip()
    return t[:n] + ("..." if len(t) > n else "")


class AgentOrchestrator:
    def __init__(self, *, search_tool: VectorSearchTool | None = None, answer_tool: AnswerTool | None = None):
        self.search_tool = search_tool or VectorSearchTool()
        self.keyword_tool = KeywordSearchTool()
        self.web_tool = WebSearchTool()
        self.answer_tool = answer_tool or AnswerTool()

    def run(self, req: AgentQueryRequest, *, db: Session, user: Dict[str, Any]) -> AgentQueryResponse:
        project_ids = [p for p in (req.project_ids or []) if isinstance(p, str)]
        if req.project_id and req.project_id not in project_ids:
            project_ids = project_ids + [req.project_id]
        scope = AgentScope(
            project_id=req.project_id,
            project_ids=project_ids or None,
            folder_id=req.folder_id,
            kb_id=req.kb_id,
            document_id=req.document_id,
        )
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

        # Agent loop state
        observations: List[Dict[str, Any]] = []
        routed_doc_ids: List[str] = []
        last_contexts = []
        citations: List[AgentCitation] = []
        provider: Optional[str] = None
        model: Optional[str] = None
        answer_text: str = ""

        max_steps = max(1, int(req.max_steps or 20))
        top_k = max(1, int(req.top_k or 5))

        for i in range(1, max_steps + 1):
            plan = plan_next_step(
                user_message=req.message,
                scope=scope.to_json(),
                observations=observations,
                max_doc_picks=5,
                top_k=top_k,
            )
            self._add_step(
                db,
                run_id=run.id,
                idx=i,
                kind="plan",
                payload={"action": plan.action, "args": plan.args, "rationale": plan.rationale},
            )

            action = plan.action

            if action == "final":
                answer_text = plan.args.get("answer") or "OK."
                provider = "planner"
                model = None
                citations = [AgentCitation(chunk_id=None, metadata={"source": "planner", "kind": "final"})]
                break

            if action == "list_documents":
                answer_text, citations = self._answer_list_documents(req.message, scope=scope, db=db)
                provider = "db"
                model = None
                observations.append({"tool": "list_documents", "count": len(citations)})
                break

            if action == "get_document_profile":
                # Force profile view for selected doc; if none selected, fall back to listing
                if scope.document_id:
                    answer_text, citations = self._answer_list_documents(req.message, scope=scope, db=db)
                else:
                    answer_text, citations = self._answer_list_documents(req.message, scope=scope, db=db)
                provider = "db"
                model = None
                observations.append({"tool": "get_document_profile"})
                break

            if action == "route_documents":
                if scope.document_id:
                    observations.append({"tool": "route_documents", "skipped": True, "reason": "document_id is set"})
                    continue
                if not scope.kb_id:
                    observations.append({"tool": "route_documents", "skipped": True, "reason": "kb_id is missing"})
                    continue
                routed_doc_ids = self._route_documents(req.message, kb_id=scope.kb_id, db=db)
                observations.append({"tool": "route_documents", "picked": routed_doc_ids})
                continue

            if action == "vector_search":
                q = plan.args.get("query") or req.message
                doc_id = scope.document_id
                if not doc_id and plan.args.get("document_id"):
                    # Only allow explicit document_id selection when kb scope exists
                    doc_id = str(plan.args.get("document_id"))
                    if scope.kb_id:
                        doc = db.get(models.Document, doc_id)
                        if not doc or (doc.kb_id and doc.kb_id != scope.kb_id):
                            observations.append({"tool": "vector_search", "error": "document_id not in kb scope"})
                            continue
                    else:
                        observations.append({"tool": "vector_search", "error": "missing kb_id for document filter"})
                        continue

                last_contexts = self._retrieve(
                    q,
                    top_k=top_k,
                    kb_id=scope.kb_id,
                    project_ids=scope.project_ids,
                    folder_id=scope.folder_id,
                    document_id=doc_id,
                    routed_doc_ids=routed_doc_ids,
                    db=db,
                )
                citations = [
                    AgentCitation(chunk_id=c.chunk_id, score=c.score, metadata=c.metadata or {}, text_preview=_preview(c.text))
                    for c in last_contexts
                ]
                observations.append({"tool": "vector_search", "matches": len(last_contexts), "top": [{"chunk_id": c.chunk_id, "score": c.score} for c in last_contexts[:5]]})
                continue

            if action == "keyword_search":
                q = plan.args.get("query") or req.message
                doc_id = scope.document_id
                if not doc_id and plan.args.get("document_id"):
                    doc_id = str(plan.args.get("document_id"))
                    if scope.kb_id:
                        doc = db.get(models.Document, doc_id)
                        if not doc or (doc.kb_id and doc.kb_id != scope.kb_id):
                            observations.append({"tool": "keyword_search", "error": "document_id not in kb scope"})
                            continue
                    else:
                        observations.append({"tool": "keyword_search", "error": "missing kb_id for document filter"})
                        continue

                results = self.keyword_tool.search(
                    q,
                    db=db,
                    top_k=top_k,
                    kb_id=scope.kb_id,
                    kb_ids=None,
                    document_id=doc_id,
                    document_ids=None,
                    project_ids=scope.project_ids,
                    folder_id=scope.folder_id,
                )
                last_contexts = results
                citations = [
                    AgentCitation(
                        chunk_id=r.chunk_id,
                        score=r.score,
                        metadata=r.metadata or {},
                        text_preview=_preview(r.text),
                    )
                    for r in results
                ]
                observations.append(
                    {
                        "tool": "keyword_search",
                        "matches": len(results),
                        "top": [{"chunk_id": r.chunk_id, "score": r.score, "matches": r.matches[:5]} for r in results[:5]],
                    }
                )
                continue

            if action == "web_search":
                q = plan.args.get("query") or req.message
                api_key = os.environ.get("GOOGLE_SEARCH_API_KEY", "").strip()
                cse_id = os.environ.get("GOOGLE_CSE_ID", "").strip()
                if not api_key or not cse_id:
                    observations.append({"tool": "web_search", "error": "missing GOOGLE_SEARCH_API_KEY or GOOGLE_CSE_ID"})
                    continue
                results = self.web_tool.search(q, api_key=api_key, cse_id=cse_id, top_k=top_k)
                last_contexts = results
                citations = [
                    AgentCitation(
                        chunk_id=None,
                        score=None,
                        metadata=r.metadata or {},
                        text_preview=_preview(r.text),
                    )
                    for r in results
                ]
                observations.append(
                    {
                        "tool": "web_search",
                        "matches": len(results),
                        "top": [{"title": r.metadata.get("title"), "url": r.metadata.get("url")} for r in results[:5]],
                    }
                )
                continue

            if action == "answer_with_context":
                if not last_contexts:
                    observations.append({"tool": "answer_with_context", "error": "no_contexts"})
                    continue
                llm_contexts = [{"chunk_id": c.chunk_id, "text": c.text, "score": c.score, "metadata": c.metadata or {}} for c in last_contexts[:top_k]]
                llm_resp = self.answer_tool.answer(req.message, llm_contexts)
                answer_text = llm_resp.get("answer") or ""
                provider = llm_resp.get("provider")
                model = llm_resp.get("model")
                observations.append({"tool": "answer_with_context", "provider": provider, "model": model})
                break

            observations.append({"tool": "unknown", "action": action})

        if not answer_text:
            answer_text = (
                "I couldn't complete the request within the step limit. "
                "Try increasing `max_steps`, widening scope, or asking a more specific question."
            )
            provider = provider or "planner"
            model = model or None
            if not citations:
                citations = [AgentCitation(chunk_id=None, metadata={"source": "planner", "kind": "step_limit"})]

        # final verification
        verified, verify_note = self._verify(answer_text, citations)
        self._add_step(
            db,
            run_id=run.id,
            idx=max_steps + 2,
            kind="verify",
            payload={"ok": verified, "note": verify_note, "final_provider": provider, "final_model": model},
        )

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
        project_ids: Optional[List[str]],
        folder_id: Optional[str],
        document_id: Optional[str],
        routed_doc_ids: List[str],
        db: Session,
    ):
        doc_ids: Optional[List[str]] = None
        if folder_id:
            doc_ids = [
                d.id for d in db.query(models.Document.id)
                .filter(models.Document.folder_id == folder_id)
                .order_by(models.Document.created_at.desc())
                .all()
            ]
            if not doc_ids:
                return []
        kb_ids: Optional[List[str]] = None
        if not kb_id and project_ids:
            kb_ids = [
                k.id
                for k in db.query(models.KnowledgeBase.id)
                .filter(models.KnowledgeBase.project_id.in_(project_ids))
                .all()
            ]
        if document_id:
            return self.search_tool.search(query, top_k=top_k, kb_id=kb_id, kb_ids=kb_ids, document_id=document_id)
        if doc_ids:
            per_doc_k = max(1, int(ceil(top_k / max(1, len(doc_ids)))))
            all_ctx = []
            for doc_id in doc_ids[:12]:
                all_ctx.extend(self.search_tool.search(query, top_k=per_doc_k, kb_id=kb_id, kb_ids=kb_ids, document_id=doc_id))
            all_ctx.sort(key=lambda c: (c.score is None, c.score))
            return all_ctx[:top_k]
        if routed_doc_ids:
            per_doc_k = max(1, int(ceil(top_k / max(1, len(routed_doc_ids)))))
            all_ctx = []
            for doc_id in routed_doc_ids[:8]:
                all_ctx.extend(self.search_tool.search(query, top_k=per_doc_k, kb_id=kb_id, kb_ids=kb_ids, document_id=doc_id))
            all_ctx.sort(key=lambda c: (c.score is None, c.score))
            return all_ctx[:top_k]
        return self.search_tool.search(query, top_k=top_k, kb_id=kb_id, kb_ids=kb_ids, document_id=None)

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
        project_ids = [p for p in (scope.project_ids or []) if isinstance(p, str)]
        if scope.project_id and scope.project_id not in project_ids:
            project_ids.append(scope.project_id)
        if project_ids:
            existing = {p[0] for p in db.query(models.Project.id).filter(models.Project.id.in_(project_ids)).all()}
            missing = [p for p in project_ids if p not in existing]
            if missing:
                raise HTTPException(status_code=404, detail="project not found")
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
            if project_ids and kb.project_id and kb.project_id not in project_ids:
                raise HTTPException(status_code=400, detail="kb_id does not belong to selected project scope")
        if scope.folder_id:
            folder = db.get(models.Folder, scope.folder_id)
            if not folder:
                raise HTTPException(status_code=404, detail="folder not found")
            if scope.kb_id and folder.kb_id != scope.kb_id:
                raise HTTPException(status_code=400, detail="folder_id does not belong to kb_id")
            if project_ids:
                kb = db.get(models.KnowledgeBase, folder.kb_id)
                if kb and kb.project_id and kb.project_id not in project_ids:
                    raise HTTPException(status_code=400, detail="folder_id does not belong to selected project scope")
        if scope.document_id:
            doc = db.get(models.Document, scope.document_id)
            if not doc:
                raise HTTPException(status_code=404, detail="document not found")
            if scope.kb_id and doc.kb_id and doc.kb_id != scope.kb_id:
                raise HTTPException(status_code=400, detail="document_id does not belong to kb_id")
            if project_ids:
                kb = db.get(models.KnowledgeBase, doc.kb_id) if doc.kb_id else None
                if kb and kb.project_id and kb.project_id not in project_ids:
                    raise HTTPException(status_code=400, detail="document_id does not belong to selected project scope")

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
