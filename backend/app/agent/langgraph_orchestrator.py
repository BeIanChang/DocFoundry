from __future__ import annotations

import os
import re
from typing import Any, Dict, List, Optional, Tuple

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.agent.orchestrator import AgentOrchestrator, AgentScope
from app.agent.planner import plan_next_step
from app.agent.schemas import AgentCitation, AgentQueryRequest, AgentQueryResponse
from app.db import models
from app.embeddings.llm import normalize_citation_tags

try:
    from typing_extensions import TypedDict
except Exception:
    from typing import TypedDict

try:
    from langgraph.graph import END, StateGraph
except Exception:  # pragma: no cover - optional dependency
    END = None
    StateGraph = None


class AgentGraphState(TypedDict, total=False):
    req: AgentQueryRequest
    db: Session
    run_id: str
    scope: AgentScope
    top_k: int
    max_steps: int
    step: int
    observations: List[Dict[str, Any]]
    routed_doc_ids: List[str]
    last_contexts: List[Any]
    last_tagged_contexts: List[Dict[str, Any]]
    last_citations: List[AgentCitation]
    citations: List[AgentCitation]
    provider: Optional[str]
    model: Optional[str]
    answer_text: str
    done: bool
    plan_action: str
    plan_args: Dict[str, Any]
    plan_rationale: str


