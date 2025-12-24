from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.agent.orchestrator import AgentOrchestrator
from app.agent.schemas import AgentQueryRequest, AgentQueryResponse, AgentRetryRequest, AgentRunRead, AgentCitation, AgentStepRead
from app.api.auth import get_current_user
from app.db.session import get_session
from app.db import models

router = APIRouter(prefix="/agent", tags=["agent"])

_orchestrator = AgentOrchestrator()


@router.post("/query", response_model=AgentQueryResponse)
def agent_query(payload: AgentQueryRequest, db: Session = Depends(get_session), user=Depends(get_current_user)):
    return _orchestrator.run(payload, db=db, user=user)


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
        kb_id=(prev.scope or {}).get("kb_id"),
        document_id=(prev.scope or {}).get("document_id"),
        top_k=payload.top_k,
        max_steps=payload.max_steps,
        mode=payload.mode,
        return_steps=payload.return_steps,
    )
    return _orchestrator.run(req, db=db, user=user)

