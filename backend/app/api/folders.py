from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List, Optional

from app.db.session import get_session
from app.db import models

router = APIRouter(prefix="/folders", tags=["folders"])


@router.post("/", response_model=dict)
def create_folder(payload: dict, db: Session = Depends(get_session)):
    kb_id = payload.get("kb_id")
    name = (payload.get("name") or "").strip()
    parent_id = payload.get("parent_id")
    if not kb_id or not name:
        raise HTTPException(status_code=400, detail="kb_id and name are required")
    kb = db.get(models.KnowledgeBase, kb_id)
    if not kb:
        raise HTTPException(status_code=404, detail="knowledge base not found")
    if parent_id:
        parent = db.get(models.Folder, parent_id)
        if not parent or parent.kb_id != kb_id:
            raise HTTPException(status_code=400, detail="invalid parent_id for kb")
    folder = models.Folder(kb_id=kb_id, parent_id=parent_id, name=name)
    db.add(folder)
    db.commit()
    db.refresh(folder)
    return {"id": folder.id, "kb_id": folder.kb_id, "parent_id": folder.parent_id, "name": folder.name}


@router.get("/", response_model=List[dict])
def list_folders(kb_id: Optional[str] = None, db: Session = Depends(get_session)):
    q = db.query(models.Folder)
    if kb_id:
        q = q.filter(models.Folder.kb_id == kb_id)
    folders = q.order_by(models.Folder.created_at.asc()).all()
    return [{"id": f.id, "kb_id": f.kb_id, "parent_id": f.parent_id, "name": f.name} for f in folders]


@router.put("/{folder_id}")
def update_folder(folder_id: str, payload: dict, db: Session = Depends(get_session)):
    folder = db.get(models.Folder, folder_id)
    if not folder:
        raise HTTPException(status_code=404, detail="folder not found")
    if "name" in payload:
        name = (payload.get("name") or "").strip()
        if not name:
            raise HTTPException(status_code=400, detail="name cannot be empty")
        folder.name = name
    db.add(folder)
    db.commit()
    db.refresh(folder)
    return {"id": folder.id, "kb_id": folder.kb_id, "parent_id": folder.parent_id, "name": folder.name}


@router.delete("/{folder_id}")
def delete_folder(folder_id: str, db: Session = Depends(get_session)):
    folder = db.get(models.Folder, folder_id)
    if not folder:
        raise HTTPException(status_code=404, detail="folder not found")
    has_children = db.query(models.Folder.id).filter(models.Folder.parent_id == folder_id).first()
    if has_children:
        raise HTTPException(status_code=400, detail="folder has subfolders")
    has_docs = db.query(models.Document.id).filter(models.Document.folder_id == folder_id).first()
    if has_docs:
        raise HTTPException(status_code=400, detail="folder has documents")
    db.delete(folder)
    db.commit()
    return {"status": "deleted", "folder_id": folder_id}
