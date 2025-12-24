from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field


AgentMode = Literal["auto", "answer", "summarize", "extract"]


class AgentQueryRequest(BaseModel):
    message: str = Field(..., min_length=1)
    project_id: Optional[str] = None
    kb_id: Optional[str] = None
    document_id: Optional[str] = None
    top_k: int = 5
    max_steps: int = 4
    mode: AgentMode = "auto"
    return_steps: bool = True


class AgentCitation(BaseModel):
    chunk_id: Optional[str]
    score: Optional[float] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)
    text_preview: Optional[str] = None


class AgentStepRead(BaseModel):
    index: int
    kind: str
    payload: Dict[str, Any]
    created_at: Optional[datetime] = None


class AgentQueryResponse(BaseModel):
    run_id: str
    answer: str
    provider: Optional[str] = None
    model: Optional[str] = None
    citations: List[AgentCitation] = Field(default_factory=list)
    steps: Optional[List[AgentStepRead]] = None


class AgentRunRead(BaseModel):
    id: str
    user_id: Optional[str] = None
    message: str
    scope: Dict[str, Any] = Field(default_factory=dict)
    mode: str
    status: str
    final_answer: Optional[str] = None
    provider: Optional[str] = None
    model: Optional[str] = None
    citations: List[AgentCitation] = Field(default_factory=list)
    created_at: Optional[datetime] = None
    steps: List[AgentStepRead] = Field(default_factory=list)


class AgentRetryRequest(BaseModel):
    message: Optional[str] = None
    top_k: int = 5
    max_steps: int = 4
    mode: AgentMode = "auto"
    return_steps: bool = True

