from typing import List
from fastapi import APIRouter, HTTPException, Depends

from app.db.session import get_session
from app.db import models

router = APIRouter(prefix="/projects", tags=["projects"])


def _serialize_project(p: models.Project) -> dict:
    return {
        "id": p.id,
        "name": p.name,
        "org_id": p.org_id,
        "created_at": p.created_at.isoformat() if p.created_at else None,
    }


@router.post("/", response_model=dict)
def create_project(payload: dict, db=Depends(get_session)):
    name = (payload.get("name") or "").strip()
    if not name:
        raise HTTPException(status_code=400, detail="name is required")
    proj = models.Project(name=name, org_id=payload.get("org_id"))
    db.add(proj)
    db.commit()
    db.refresh(proj)
    return _serialize_project(proj)


@router.get("/", response_model=List[dict])
def list_projects(db=Depends(get_session)):
    projects = db.query(models.Project).order_by(models.Project.created_at.desc()).all()
    return [_serialize_project(p) for p in projects]


@router.get("/{project_id}", response_model=dict)
def get_project(project_id: str, db=Depends(get_session)):
    proj = db.get(models.Project, project_id)
    if not proj:
        raise HTTPException(status_code=404, detail="project not found")
    return _serialize_project(proj)


@router.put("/{project_id}", response_model=dict)
def update_project(project_id: str, payload: dict, db=Depends(get_session)):
    proj = db.get(models.Project, project_id)
    if not proj:
        raise HTTPException(status_code=404, detail="project not found")
    if "name" in payload:
        name = (payload.get("name") or "").strip()
        if not name:
            raise HTTPException(status_code=400, detail="name cannot be empty")
        proj.name = name
    if "org_id" in payload:
        proj.org_id = payload.get("org_id")
    db.add(proj)
    db.commit()
    db.refresh(proj)
    return _serialize_project(proj)


@router.delete("/{project_id}")
def delete_project(project_id: str, db=Depends(get_session)):
    proj = db.get(models.Project, project_id)
    if not proj:
        raise HTTPException(status_code=404, detail="project not found")
    db.delete(proj)
    db.commit()
    return {"status": "deleted"}
