import os
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.db.session import get_session
from app.db import models

router = APIRouter(prefix="/library", tags=["library"])


def _upload_base_dir() -> Path:
    return Path(os.environ.get("UPLOAD_DIR", "./uploads")).resolve()


def _safe_file_response(path_str: str) -> FileResponse:
    base = _upload_base_dir()
    path = Path(path_str).resolve()
    if not str(path).startswith(str(base)):
        raise HTTPException(status_code=400, detail="invalid file path")
    if not path.exists() or not path.is_file():
        raise HTTPException(status_code=404, detail="file not found")
    return FileResponse(path)


@router.get("/tree", response_model=dict)
def get_tree(db: Session = Depends(get_session)):
    """
    Returns a VSCode-like nested tree:
    projects -> knowledge_bases -> folders/documents -> versions (+ profile/text availability)
    """
    projects = db.query(models.Project).order_by(models.Project.created_at.desc()).all()
    out = {"projects": []}
    for p in projects:
        kb_list = (
            db.query(models.KnowledgeBase)
            .filter(models.KnowledgeBase.project_id == p.id)
            .order_by(models.KnowledgeBase.created_at.desc())
            .all()
        )
        p_item = {"id": p.id, "name": p.name, "knowledge_bases": []}
        for kb in kb_list:
            docs = (
                db.query(models.Document)
                .filter(models.Document.kb_id == kb.id)
                .order_by(models.Document.created_at.desc())
                .all()
            )
            kb_item = {"id": kb.id, "name": kb.name, "documents": []}
            folder_rows = (
                db.query(models.Folder)
                .filter(models.Folder.kb_id == kb.id)
                .order_by(models.Folder.created_at.asc())
                .all()
            )
            folder_nodes = {}
            for f in folder_rows:
                folder_nodes[f.id] = {
                    "id": f.id,
                    "kb_id": f.kb_id,
                    "parent_id": f.parent_id,
                    "name": f.name,
                    "folders": [],
                    "documents": [],
                }
            kb_item["folders"] = []
            for f in folder_rows:
                node = folder_nodes[f.id]
                if f.parent_id and f.parent_id in folder_nodes:
                    folder_nodes[f.parent_id]["folders"].append(node)
                else:
                    kb_item["folders"].append(node)
            for d in docs:
                versions = (
                    db.query(models.DocumentVersion)
                    .filter(models.DocumentVersion.document_id == d.id)
                    .order_by(models.DocumentVersion.version_number.desc())
                    .all()
                )
                d_item = {"id": d.id, "title": d.title, "versions": []}
                for v in versions:
                    has_profile = (
                        db.query(models.DocumentProfile.id)
                        .filter(models.DocumentProfile.version_id == v.id)
                        .first()
                        is not None
                    )
                    has_text = (
                        db.query(models.DocumentVersionText.id)
                        .filter(models.DocumentVersionText.version_id == v.id)
                        .first()
                        is not None
                    )
                    d_item["versions"].append(
                        {
                            "id": v.id,
                            "version_number": v.version_number,
                            "file_name": v.file_name,
                            "uploaded_at": v.uploaded_at.isoformat() if v.uploaded_at else None,
                            "has_raw": bool(v.file_path),
                            "has_text": has_text,
                            "has_profile": has_profile,
                        }
                    )
                if d.folder_id and d.folder_id in folder_nodes:
                    folder_nodes[d.folder_id]["documents"].append(d_item)
                else:
                    kb_item["documents"].append(d_item)
            p_item["knowledge_bases"].append(kb_item)
        out["projects"].append(p_item)
    return out


@router.get("/versions/{version_id}", response_model=dict)
def get_version(version_id: str, db: Session = Depends(get_session)):
    v = db.get(models.DocumentVersion, version_id)
    if not v:
        raise HTTPException(status_code=404, detail="version not found")
    doc = db.get(models.Document, v.document_id) if v.document_id else None
    return {
        "id": v.id,
        "document_id": v.document_id,
        "kb_id": doc.kb_id if doc else None,
        "version_number": v.version_number,
        "file_name": v.file_name,
        "file_path": v.file_path,
        "uploaded_at": v.uploaded_at.isoformat() if v.uploaded_at else None,
    }


@router.get("/versions/{version_id}/raw")
def get_version_raw(version_id: str, db: Session = Depends(get_session)):
    v = db.get(models.DocumentVersion, version_id)
    if not v:
        raise HTTPException(status_code=404, detail="version not found")
    if not v.file_path:
        raise HTTPException(status_code=404, detail="no raw file stored for this version")
    return _safe_file_response(v.file_path)


@router.get("/versions/{version_id}/text", response_model=dict)
def get_version_text(version_id: str, db: Session = Depends(get_session)):
    t = db.query(models.DocumentVersionText).filter(models.DocumentVersionText.version_id == version_id).first()
    if not t:
        raise HTTPException(status_code=404, detail="no parsed text stored for this version")
    return {"version_id": version_id, "document_id": t.document_id, "text": t.text}
