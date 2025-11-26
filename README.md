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
