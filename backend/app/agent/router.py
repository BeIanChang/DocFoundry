from __future__ import annotations

import os

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.agent.langgraph_orchestrator import AgentLangGraphOrchestrator
from app.agent.orchestrator import AgentOrchestrator
from app.agent.schemas import AgentQueryRequest, AgentQueryResponse, AgentRetryRequest, AgentRunRead, AgentCitation, AgentStepRead
from app.api.auth import get_current_user
from app.db.session import get_session
from app.db import models

router = APIRouter(prefix="/agent", tags=["agent"])

_classic_orchestrator = AgentOrchestrator()
_langgraph_orchestrator = AgentLangGraphOrchestrator()


def _resolve_engine(loop_engine: str | None) -> str:
    requested = (loop_engine or os.environ.get("AGENT_LOOP_ENGINE") or "classic").strip().lower()
    if requested in {"classic", "langgraph"}:
        return requested
    return "classic"


def _pick_orchestrator(loop_engine: str | None):
    engine = _resolve_engine(loop_engine)
    if engine == "langgraph":
        if not _langgraph_orchestrator.is_available():
            raise HTTPException(
                status_code=500,
                detail="langgraph engine requested but dependency is not installed; use classic or install langgraph",
            )
        return _langgraph_orchestrator
    return _classic_orchestrator


@router.post("/query", response_model=AgentQueryResponse)
def agent_query(payload: AgentQueryRequest, db: Session = Depends(get_session), user=Depends(get_current_user)):
    orchestrator = _pick_orchestrator(payload.loop_engine)
    return orchestrator.run(payload, db=db, user=user)


@router.get("/runs/{run_id}", response_model=AgentRunRead)
def get_run(run_id: str, db: Session = Depends(get_session), user=Depends(get_current_user)):
    run = db.get(models.AgentRun, run_id)
    if not run:
        raise HTTPException(status_code=404, detail="run not found")
    if run.user_id and run.user_id != user.get("id"):
        raise HTTPException(status_code=404, detail="run not found")
    steps = (
        db.query(models.AgentStep)
        .filter(models.AgentStep.run_id == run.id)
        .order_by(models.AgentStep.idx.asc(), models.AgentStep.created_at.asc())
        .all()
    )
    return AgentRunRead(
        id=run.id,
        user_id=run.user_id,
        message=run.message,
        scope=run.scope or {},
        mode=run.mode,
        status=run.status,
        final_answer=run.final_answer,
        provider=run.provider,
        model=run.model,
        citations=[AgentCitation(**c) for c in (run.citations or [])],
        created_at=run.created_at,
        steps=[AgentStepRead(index=s.idx, kind=s.kind, payload=s.payload or {}, created_at=s.created_at) for s in steps],
    )


@router.post("/runs/{run_id}/retry", response_model=AgentQueryResponse)
def retry_run(run_id: str, payload: AgentRetryRequest, db: Session = Depends(get_session), user=Depends(get_current_user)):
    prev = db.get(models.AgentRun, run_id)
    if not prev:
        raise HTTPException(status_code=404, detail="run not found")
    if prev.user_id and prev.user_id != user.get("id"):
        raise HTTPException(status_code=404, detail="run not found")
    req = AgentQueryRequest(
        message=payload.message or prev.message,
        project_id=(prev.scope or {}).get("project_id"),
        project_ids=(prev.scope or {}).get("project_ids") or None,
        folder_id=(prev.scope or {}).get("folder_id"),
        kb_id=(prev.scope or {}).get("kb_id"),
        document_id=(prev.scope or {}).get("document_id"),
        top_k=payload.top_k,
        max_steps=payload.max_steps,
        mode=payload.mode,
        loop_engine=payload.loop_engine,
        return_steps=payload.return_steps,
    )
    orchestrator = _pick_orchestrator(req.loop_engine)
    return orchestrator.run(req, db=db, user=user)
