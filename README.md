# DocFoundry — AI Document Intelligence & RAG Workflow Platform

Project skeleton for DocFoundry: an AI Document Intelligence & RAG Workflow Platform.

Architecture:
- backend: FastAPI app (upload, parsing, embeddings/vector store placeholder, RAG/QA endpoints, workflows)
- frontend: Next.js lightweight dashboard
- docker-compose for local deployment

This repo is intended as a portfolio-level project demonstrating AI + backend engineering skills.

See subfolders for instructions.

## Run with Docker Compose

- Build and start core services: `docker compose up --build backend frontend postgres`
- Backend: FastAPI at `http://localhost:8000` (`/health`, `/docs`), uses Postgres `docfoundry` DB and persists Chroma to `./chroma_db`.
- Frontend: Next.js at `http://localhost:3000`.
- Dev backend container (hot-reload) is available under the `dev` profile: `docker compose --profile dev up backend-dev postgres`.
  - Avoid running `backend` and `backend-dev` together because they both bind port 8000.
- For faster rebuilds: the backend Dockerfile uses BuildKit pip cache. Rebuild only when `requirements*.txt` change (`docker compose build backend`), otherwise use `docker compose up backend` to reuse the cached image.

## Minimal RAG flow (backend)

- Upload/parse/chunk a document via `/documents/{doc_id}/upload` (see `app/api/documents.py`); chunks are embedded into Chroma with metadata (`kb_id`, `document_id`, `version_id`).
- Query via `POST /rag/query`:
  ```json
  { "query": "your question", "kb_id": "<optional>", "document_id": "<optional>", "top_k": 5 }
  ```
  Returns `answer`, `sources` (chunk text, metadata, scores). Default LLM provider is a stub (`LLM_PROVIDER=stub`); swap provider when wiring a real model.

## Stub auth (dev only)
- Now uses JWT (HS256) with dev defaults. Env: `JWT_SECRET`, `JWT_EXP_MINUTES` (see docker-compose).
- `POST /auth/register` with `{"email": "...", "password": "...", "name": "..."}` returns a JWT and creates a DB user.
- `POST /auth/login` returns a JWT (validated against DB user + password_hash).
- Include `Authorization: Bearer <token>` on requests that need user context.

## New endpoints (Milestone 4 beginnings)
- Projects: `POST /projects`, `GET /projects`, `GET /projects/{id}`, `PUT /projects/{id}`, `DELETE /projects/{id}`. KB creation now validates `project_id` if supplied.
- Chat: `POST /chat/sessions` (optional `kb_id`, requires `Authorization: Bearer <token>`), `GET /chat/sessions`, `POST /chat/sessions/{id}/messages` (uses RAG under the hood and stores Q/A in `chat_messages`).

## LLM provider options
- Default: `LLM_PROVIDER=stub` (no external calls).
- Cerebras (OpenAI-compatible): set `LLM_PROVIDER=cerebras`, `CEREBRAS_API_KEY=<key>`, optional `CEREBRAS_MODEL` (default `llama3.1-8b-instruct`). Endpoint: `https://api.cerebras.ai/v1/chat/completions`.
