# DocFoundry — Agentic Knowledge Workspace ✨

## 🎥 Introduction

[![Demo](assets/thumbnail.jpg)](https://github.com/user-attachments/assets/ff8bae84-a8c3-4200-8d8e-423e72579754)

DocFoundry turns messy internal documents into a living, queryable knowledge base with an agent that can reason across files, cite sources inline, and surface what matters in seconds.

## 🚀 Why it stands out 
- LLM Agent that decides when to search, how to scope, and how to answer with traceable citations.
- Multi-level knowledge organization (Projects, KBs, Folders, Documents) with a VSCode-like explorer.
- Inline, clickable citations that jump straight to the exact source chunk.
- End-to-end pipeline: upload → parse → embed → retrieve → answer → persist.

## 🧠 Core features 
- Document ingestion with parsing, chunking, and profile extraction.
- Vector + keyword retrieval with pgvector-backed embeddings.
- Agent chat with chat history, scoped search, and trace debugging.
- Source viewer with raw/parsed content and citation navigation.
- JWT auth and per-user workspaces.

## 🛠️ Tech stack 
- Backend: FastAPI, SQLAlchemy, Alembic, JWT auth
- Storage: PostgreSQL + pgvector (embeddings), local file storage for uploads
- LLM: Cerebras API (OpenAI-compatible)
- Frontend: Next.js + React, custom UI/UX
- Infra: Docker, K8s manifests, AWS-ready (EKS/RDS/ECR)


## ⚡ Quick start (local) 
```bash
docker compose up --build backend frontend postgres
```

- Backend: `http://localhost:8000` (`/health`, `/docs`)
- Frontend: `http://localhost:3000`

## 📦 Repo layout 
- `backend/` FastAPI app (agent, retrieval, uploads, auth)
- `frontend/` Next.js app (workspace UI)
- `k8s/` K8s manifests for deployment

## 📌 Notes 
- Default LLM provider is configurable in `.env`.
- For production, configure Cerebras keys and Postgres with pgvector enabled.
