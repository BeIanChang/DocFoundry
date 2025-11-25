-- DocFoundry detailed SQL schema for Postgres
-- Run this on Postgres (requires 'pgcrypto' extension or 'uuid-ossp')
-- Example: CREATE EXTENSION IF NOT EXISTS pgcrypto;

-- NOTE: This file provides CREATE TABLE statements, indexes and notes.
-- It mirrors the SQLAlchemy models and is intended for dev/seed/migration review.


-- === Extensions & helper ===
-- SELECT version();
CREATE EXTENSION IF NOT EXISTS pgcrypto;
CREATE EXTENSION IF NOT EXISTS citext;
CREATE EXTENSION IF NOT EXISTS pg_trgm; -- optional for similarity search


-- =====================
-- Users / Orgs / Project
-- =====================
CREATE TABLE IF NOT EXISTS orgs (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  name TEXT NOT NULL,
  metadata JSONB DEFAULT '{}'::jsonb,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS users (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  org_id UUID REFERENCES orgs(id) ON DELETE SET NULL,
  email CITEXT UNIQUE NOT NULL,
  password_hash TEXT, -- store bcrypt/argon2 hash
  display_name TEXT,
  role TEXT NOT NULL DEFAULT 'user', -- admin / user
  is_active BOOLEAN NOT NULL DEFAULT true,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  last_login_at TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS idx_users_org ON users(org_id);

CREATE TABLE IF NOT EXISTS projects (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  org_id UUID REFERENCES orgs(id) ON DELETE CASCADE,
  name TEXT NOT NULL,
  description TEXT,
  metadata JSONB DEFAULT '{}'::jsonb,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_projects_org ON projects(org_id);


-- =====================
-- Knowledge Bases & Docs
-- =====================
CREATE TABLE IF NOT EXISTS knowledge_bases (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  project_id UUID REFERENCES projects(id) ON DELETE CASCADE,
  owner_id UUID REFERENCES users(id),
  name TEXT NOT NULL,
  description TEXT,
  visibility TEXT NOT NULL DEFAULT 'private', -- private / org / public
  metadata JSONB DEFAULT '{}'::jsonb,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_kb_project ON knowledge_bases(project_id);

CREATE TABLE IF NOT EXISTS documents (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  kb_id UUID NOT NULL REFERENCES knowledge_bases(id) ON DELETE CASCADE,
  created_by UUID REFERENCES users(id) ON DELETE SET NULL,
  title TEXT NOT NULL,
  doc_type TEXT,
  source_type TEXT NOT NULL DEFAULT 'upload', -- upload/s3/url
  source_uri TEXT,
  status TEXT NOT NULL DEFAULT 'pending', -- pending/parsed/indexed/failed
  error_message TEXT,
  current_version_id UUID, -- set after versions are created
  num_pages INT DEFAULT 0,
  num_chunks INT DEFAULT 0,
  metadata JSONB DEFAULT '{}'::jsonb,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_documents_kb_created ON documents(kb_id, created_at DESC);

CREATE TABLE IF NOT EXISTS document_versions (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  document_id UUID NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
  version_number INT NOT NULL,
  uploaded_by UUID REFERENCES users(id) ON DELETE SET NULL,
  mime_type TEXT,
  storage_backend TEXT, -- local/s3/minio
  storage_path TEXT, -- s3://bucket/key or /data/files/...
  file_size BIGINT,
  checksum TEXT,
  status TEXT NOT NULL DEFAULT 'pending',
  metadata JSONB DEFAULT '{}'::jsonb,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_document_versions_unique ON document_versions(document_id, version_number);

-- document_files is optional; if you want to keep multiple file objects per version, uncomment below
-- CREATE TABLE IF NOT EXISTS document_files (
--   id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
--   document_version_id UUID NOT NULL REFERENCES document_versions(id) ON DELETE CASCADE,
--   storage_backend TEXT NOT NULL,
--   storage_path TEXT NOT NULL,
--   metadata JSONB DEFAULT '{}'::jsonb,
--   created_at TIMESTAMPTZ NOT NULL DEFAULT now()
-- );


-- =====================
-- Chunking & Embeddings
-- =====================
-- Strategy: store chunk text + metadata in Postgres and link embedding ids to an external vector store (Chroma/Pinecone).

CREATE TABLE IF NOT EXISTS chunks (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  document_id UUID REFERENCES documents(id) ON DELETE CASCADE,
  version_id UUID REFERENCES document_versions(id) ON DELETE CASCADE,
  kb_id UUID REFERENCES knowledge_bases(id) ON DELETE CASCADE,
  index_in_doc INT NOT NULL DEFAULT 0,
  page_number INT,
  block_type TEXT,
  text TEXT NOT NULL,
  meta JSONB DEFAULT '{}'::jsonb,
  embedding_id TEXT, -- id in external vector DB
  score DOUBLE PRECISION, -- optional score field if needed for caching
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_chunks_doc_idx ON chunks(document_id, index_in_doc);
CREATE INDEX IF NOT EXISTS idx_chunks_kb ON chunks(kb_id);
CREATE INDEX IF NOT EXISTS idx_chunks_text_trgm ON chunks USING GIN (text gin_trgm_ops);

-- Optional: pgvector storage for embeddings
-- CREATE EXTENSION IF NOT EXISTS vector;
-- CREATE TABLE IF NOT EXISTS chunks_vector (
--   id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
--   version_id UUID REFERENCES document_versions(id) ON DELETE CASCADE,
--   kb_id UUID REFERENCES knowledge_bases(id) ON DELETE CASCADE,
--   text TEXT NOT NULL,
--   embedding vector(1536),
--   meta JSONB DEFAULT '{}'::jsonb,
--   created_at TIMESTAMPTZ NOT NULL DEFAULT now()
-- );
-- CREATE INDEX IF NOT EXISTS idx_chunks_embedding ON chunks_vector USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100);


-- =====================
-- Chat / RAG
-- =====================
CREATE TABLE IF NOT EXISTS chat_sessions (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  kb_id UUID REFERENCES knowledge_bases(id) ON DELETE CASCADE,
  user_id UUID REFERENCES users(id) ON DELETE SET NULL,
  title TEXT,
  related_document_id UUID REFERENCES documents(id),
  metadata JSONB DEFAULT '{}'::jsonb,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_chat_sessions_user ON chat_sessions(user_id, created_at DESC);

CREATE TABLE IF NOT EXISTS chat_messages (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  session_id UUID NOT NULL REFERENCES chat_sessions(id) ON DELETE CASCADE,
  sender TEXT, -- optional sender id
  role TEXT NOT NULL, -- user / assistant / system
  content TEXT NOT NULL,
  citations JSONB, -- [{chunk_id, doc_id, page_number, score}, ...]
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_chat_messages_session ON chat_messages(session_id, created_at DESC);


-- =====================
-- Workflow definitions / jobs / results
-- =====================
CREATE TABLE IF NOT EXISTS workflow_definitions (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  kb_id UUID REFERENCES knowledge_bases(id) ON DELETE SET NULL,
  name TEXT NOT NULL,
  type TEXT NOT NULL,
  description TEXT,
  config JSONB DEFAULT '{}'::jsonb,
  created_by UUID REFERENCES users(id),
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS workflow_jobs (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  workflow_def_id UUID NOT NULL REFERENCES workflow_definitions(id),
  kb_id UUID REFERENCES knowledge_bases(id) ON DELETE SET NULL,
  document_id UUID REFERENCES documents(id) ON DELETE SET NULL,
  triggered_by UUID REFERENCES users(id) ON DELETE SET NULL,
  status TEXT NOT NULL DEFAULT 'pending', -- pending/running/done/failed
  progress INT DEFAULT 0,
  input_params JSONB DEFAULT '{}'::jsonb,
  error_message TEXT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  started_at TIMESTAMPTZ,
  finished_at TIMESTAMPTZ
);
CREATE INDEX IF NOT EXISTS idx_workflow_jobs_kb ON workflow_jobs(kb_id, created_at DESC);

CREATE TABLE IF NOT EXISTS workflow_results (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  job_id UUID NOT NULL REFERENCES workflow_jobs(id) ON DELETE CASCADE,
  result_type TEXT NOT NULL,
  result_json JSONB NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);


-- =====================
-- Ingestion Job / Items
-- =====================
CREATE TABLE IF NOT EXISTS ingestion_jobs (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  kb_id UUID NOT NULL REFERENCES knowledge_bases(id) ON DELETE CASCADE,
  org_id UUID REFERENCES orgs(id) ON DELETE SET NULL,
  triggered_by UUID REFERENCES users(id) ON DELETE SET NULL,
  source_type TEXT NOT NULL, -- upload/s3/url_list
  status TEXT NOT NULL DEFAULT 'pending',
  total_files INT DEFAULT 0,
  processed_files INT DEFAULT 0,
  failed_files INT DEFAULT 0,
  metadata JSONB DEFAULT '{}'::jsonb,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  started_at TIMESTAMPTZ,
  finished_at TIMESTAMPTZ
);

CREATE TABLE IF NOT EXISTS ingestion_items (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  job_id UUID NOT NULL REFERENCES ingestion_jobs(id) ON DELETE CASCADE,
  document_id UUID REFERENCES documents(id) ON DELETE SET NULL,
  source_uri TEXT,
  status TEXT NOT NULL DEFAULT 'pending', -- pending/parsing/indexed/failed
  error_message TEXT,
  metadata JSONB DEFAULT '{}'::jsonb,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_ingestion_items_job ON ingestion_items(job_id);


-- =====================
-- Optional / Admin
-- =====================
CREATE TABLE IF NOT EXISTS api_tokens (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  org_id UUID REFERENCES orgs(id) ON DELETE SET NULL,
  user_id UUID REFERENCES users(id) ON DELETE SET NULL,
  token_hash TEXT NOT NULL,
  name TEXT,
  scopes TEXT[],
  metadata JSONB DEFAULT '{}'::jsonb,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  revoked_at TIMESTAMPTZ
);

CREATE TABLE IF NOT EXISTS audit_logs (
  id BIGSERIAL PRIMARY KEY,
  org_id UUID REFERENCES orgs(id) ON DELETE SET NULL,
  user_id UUID REFERENCES users(id) ON DELETE SET NULL,
  action TEXT NOT NULL,
  resource_type TEXT,
  resource_id UUID,
  metadata JSONB DEFAULT '{}'::jsonb,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_audit_org ON audit_logs(org_id);

-- End of schema
