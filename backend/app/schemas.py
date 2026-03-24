from pydantic import BaseModel, ConfigDict
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

    model_config = ConfigDict(from_attributes=True)


class KnowledgeBaseUpdate(BaseModel):
    name: Optional[str]
    description: Optional[str]
    visibility: Optional[str]


class DocumentCreate(BaseModel):
    kb_id: Optional[str]
    title: Optional[str] = None
    folder_id: Optional[str] = None


class DocumentRead(BaseModel):
    id: str
    kb_id: Optional[str]
    title: str
    metadata: Optional[Any]
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class DocumentUpdate(BaseModel):
    title: Optional[str]
    status: Optional[str]
    metadata: Optional[Any]


class DocumentProfileUpdate(BaseModel):
    title: Optional[str]
    file_name: Optional[str]
    doc_type: Optional[str]
    year_start: Optional[int]
    year_end: Optional[int]
    summary: Optional[str]
    tags: Optional[Any]
    meta: Optional[Any]
