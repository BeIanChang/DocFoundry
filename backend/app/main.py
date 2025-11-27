from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
import tempfile
import os
# import parsers lazily (parsing libs are optional in dev image)
from app.db.session import get_engine
from app.db import models as models

app = FastAPI(title="DocFoundry")


@app.on_event("startup")
def startup_db():
    # create tables if they don't exist
    engine = get_engine()
    models.Base.metadata.create_all(bind=engine)

app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

# include API routers
from app.api.kb import router as kb_router
from app.api.documents import router as documents_router
from app.api.rag import router as rag_router
from app.api.auth import router as auth_router

app.include_router(kb_router)
app.include_router(documents_router)
app.include_router(rag_router)
app.include_router(auth_router)

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
