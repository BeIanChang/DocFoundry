from pydantic import BaseModel
from typing import Optional, Any
from datetime import datetime


class KnowledgeBaseCreate(BaseModel):
    project_id: Optional[str]
    name: str
    description: Optional[str] = None


class KnowledgeBaseRead(BaseModel):
    id: str
    project_id: Optional[str]
    name: str
    description: Optional[str]
    metadata: Optional[Any]
    created_at: datetime

    class Config:
        orm_mode = True


class KnowledgeBaseUpdate(BaseModel):
    name: Optional[str]
    description: Optional[str]
    visibility: Optional[str]


class DocumentCreate(BaseModel):
    kb_id: Optional[str]
    title: str


class DocumentRead(BaseModel):
    id: str
    kb_id: Optional[str]
    title: str
    metadata: Optional[Any]
    created_at: datetime

    class Config:
        orm_mode = True


class DocumentUpdate(BaseModel):
    title: Optional[str]
    status: Optional[str]
    metadata: Optional[Any]
