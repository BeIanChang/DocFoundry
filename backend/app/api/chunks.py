from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db.session import get_session
from app.db import models

router = APIRouter(prefix="/chunks", tags=["chunks"])


@router.get("/{chunk_id}", response_model=dict)
def get_chunk(chunk_id: str, db: Session = Depends(get_session)):
    """
    Fetch a chunk with enough linkage info to drive UI navigation from citations.
    """
    chunk = db.get(models.Chunk, chunk_id)
    if not chunk:
        raise HTTPException(status_code=404, detail="chunk not found")

    version = db.get(models.DocumentVersion, chunk.version_id) if chunk.version_id else None
    document = db.get(models.Document, version.document_id) if version and version.document_id else None

    return {
        "id": chunk.id,
        "text": chunk.text,
        "start_pos": chunk.start_pos,
        "end_pos": chunk.end_pos,
        "meta": chunk.meta,
        "version_id": chunk.version_id,
        "document_id": document.id if document else None,
        "kb_id": document.kb_id if document else None,
        "file_name": version.file_name if version else None,
        "uploaded_at": version.uploaded_at.isoformat() if version and version.uploaded_at else None,
    }

