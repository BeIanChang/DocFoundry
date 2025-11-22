Backend (FastAPI) skeleton

- Run locally:
  - create a virtualenv: `python -m venv .venv` and activate it
  - `pip install -r requirements.txt`
  - `uvicorn app.main:app --reload --host 0.0.0.0 --port 8000`

- Endpoints (skeleton):
  - `POST /upload` — upload a document (PDF/TXT/HTML)
  - `POST /qa` — RAG QA endpoint (stub)
  - `POST /workflow` — run workflows like summarize/extract (stub)

This folder contains placeholder implementations for parsing, embeddings and vector store.
