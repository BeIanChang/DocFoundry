from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List

from app.db.session import get_session
from app.db import models
from app.schemas import KnowledgeBaseCreate, KnowledgeBaseRead, KnowledgeBaseUpdate

router = APIRouter(prefix="/kb", tags=["knowledge_bases"])


@router.post("/", response_model=KnowledgeBaseRead)
def create_kb(payload: KnowledgeBaseCreate, db: Session = Depends(get_session)):
    # validate project_id if provided
    if payload.project_id:
        proj = db.get(models.Project, payload.project_id)
        if not proj:
            raise HTTPException(status_code=404, detail="project not found")
    try:
        kb = models.KnowledgeBase(
            project_id=payload.project_id,
            name=payload.name,
            description=payload.description,
        )
        db.add(kb)
        db.commit()
        db.refresh(kb)
    except Exception as exc:
        # In dev mode, return the exception detail so it's easier to debug
        # (In production you'd log and return a generic message)
        raise HTTPException(status_code=500, detail=f"create_kb failed: {exc}")
    return {
        "id": kb.id,
        "project_id": kb.project_id,
        "name": kb.name,
        "description": kb.description,
        "metadata": None,
        "created_at": kb.created_at.isoformat() if kb.created_at else None,
    }


@router.get("/", response_model=List[KnowledgeBaseRead])
def list_kb(project_id: str = None, db: Session = Depends(get_session)):
    q = db.query(models.KnowledgeBase)
    if project_id:
        q = q.filter(models.KnowledgeBase.project_id == project_id)
    results = q.order_by(models.KnowledgeBase.created_at.desc()).all()
    out = []
    for k in results:
        out.append({
            "id": k.id,
            "project_id": k.project_id,
            "name": k.name,
            "description": k.description,
            # KnowledgeBase model does not have an instance-level 'metadata' column
            "metadata": None,
            "created_at": k.created_at.isoformat() if k.created_at else None,
        })
    return out


@router.get("/{kb_id}", response_model=KnowledgeBaseRead)
def get_kb(kb_id: str, db: Session = Depends(get_session)):
    kb = db.get(models.KnowledgeBase, kb_id)
    if not kb:
        raise HTTPException(status_code=404, detail="knowledge base not found")
    return {
        "id": kb.id,
        "project_id": kb.project_id,
        "name": kb.name,
        "description": kb.description,
        "metadata": None,
        "created_at": kb.created_at.isoformat() if kb.created_at else None,
    }


@router.put("/{kb_id}", response_model=KnowledgeBaseRead)
def update_kb(kb_id: str, payload: KnowledgeBaseUpdate, db: Session = Depends(get_session)):
    kb = db.get(models.KnowledgeBase, kb_id)
    if not kb:
        raise HTTPException(status_code=404, detail="knowledge base not found")
    allowed = {'name', 'description'}
    for field, val in payload.dict(exclude_unset=True).items():
        if field in allowed:
            setattr(kb, field, val)
    db.add(kb)
    db.commit()
    db.refresh(kb)
    return {
        "id": kb.id,
        "project_id": kb.project_id,
        "name": kb.name,
        "description": kb.description,
        "metadata": None,
        "created_at": kb.created_at.isoformat() if kb.created_at else None,
    }


@router.delete("/{kb_id}")
def delete_kb(kb_id: str, db: Session = Depends(get_session)):
    kb = db.get(models.KnowledgeBase, kb_id)
    if not kb:
        raise HTTPException(status_code=404, detail="knowledge base not found")
    db.delete(kb)
    db.commit()
    return {"status": "deleted"}
