from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
import tempfile
import os
from dotenv import load_dotenv
from pathlib import Path
# import parsers lazily (parsing libs are optional in dev image)
from app.db.session import get_engine
from app.db import models as models

load_dotenv()

app = FastAPI(title="DocFoundry")


@app.on_event("startup")
def startup_db():
    """
    Dev-friendly DB init:
    - Prefer Alembic migrations when available (keeps existing SQLite DBs in sync).
    - Fall back to `create_all` if migrations can't run.
    """
    engine = get_engine()
    database_url = os.environ.get("DATABASE_URL") or "sqlite:///./docfoundry.db"

    try:
        from alembic import command
        from alembic.config import Config

        backend_dir = Path(__file__).resolve().parents[1]
        alembic_ini = backend_dir / "alembic.ini"
        alembic_dir = backend_dir / "alembic"
        cfg = Config(str(alembic_ini))
        cfg.set_main_option("script_location", str(alembic_dir))
        cfg.set_main_option("sqlalchemy.url", database_url)
        command.upgrade(cfg, "head")
    except Exception:
        pass

    # Ensure any new tables (not yet in migrations) exist in dev.
    models.Base.metadata.create_all(bind=engine)

app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

# include API routers
from app.api.kb import router as kb_router
from app.api.documents import router as documents_router
from app.api.rag import router as rag_router
from app.api.auth import router as auth_router
from app.api.projects import router as projects_router
from app.api.chat import router as chat_router
from app.agent.router import router as agent_router

app.include_router(kb_router)
app.include_router(documents_router)
app.include_router(rag_router)
app.include_router(auth_router)
app.include_router(projects_router)
app.include_router(chat_router)
app.include_router(agent_router)

@app.get("/health")
def health():
    return {"status": "ok"}

@app.post("/upload")
async def upload(file: UploadFile = File(...)):
    filename = file.filename
    data = await file.read()
    try:
        from app.parsers.pdf_parser import parse_file
        text = parse_file(filename, data)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

    # Add to vector store (placeholder). import lazily so dev image doesn't require heavy libs
    try:
        from app.embeddings.vector_store import add_documents
        add_documents([{"id": filename, "text": text}])
    except Exception:
        # embedding subsystem is optional in dev mode
        pass

    return {"filename": filename, "size": len(data), "preview": text[:500]}

@app.post("/qa")
async def qa(query: dict):
    q = query.get("query")
    if not q:
        raise HTTPException(status_code=400, detail="missing query")
    try:
        from app.embeddings.vector_store import query_documents
        results = query_documents(q)
    except Exception:
        results = {"ids": [], "documents": [], "distances": []}
    return JSONResponse({"query": q, "results": results})

@app.post("/workflow")
async def workflow(payload: dict):
    # payload: {"type": "summarize|extract|qa", ...}
    return {"status": "not_implemented", "payload": payload}

if __name__ == '__main__':
    import uvicorn
    uvicorn.run(app, host='0.0.0.0', port=8000)
