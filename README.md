# DocFoundry

Agentic knowledge workspace for document-centric reasoning with traceable citations.

## Project Goal

Build a workspace where users can ingest internal documents, organize them by project/KB/folder, and ask questions through an agent that plans retrieval steps, answers with citations, and keeps step-by-step trace logs.

## Current Progress

Core platform:

- Multi-level content model is in place: Projects -> Knowledge Bases -> Folders -> Documents.
- End-to-end pipeline works: upload -> parse -> chunk -> embed -> retrieve -> answer.
- JWT-based auth and per-user run history are implemented.
- Frontend library/chat flow is integrated with scoped agent query APIs.

Agent loop progress:

- Classic orchestrator loop is working in production path.
- Retrieval toolkit includes `vector_search`, `keyword_search`, and `web_search`.
- New `grep_search` tool is now added for regex/literal pattern search over chunk text.
- Planner can now choose `grep_search` as an action when pattern matching is needed.
- Scope guardrails and citation normalization are active in final answers.

LangGraph progress:

- Optional LangGraph-based self-defined loop engine is implemented.
- Engine can be selected per request (`loop_engine`) or by env (`AGENT_LOOP_ENGINE`).
- Fallback behavior is explicit: if LangGraph dependency is missing, classic loop remains available.

## Quick Start (Local)

```bash
docker compose up --build backend frontend postgres
```

- Backend: `http://localhost:8000` (`/health`, `/docs`)
- Frontend: `http://localhost:3000`

For backend-only details, see `backend/README.md`.

## Remote Server Test Plan

1. Deploy and start services (`backend`, `frontend`, `postgres`) with environment values for your server.
2. Verify backend health: `GET /health`.
3. Register/login and obtain JWT.
4. Create project + KB + document, upload at least one file.
5. Run agent queries on both engines:
   - classic: set `"loop_engine": "classic"`
   - LangGraph: set `"loop_engine": "langgraph"` (after installing `requirements-langgraph.txt`)
6. Validate citations and step traces returned by `/agent/query`.
7. Run a grep-focused query (regex or exact snippet) to validate `grep_search` path.

## Next Steps

- Connect DocFoundry runtime to the dedicated serving gateway (`DocFoundry-Serve`) for stage-aware inference.
- Add deeper observability for agent tool usage and per-stage latency.
- Expand regression tests for classic vs LangGraph loop parity.
- Harden deployment profile for production autoscaling and secrets management.

## Repo Layout

- `backend/`: FastAPI app (agent loop, retrieval, auth, ingestion)
- `frontend/`: Next.js workspace UI
- `k8s/`: deployment manifests