class AgentLangGraphOrchestrator(AgentOrchestrator):
    def __init__(self):
        super().__init__()
        self._graph = self._build_graph() if StateGraph is not None and END is not None else None

    def is_available(self) -> bool:
        return self._graph is not None

    def run(self, req: AgentQueryRequest, *, db: Session, user: Dict[str, Any]) -> AgentQueryResponse:
        if self._graph is None:
            raise HTTPException(
                status_code=500,
                detail="LangGraph engine is not available. Install langgraph to enable loop_engine='langgraph'.",
            )

        project_ids = [p for p in (req.project_ids or []) if isinstance(p, str)]
        if req.project_id and req.project_id not in project_ids:
            project_ids = project_ids + [req.project_id]
        base_scope = AgentScope(
            project_id=req.project_id,
            project_ids=project_ids or None,
            folder_id=req.folder_id,
            kb_id=req.kb_id,
            document_id=req.document_id,
        )
        self._validate_scope(base_scope, db=db)
        scope = self._resolve_scope_kb(base_scope, db=db)

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

        self._add_step(
            db,
            run_id=run.id,
            idx=0,
            kind="interpret",
            payload={"scope": scope.to_json(), "mode": req.mode, "engine": "langgraph"},
        )

        init_state: AgentGraphState = {
            "req": req,
            "db": db,
            "run_id": run.id,
            "scope": scope,
            "top_k": max(1, int(req.top_k or 5)),
            "max_steps": max(1, int(req.max_steps or 20)),
            "step": 0,
            "observations": [],
            "routed_doc_ids": [],
            "last_contexts": [],
            "last_tagged_contexts": [],
            "last_citations": [],
            "citations": [],
            "provider": None,
            "model": None,
            "answer_text": "",
            "done": False,
            "plan_action": "",
            "plan_args": {},
            "plan_rationale": "",
        }
        final_state = self._graph.invoke(init_state)

        answer_text = str(final_state.get("answer_text") or "")
        provider = final_state.get("provider")
        model = final_state.get("model")
        citations = final_state.get("citations") or []
        top_k = int(final_state.get("top_k") or 5)

        if not answer_text:
            answer_text = (
                "I couldn't complete the request within the step limit. "
                "Try increasing `max_steps`, widening scope, or asking a more specific question."
            )
            provider = provider or "planner"
            model = model or None
            if not citations:
                citations = [AgentCitation(chunk_id=None, metadata={"source": "planner", "kind": "step_limit"})]

        if provider not in {"db", "planner"} and citations and not re.search(r"\[[SWD]\d+\]", answer_text or ""):
            tags = [f"[{c.tag}]" for c in citations if c.tag]
            if tags:
                answer_text = f"{answer_text}\n\nSources: {' '.join(tags)}"
        answer_text = normalize_citation_tags(answer_text)

        verified, verify_note = self._verify(answer_text, citations)
        self._add_step(
            db,
            run_id=run.id,
            idx=max(1, int(final_state.get("step") or 0)) + 2,
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

        steps_out = self._read_steps(db, run_id=run.id) if req.return_steps else None
        return AgentQueryResponse(
            run_id=run.id,
            answer=answer_text,
            provider=provider,
            model=model,
            citations=citations,
            steps=steps_out,
        )

    def _build_graph(self):
        workflow = StateGraph(AgentGraphState)
        workflow.add_node("plan", self._plan_node)
        workflow.add_node("act", self._act_node)
        workflow.set_entry_point("plan")
        workflow.add_conditional_edges("plan", self._route_after_plan, {"act": "act", "end": END})
        workflow.add_conditional_edges("act", self._route_after_act, {"plan": "plan", "end": END})
        return workflow.compile()

    def _route_after_plan(self, state: AgentGraphState) -> str:
        return "end" if state.get("done") else "act"

    def _route_after_act(self, state: AgentGraphState) -> str:
        return "end" if state.get("done") else "plan"

    def _append_observation(self, state: AgentGraphState, item: Dict[str, Any]) -> List[Dict[str, Any]]:
        obs = list(state.get("observations") or [])
        obs.append(item)
        return obs

    def _plan_node(self, state: AgentGraphState) -> AgentGraphState:
        if state.get("done"):
            return {}

        req = state["req"]
        db = state["db"]
        run_id = state["run_id"]
        scope = state["scope"]
        step = int(state.get("step") or 0)
        max_steps = int(state.get("max_steps") or 20)
        top_k = int(state.get("top_k") or 5)
        observations = state.get("observations") or []
        last_tagged_contexts = state.get("last_tagged_contexts") or []
        last_citations = state.get("last_citations") or []
        citations = state.get("citations") or []

        if step >= max_steps:
            return {"done": True}

        if self._should_break_loop(observations, last_tagged_contexts):
            llm_resp = self.answer_tool.answer(req.message, last_tagged_contexts[:top_k])
            obs = self._append_observation(state, {"tool": "answer_with_context", "mode": "loop_break"})
            return {
                "answer_text": llm_resp.get("answer") or "",
                "provider": llm_resp.get("provider"),
                "model": llm_resp.get("model"),
                "citations": last_citations or citations,
                "observations": obs,
                "done": True,
            }

        plan = plan_next_step(
            user_message=req.message,
            scope=scope.to_json(),
            observations=observations,
            max_doc_picks=5,
            top_k=top_k,
        )
        next_step = step + 1
        self._add_step(
            db,
            run_id=run_id,
            idx=next_step,
            kind="plan",
            payload={"action": plan.action, "args": plan.args, "rationale": plan.rationale},
        )
        return {
            "step": next_step,
            "plan_action": plan.action,
            "plan_args": plan.args,
            "plan_rationale": plan.rationale,
        }

    def _act_node(self, state: AgentGraphState) -> AgentGraphState:
        if state.get("done"):
            return {}

        req = state["req"]
        db = state["db"]
        scope = state["scope"]
        top_k = int(state.get("top_k") or 5)
        action = str(state.get("plan_action") or "")
        args = state.get("plan_args") or {}
        observations = state.get("observations") or []
        routed_doc_ids = list(state.get("routed_doc_ids") or [])
        last_contexts = list(state.get("last_contexts") or [])
        last_tagged_contexts = list(state.get("last_tagged_contexts") or [])
        last_citations = list(state.get("last_citations") or [])
        citations = list(state.get("citations") or [])

        if action == "final":
            return {
                "answer_text": args.get("answer") or "OK.",
                "provider": "planner",
                "model": None,
                "citations": [AgentCitation(chunk_id=None, metadata={"source": "planner", "kind": "final"})],
                "done": True,
            }

        if action == "answer_with_context" and args.get("answer"):
            out_cites = citations or last_citations or [
                AgentCitation(chunk_id=None, metadata={"source": "planner", "kind": "final"})
            ]
            obs = self._append_observation(state, {"tool": "answer_with_context", "mode": "planner_answer"})
            return {
                "answer_text": normalize_citation_tags(str(args.get("answer") or "")),
                "provider": "planner",
                "model": None,
                "citations": out_cites,
                "observations": obs,
                "done": True,
            }

        if action == "list_documents":
            list_answer, list_citations, contexts = self._answer_list_documents(req.message, scope=scope, db=db)
            if contexts:
                last_contexts = contexts
                last_tagged_contexts, citations = self._tag_contexts(contexts)
                last_citations = citations
                doc_index = [
                    {"tag": c.tag, "document_id": (c.metadata or {}).get("document_id")}
                    for c in citations
                    if c.tag and (c.metadata or {}).get("document_id")
                ]
            else:
                doc_index = []
            obs = self._append_observation(
                state,
                {
                    "tool": "list_documents",
                    "count": len(list_citations),
                    "context_ready": bool(contexts),
                    "doc_index": doc_index,
                    "preview": list_answer[:300],
                },
            )
            return {
                "observations": obs,
                "last_contexts": last_contexts,
                "last_tagged_contexts": last_tagged_contexts,
                "last_citations": last_citations,
                "citations": citations,
            }

        if action == "get_document_profile":
            doc_arg = args.get("document_id")
            resolved_doc_id = self._resolve_doc_id_arg(doc_arg, last_citations)
            if resolved_doc_id:
                temp_scope = AgentScope(
                    project_id=scope.project_id,
                    project_ids=scope.project_ids,
                    folder_id=scope.folder_id,
                    kb_id=scope.kb_id,
                    document_id=resolved_doc_id,
                )
                list_answer, list_citations, contexts = self._answer_list_documents(req.message, scope=temp_scope, db=db)
            else:
                list_answer, list_citations, contexts = self._answer_list_documents(req.message, scope=scope, db=db)
            if contexts:
                last_contexts = contexts
                last_tagged_contexts, citations = self._tag_contexts(contexts)
                last_citations = citations
            obs = self._append_observation(
                state,
                {
                    "tool": "get_document_profile",
                    "count": len(list_citations),
                    "context_ready": bool(contexts),
                    "preview": list_answer[:300],
                },
            )
            return {
                "observations": obs,
                "last_contexts": last_contexts,
                "last_tagged_contexts": last_tagged_contexts,
                "last_citations": last_citations,
                "citations": citations,
            }

        if action == "route_documents":
            if scope.document_id:
                obs = self._append_observation(
                    state,
                    {"tool": "route_documents", "skipped": True, "reason": "document_id is set"},
                )
                return {"observations": obs}
            if not scope.kb_id:
                obs = self._append_observation(
                    state,
                    {"tool": "route_documents", "skipped": True, "reason": "kb_id is missing"},
                )
                return {"observations": obs}
            routed_doc_ids = self._route_documents(req.message, kb_id=scope.kb_id, db=db)
            routed_doc_ids = [
                d
                for d in routed_doc_ids
                if re.match(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$", d)
            ]
            obs = self._append_observation(state, {"tool": "route_documents", "picked": routed_doc_ids})
            return {"observations": obs, "routed_doc_ids": routed_doc_ids}

        if action == "vector_search":
            q = args.get("query") or req.message
            doc_id = scope.document_id
            if not doc_id and args.get("document_id"):
                doc_id = str(args.get("document_id"))
                if scope.kb_id:
                    doc = db.get(models.Document, doc_id)
                    if not doc or (doc.kb_id and doc.kb_id != scope.kb_id):
                        obs = self._append_observation(state, {"tool": "vector_search", "error": "document_id not in kb scope"})
                        return {"observations": obs}
                else:
                    obs = self._append_observation(state, {"tool": "vector_search", "error": "missing kb_id for document filter"})
                    return {"observations": obs}

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
            last_tagged_contexts, citations = self._tag_contexts(last_contexts)
            last_citations = citations
            obs = self._append_observation(
                state,
                {
                    "tool": "vector_search",
                    "matches": len(last_contexts),
                    "top": [{"chunk_id": c.chunk_id, "score": c.score} for c in last_contexts[:5]],
                },
            )
            if last_contexts:
                llm_resp = self.answer_tool.answer(req.message, last_tagged_contexts[:top_k])
                obs = self._append_observation(
                    {"observations": obs},
                    {"tool": "answer_with_context", "provider": llm_resp.get("provider"), "model": llm_resp.get("model")},
                )
                return {
                    "observations": obs,
                    "last_contexts": last_contexts,
                    "last_tagged_contexts": last_tagged_contexts,
                    "last_citations": last_citations,
                    "citations": citations,
                    "answer_text": llm_resp.get("answer") or "",
                    "provider": llm_resp.get("provider"),
                    "model": llm_resp.get("model"),
                    "done": True,
                }
            return {
                "observations": obs,
                "last_contexts": last_contexts,
                "last_tagged_contexts": last_tagged_contexts,
                "last_citations": last_citations,
                "citations": citations,
            }

        if action == "keyword_search":
            q = args.get("query") or req.message
            doc_id = scope.document_id
            if not doc_id and args.get("document_id"):
                doc_id = str(args.get("document_id"))
                if scope.kb_id:
                    doc = db.get(models.Document, doc_id)
                    if not doc or (doc.kb_id and doc.kb_id != scope.kb_id):
                        obs = self._append_observation(state, {"tool": "keyword_search", "error": "document_id not in kb scope"})
                        return {"observations": obs}
                else:
                    obs = self._append_observation(state, {"tool": "keyword_search", "error": "missing kb_id for document filter"})
                    return {"observations": obs}

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
            last_tagged_contexts, citations = self._tag_contexts(results)
            last_citations = citations
            obs = self._append_observation(
                state,
                {
                    "tool": "keyword_search",
                    "matches": len(results),
                    "top": [{"chunk_id": r.chunk_id, "score": r.score, "matches": r.matches[:5]} for r in results[:5]],
                },
            )
            if results:
                llm_resp = self.answer_tool.answer(req.message, last_tagged_contexts[:top_k])
                obs = self._append_observation(
                    {"observations": obs},
                    {"tool": "answer_with_context", "provider": llm_resp.get("provider"), "model": llm_resp.get("model")},
                )
                return {
                    "observations": obs,
                    "last_contexts": last_contexts,
                    "last_tagged_contexts": last_tagged_contexts,
                    "last_citations": last_citations,
                    "citations": citations,
                    "answer_text": llm_resp.get("answer") or "",
                    "provider": llm_resp.get("provider"),
                    "model": llm_resp.get("model"),
                    "done": True,
                }
            return {
                "observations": obs,
                "last_contexts": last_contexts,
                "last_tagged_contexts": last_tagged_contexts,
                "last_citations": last_citations,
                "citations": citations,
            }

        if action == "grep_search":
            q = args.get("query") or req.message
            doc_id = scope.document_id
            if not doc_id and args.get("document_id"):
                doc_id = str(args.get("document_id"))
                if scope.kb_id:
                    doc = db.get(models.Document, doc_id)
                    if not doc or (doc.kb_id and doc.kb_id != scope.kb_id):
                        obs = self._append_observation(state, {"tool": "grep_search", "error": "document_id not in kb scope"})
                        return {"observations": obs}
                else:
                    obs = self._append_observation(state, {"tool": "grep_search", "error": "missing kb_id for document filter"})
                    return {"observations": obs}

            results = self.grep_tool.search(
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
            last_tagged_contexts, citations = self._tag_contexts(results)
            last_citations = citations
            obs = self._append_observation(
                state,
                {
                    "tool": "grep_search",
                    "query": q,
                    "matches": len(results),
                    "top": [
                        {
                            "chunk_id": r.chunk_id,
                            "score": r.score,
                            "sample_matches": [m.get("match") for m in (r.matches or [])[:5]],
                        }
                        for r in results[:5]
                    ],
                },
            )
            if results:
                llm_resp = self.answer_tool.answer(req.message, last_tagged_contexts[:top_k])
                obs = self._append_observation(
                    {"observations": obs},
                    {"tool": "answer_with_context", "provider": llm_resp.get("provider"), "model": llm_resp.get("model")},
                )
                return {
                    "observations": obs,
                    "last_contexts": last_contexts,
                    "last_tagged_contexts": last_tagged_contexts,
                    "last_citations": last_citations,
                    "citations": citations,
                    "answer_text": llm_resp.get("answer") or "",
                    "provider": llm_resp.get("provider"),
                    "model": llm_resp.get("model"),
                    "done": True,
                }
            return {
                "observations": obs,
                "last_contexts": last_contexts,
                "last_tagged_contexts": last_tagged_contexts,
                "last_citations": last_citations,
                "citations": citations,
            }

        if action == "web_search":
            q = args.get("query") or req.message
            api_key = os.environ.get("GOOGLE_SEARCH_API_KEY", "").strip()
            cse_id = os.environ.get("GOOGLE_CSE_ID", "").strip()
            if not api_key or not cse_id:
                obs = self._append_observation(
                    state,
                    {"tool": "web_search", "error": "missing GOOGLE_SEARCH_API_KEY or GOOGLE_CSE_ID"},
                )
                return {"observations": obs}
            results = self.web_tool.search(q, api_key=api_key, cse_id=cse_id, top_k=top_k)
            last_contexts = results
            last_tagged_contexts, citations = self._tag_contexts(results)
            obs = self._append_observation(
                state,
                {
                    "tool": "web_search",
                    "matches": len(results),
                    "top": [{"title": r.metadata.get("title"), "url": r.metadata.get("url")} for r in results[:5]],
                },
            )
            if results:
                llm_resp = self.answer_tool.answer(req.message, last_tagged_contexts[:top_k])
                obs = self._append_observation(
                    {"observations": obs},
                    {"tool": "answer_with_context", "provider": llm_resp.get("provider"), "model": llm_resp.get("model")},
                )
                return {
                    "observations": obs,
                    "last_contexts": last_contexts,
                    "last_tagged_contexts": last_tagged_contexts,
                    "citations": citations,
                    "answer_text": llm_resp.get("answer") or "",
                    "provider": llm_resp.get("provider"),
                    "model": llm_resp.get("model"),
                    "done": True,
                }
            return {
                "observations": obs,
                "last_contexts": last_contexts,
                "last_tagged_contexts": last_tagged_contexts,
                "citations": citations,
            }

        if action == "answer_with_context":
            if not last_contexts:
                obs = self._append_observation(state, {"tool": "answer_with_context", "error": "no_contexts"})
                return {"observations": obs}
            llm_contexts = (
                last_tagged_contexts[:top_k]
                if last_tagged_contexts
                else [
                    {"chunk_id": c.chunk_id, "text": c.text, "score": c.score, "metadata": c.metadata or {}}
                    for c in last_contexts[:top_k]
                ]
            )
            llm_resp = self.answer_tool.answer(req.message, llm_contexts)
            obs = self._append_observation(
                state,
                {"tool": "answer_with_context", "provider": llm_resp.get("provider"), "model": llm_resp.get("model")},
            )
            return {
                "observations": obs,
                "answer_text": llm_resp.get("answer") or "",
                "provider": llm_resp.get("provider"),
                "model": llm_resp.get("model"),
                "done": True,
            }

        obs = self._append_observation(state, {"tool": "unknown", "action": action})
        return {"observations": obs}

    def _resolve_scope_kb(self, scope: AgentScope, *, db: Session) -> AgentScope:
        if scope.document_id and not scope.kb_id:
            doc = db.get(models.Document, scope.document_id)
            if doc and doc.kb_id:
                return AgentScope(
                    project_id=scope.project_id,
                    project_ids=scope.project_ids,
                    folder_id=scope.folder_id,
                    kb_id=doc.kb_id,
                    document_id=scope.document_id,
                )
        return scope
