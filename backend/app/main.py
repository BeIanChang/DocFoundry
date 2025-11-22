from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
import tempfile
import os
from app.parsers.pdf_parser import parse_file
from app.embeddings.vector_store import add_documents, query_documents

app = FastAPI(title="DocFoundry")

app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

@app.get("/health")
def health():
    return {"status": "ok"}

@app.post("/upload")
async def upload(file: UploadFile = File(...)):
    filename = file.filename
    data = await file.read()
    try:
        text = parse_file(filename, data)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

    # Add to vector store (placeholder)
    add_documents([{"id": filename, "text": text}])

    return {"filename": filename, "size": len(data), "preview": text[:500]}

@app.post("/qa")
async def qa(query: dict):
    q = query.get("query")
    if not q:
        raise HTTPException(status_code=400, detail="missing query")
    results = query_documents(q)
    return JSONResponse({"query": q, "results": results})

@app.post("/workflow")
async def workflow(payload: dict):
    # payload: {"type": "summarize|extract|qa", ...}
    return {"status": "not_implemented", "payload": payload}

if __name__ == '__main__':
    import uvicorn
    uvicorn.run(app, host='0.0.0.0', port=8000)
