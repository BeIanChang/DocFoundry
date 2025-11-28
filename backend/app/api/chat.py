from typing import List
from fastapi import APIRouter, HTTPException, Depends

from app.db import models
from app.db.session import get_session
from app.api.rag import rag_query
from app.api.auth import get_current_user

router = APIRouter(prefix="/chat", tags=["chat"])


def _serialize_session(s: models.ChatSession):
    return {
        "id": s.id,
        "user_id": s.user_id,
        "kb_id": s.kb_id,
        "started_at": s.started_at.isoformat() if s.started_at else None,
        "meta": s.meta,
    }


@router.post("/sessions", response_model=dict)
def create_session(payload: dict, db=Depends(get_session), user=Depends(get_current_user)):
    kb_id = payload.get("kb_id")
    if kb_id:
        kb = db.get(models.KnowledgeBase, kb_id)
        if not kb:
            raise HTTPException(status_code=404, detail="knowledge base not found")
    # user_id is nullable in the schema; avoid FK issues with in-memory auth users
    session = models.ChatSession(user_id=None, kb_id=kb_id, meta=payload.get("meta"))
    db.add(session)
    db.commit()
    db.refresh(session)
    return _serialize_session(session)


@router.get("/sessions", response_model=List[dict])
def list_sessions(db=Depends(get_session), user=Depends(get_current_user)):
    sessions = (
        db.query(models.ChatSession)
        .filter(models.ChatSession.user_id == user["id"])
        .order_by(models.ChatSession.started_at.desc())
        .all()
    )
    return [_serialize_session(s) for s in sessions]


@router.post("/sessions/{session_id}/messages", response_model=dict)
def post_message(session_id: str, payload: dict, db=Depends(get_session), user=Depends(get_current_user)):
    session = db.get(models.ChatSession, session_id)
    if not session:
        raise HTTPException(status_code=404, detail="chat session not found")
    if session.user_id and session.user_id != user["id"]:
        raise HTTPException(status_code=404, detail="chat session not found for this user")
    question = payload.get("query") or payload.get("message")
    if not question:
        raise HTTPException(status_code=400, detail="query/message is required")

    # store user message
    user_msg = models.ChatMessage(session_id=session.id, sender=user["email"], role="user", content=question)
    db.add(user_msg)
    db.commit()
    db.refresh(user_msg)

    # call RAG; filter by kb if present
    rag_payload = {
        "query": question,
        "kb_id": session.kb_id,
        "document_id": payload.get("document_id"),
        "top_k": payload.get("top_k") or 5,
    }
    rag_resp = rag_query(rag_payload, db=db)

    # store assistant message
    answer_text = rag_resp.get("answer") or ""
    asst_msg = models.ChatMessage(session_id=session.id, sender="assistant", role="assistant", content=answer_text)
    db.add(asst_msg)
    db.commit()
    db.refresh(asst_msg)

    return {
        "session": _serialize_session(session),
        "question": {"id": user_msg.id, "content": user_msg.content},
        "answer": {"id": asst_msg.id, "content": asst_msg.content},
        "rag": rag_resp,
    }
