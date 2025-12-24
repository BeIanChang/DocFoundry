import uuid
from sqlalchemy import (
    Column,
    String,
    Integer,
    Text,
    ForeignKey,
    DateTime,
    Boolean,
    JSON,
)
from sqlalchemy.orm import relationship, declarative_base
from sqlalchemy.sql import func

Base = declarative_base()

def gen_uuid():
    return str(uuid.uuid4())


class User(Base):
    __tablename__ = 'users'
    id = Column(String(36), primary_key=True, default=gen_uuid)
    email = Column(String(255), unique=True, nullable=False)
    name = Column(String(255))
    password_hash = Column(String(255))
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class Org(Base):
    __tablename__ = 'orgs'
    id = Column(String(36), primary_key=True, default=gen_uuid)
    name = Column(String(255), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    projects = relationship('Project', back_populates='org')


class Project(Base):
    __tablename__ = 'projects'
    id = Column(String(36), primary_key=True, default=gen_uuid)
    name = Column(String(255), nullable=False)
    org_id = Column(String(36), ForeignKey('orgs.id'), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    org = relationship('Org', back_populates='projects')
    knowledge_bases = relationship('KnowledgeBase', back_populates='project')


class KnowledgeBase(Base):
    __tablename__ = 'knowledge_bases'
    id = Column(String(36), primary_key=True, default=gen_uuid)
    name = Column(String(255), nullable=False)
    project_id = Column(String(36), ForeignKey('projects.id'), nullable=True)
    description = Column(Text)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    project = relationship('Project', back_populates='knowledge_bases')
    documents = relationship('Document', back_populates='knowledge_base')


class Document(Base):
    __tablename__ = 'documents'
    id = Column(String(36), primary_key=True, default=gen_uuid)
    title = Column(String(1024))
    kb_id = Column(String(36), ForeignKey('knowledge_bases.id'), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    knowledge_base = relationship('KnowledgeBase', back_populates='documents')
    versions = relationship('DocumentVersion', back_populates='document')


class DocumentVersion(Base):
    __tablename__ = 'document_versions'
    id = Column(String(36), primary_key=True, default=gen_uuid)
    document_id = Column(String(36), ForeignKey('documents.id'), nullable=False)
    version_number = Column(Integer, default=1)
    file_name = Column(String(1024))
    file_path = Column(String(2048))
    uploaded_at = Column(DateTime(timezone=True), server_default=func.now())
    document = relationship('Document', back_populates='versions')
    chunks = relationship('Chunk', back_populates='version')
    profiles = relationship('DocumentProfile', back_populates='version')


class Chunk(Base):
    __tablename__ = 'chunks'
    id = Column(String(36), primary_key=True, default=gen_uuid)
    version_id = Column(String(36), ForeignKey('document_versions.id'), nullable=False)
    text = Column(Text)
    start_pos = Column(Integer)
    end_pos = Column(Integer)
    meta = Column(JSON)
    version = relationship('DocumentVersion', back_populates='chunks')


class DocumentProfile(Base):
    __tablename__ = "document_profiles"
    id = Column(String(36), primary_key=True, default=gen_uuid)
    document_id = Column(String(36), ForeignKey("documents.id"), nullable=False)
    version_id = Column(String(36), ForeignKey("document_versions.id"), nullable=False)
    title = Column(String(1024))
    file_name = Column(String(1024))
    doc_type = Column(String(128))
    year_start = Column(Integer)
    year_end = Column(Integer)
    summary = Column(Text)
    tags = Column(JSON)
    meta = Column(JSON)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    document = relationship("Document")
    version = relationship("DocumentVersion", back_populates="profiles")


class ChatSession(Base):
    __tablename__ = 'chat_sessions'
    id = Column(String(36), primary_key=True, default=gen_uuid)
    user_id = Column(String(36), ForeignKey('users.id'), nullable=True)
    kb_id = Column(String(36), ForeignKey('knowledge_bases.id'), nullable=True)
    started_at = Column(DateTime(timezone=True), server_default=func.now())
    meta = Column(JSON)
    messages = relationship('ChatMessage', back_populates='session')


class ChatMessage(Base):
    __tablename__ = 'chat_messages'
    id = Column(String(36), primary_key=True, default=gen_uuid)
    session_id = Column(String(36), ForeignKey('chat_sessions.id'), nullable=False)
    sender = Column(String(64))
    role = Column(String(64))
    content = Column(Text)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    order = Column(Integer, default=0)
    session = relationship('ChatSession', back_populates='messages')


class WorkflowDefinition(Base):
    __tablename__ = 'workflow_definitions'
    id = Column(String(36), primary_key=True, default=gen_uuid)
    name = Column(String(255), nullable=False)
    spec = Column(JSON)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class WorkflowJob(Base):
    __tablename__ = 'workflow_jobs'
    id = Column(String(36), primary_key=True, default=gen_uuid)
    workflow_def_id = Column(String(36), ForeignKey('workflow_definitions.id'))
    status = Column(String(64), default='pending')
    input = Column(JSON)
    started_at = Column(DateTime(timezone=True))
    finished_at = Column(DateTime(timezone=True))
    results = relationship('WorkflowResult', back_populates='job')


class WorkflowResult(Base):
    __tablename__ = 'workflow_results'
    id = Column(String(36), primary_key=True, default=gen_uuid)
    workflow_job_id = Column(String(36), ForeignKey('workflow_jobs.id'))
    result = Column(JSON)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    job = relationship('WorkflowJob', back_populates='results')


class IngestionJob(Base):
    __tablename__ = 'ingestion_jobs'
    id = Column(String(36), primary_key=True, default=gen_uuid)
    kb_id = Column(String(36), ForeignKey('knowledge_bases.id'))
    status = Column(String(64), default='pending')
    started_at = Column(DateTime(timezone=True))
    finished_at = Column(DateTime(timezone=True))
    items = relationship('IngestionItem', back_populates='job')


class IngestionItem(Base):
    __tablename__ = 'ingestion_items'
    id = Column(String(36), primary_key=True, default=gen_uuid)
    ingestion_job_id = Column(String(36), ForeignKey('ingestion_jobs.id'))
    document_id = Column(String(36), ForeignKey('documents.id'))
    status = Column(String(64), default='pending')
    detail = Column(JSON)
    job = relationship('IngestionJob', back_populates='items')


class AgentRun(Base):
    __tablename__ = "agent_runs"
    id = Column(String(36), primary_key=True, default=gen_uuid)
    user_id = Column(String(36), ForeignKey("users.id"), nullable=True)
    message = Column(Text, nullable=False)
    scope = Column(JSON)
    mode = Column(String(64), default="auto")
    status = Column(String(64), default="running")
    final_answer = Column(Text)
    provider = Column(String(64))
    model = Column(String(255))
    citations = Column(JSON)
    error = Column(Text)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    steps = relationship("AgentStep", back_populates="run")


class AgentStep(Base):
    __tablename__ = "agent_steps"
    id = Column(String(36), primary_key=True, default=gen_uuid)
    run_id = Column(String(36), ForeignKey("agent_runs.id"), nullable=False)
    idx = Column(Integer, default=0)
    kind = Column(String(64))
    payload = Column(JSON)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    run = relationship("AgentRun", back_populates="steps")
