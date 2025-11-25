from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List

from app.db.session import get_session
from app.db import models
from app.schemas import DocumentCreate, DocumentRead, DocumentUpdate

router = APIRouter(prefix="/documents", tags=["documents"])


@router.post("/", response_model=DocumentRead)
def create_document(payload: DocumentCreate, db: Session = Depends(get_session)):
    doc = models.Document(
        title=payload.title,
        kb_id=payload.kb_id,
    )
    db.add(doc)
    db.commit()
    db.refresh(doc)
    return {
        "id": doc.id,
        "kb_id": doc.kb_id,
        "title": doc.title,
        "metadata": getattr(doc, "metadata", None),
        "created_at": doc.created_at,
    }


@router.get("/", response_model=List[DocumentRead])
def list_documents(kb_id: str = None, db: Session = Depends(get_session)):
    q = db.query(models.Document)
    if kb_id:
        q = q.filter(models.Document.kb_id == kb_id)
    results = q.order_by(models.Document.created_at.desc()).all()
    out = []
    for d in results:
        out.append({
            "id": d.id,
            "kb_id": d.kb_id,
            "title": d.title,
            "metadata": getattr(d, "metadata", None),
            "created_at": d.created_at,
        })
    return out


@router.get("/{doc_id}", response_model=DocumentRead)
def get_document(doc_id: str, db: Session = Depends(get_session)):
    doc = db.get(models.Document, doc_id)
    if not doc:
        raise HTTPException(status_code=404, detail="document not found")
    return {
        "id": doc.id,
        "kb_id": doc.kb_id,
        "title": doc.title,
        "metadata": getattr(doc, "metadata", None),
        "created_at": doc.created_at,
    }


@router.put("/{doc_id}", response_model=DocumentRead)
def update_document(doc_id: str, payload: DocumentUpdate, db: Session = Depends(get_session)):
    doc = db.get(models.Document, doc_id)
    if not doc:
        raise HTTPException(status_code=404, detail="document not found")
    allowed = {'title', 'status', 'metadata'}
    for field, val in payload.dict(exclude_unset=True).items():
        if field in allowed:
            setattr(doc, field, val)
    db.add(doc)
    db.commit()
    db.refresh(doc)
    return {
        "id": doc.id,
        "kb_id": doc.kb_id,
        "title": doc.title,
        "metadata": getattr(doc, "metadata", None),
        "created_at": doc.created_at,
    }


@router.delete("/{doc_id}")
def delete_document(doc_id: str, db: Session = Depends(get_session)):
    doc = db.get(models.Document, doc_id)
    if not doc:
        raise HTTPException(status_code=404, detail="document not found")
    db.delete(doc)
    db.commit()
    return {"status": "deleted"}
