from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from sqlalchemy.orm import Session
from typing import List

from app.db.session import get_session
from app.db import models
from app.schemas import DocumentCreate, DocumentRead, DocumentUpdate
from app.parsers.chunker import chunk_text
from app.embeddings import vector_store
from app.agent.profiling import generate_document_profile

router = APIRouter(prefix="/documents", tags=["documents"])


@router.post("/", response_model=DocumentRead)
def create_document(payload: DocumentCreate, db: Session = Depends(get_session)):
    # validate kb_id if provided
    if payload.kb_id:
        kb = db.get(models.KnowledgeBase, payload.kb_id)
        if not kb:
            raise HTTPException(status_code=404, detail="knowledge base not found")

    doc = models.Document(
        title=payload.title,
        kb_id=payload.kb_id,
    )
    try:
        db.add(doc)
        db.commit()
        db.refresh(doc)
    except Exception as exc:
        # provide better error message in dev when DB constraints fail
        raise HTTPException(status_code=400, detail=f"failed to create document: {exc}")
    return {
        "id": doc.id,
        "kb_id": doc.kb_id,
        "title": doc.title,
        # Document currently has no instance-level 'metadata' column defined in models
        "metadata": None,
        "created_at": doc.created_at.isoformat() if doc.created_at else None,
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
            "metadata": None,
            "created_at": d.created_at.isoformat() if d.created_at else None,
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
        "metadata": None,
        "created_at": doc.created_at.isoformat() if doc.created_at else None,
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
        "metadata": None,
        "created_at": doc.created_at.isoformat() if doc.created_at else None,
    }


@router.delete("/{doc_id}")
def delete_document(doc_id: str, db: Session = Depends(get_session)):
    doc = db.get(models.Document, doc_id)
    if not doc:
        raise HTTPException(status_code=404, detail="document not found")
    db.delete(doc)
    db.commit()
    return {"status": "deleted"}


@router.post("/{doc_id}/upload")
async def upload_document_file(doc_id: str, file: UploadFile = File(...), db: Session = Depends(get_session)):
    """Upload a file for an existing document, parse it, create a new DocumentVersion and chunk entries."""
    doc = db.get(models.Document, doc_id)
    if not doc:
        raise HTTPException(status_code=404, detail="document not found")

    data = await file.read()
    try:
        from app.parsers.pdf_parser import parse_file

        text = parse_file(file.filename, data)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"failed to parse file: {e}")

    # determine next version number
    try:
        last_ver = db.query(models.DocumentVersion).filter(models.DocumentVersion.document_id == doc_id).order_by(models.DocumentVersion.version_number.desc()).first()
        next_ver = 1 if not last_ver else (last_ver.version_number + 1)
    except Exception:
        next_ver = 1

    version = models.DocumentVersion(document_id=doc_id, version_number=next_ver, file_name=file.filename)
    db.add(version)
    db.commit()
    db.refresh(version)

    # chunk and store
    chunks = chunk_text(text)
    chunk_models = []
    for c in chunks:
        ch = models.Chunk(version_id=version.id, text=c["text"], start_pos=c["start_pos"], end_pos=c["end_pos"], meta=None)
        db.add(ch)
        chunk_models.append(ch)

    db.commit()
    # ensure IDs populated
    for ch in chunk_models:
        db.refresh(ch)

    # push embeddings to vector store with metadata for filtering
    try:
        vector_store.add_documents([
            {
                "id": ch.id,
                "text": ch.text,
                "metadata": {
                    "kb_id": doc.kb_id,
                    "document_id": doc.id,
                    "version_id": version.id,
                    "start_pos": ch.start_pos,
                    "end_pos": ch.end_pos,
                },
            }
            for ch in chunk_models
        ])
    except Exception:
        # embeddings are optional in dev; ignore failures
        pass

    # generate a lightweight searchable profile for this version
    try:
        prof = generate_document_profile(title=doc.title or "", file_name=file.filename, text=text)
        db.add(
            models.DocumentProfile(
                document_id=doc.id,
                version_id=version.id,
                title=doc.title,
                file_name=file.filename,
                doc_type=prof.doc_type,
                year_start=prof.year_start,
                year_end=prof.year_end,
                summary=prof.summary,
                tags=prof.tags,
                meta=prof.meta,
            )
        )
        db.commit()
    except Exception:
        # profiling is best-effort in dev
        pass

    return {"version_id": version.id, "chunks_created": len(chunks)}


@router.get("/{doc_id}/profile")
def get_document_profile(doc_id: str, db: Session = Depends(get_session)):
    """Return the latest profile for the document (if available)."""
    doc = db.get(models.Document, doc_id)
    if not doc:
        raise HTTPException(status_code=404, detail="document not found")

    ver = (
        db.query(models.DocumentVersion)
        .filter(models.DocumentVersion.document_id == doc_id)
        .order_by(models.DocumentVersion.version_number.desc())
        .first()
    )
    if not ver:
        raise HTTPException(status_code=404, detail="document has no versions")

    profile = (
        db.query(models.DocumentProfile)
        .filter(models.DocumentProfile.version_id == ver.id)
        .order_by(models.DocumentProfile.created_at.desc())
        .first()
    )
    if not profile:
        return {
            "document_id": doc_id,
            "version_id": ver.id,
            "title": doc.title,
            "file_name": ver.file_name,
            "doc_type": None,
            "year_start": None,
            "year_end": None,
            "summary": None,
            "tags": [],
            "meta": {"status": "missing"},
        }

    return {
        "document_id": profile.document_id,
        "version_id": profile.version_id,
        "title": profile.title,
        "file_name": profile.file_name,
        "doc_type": profile.doc_type,
        "year_start": profile.year_start,
        "year_end": profile.year_end,
        "summary": profile.summary,
        "tags": profile.tags or [],
        "meta": profile.meta or {},
        "created_at": profile.created_at.isoformat() if profile.created_at else None,
    }
