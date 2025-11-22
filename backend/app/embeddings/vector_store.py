import os
from sentence_transformers import SentenceTransformer
import chromadb
from chromadb.config import Settings

# simple local chroma client
CHROMA_DIR = os.environ.get('CHROMA_DIR', './chroma_db')
client = chromadb.Client(Settings(chroma_db_impl="duckdb+parquet", persist_directory=CHROMA_DIR))
collection = client.get_or_create_collection("documents")

# load a small model for embeddings — user can swap to OpenAI or others
EMBED_MODEL = SentenceTransformer('all-MiniLM-L6-v2')


def add_documents(docs):
    """docs: list of {id: str, text: str} — add to chroma"""
    if not docs:
        return []
    ids = [d['id'] for d in docs]
    texts = [d['text'] for d in docs]
    embeddings = EMBED_MODEL.encode(texts, show_progress_bar=False).tolist()
    collection.add(ids=ids, documents=texts, embeddings=embeddings)
    client.persist()
    return ids


def query_documents(query: str, n_results: int = 5):
    emb = EMBED_MODEL.encode([query]).tolist()[0]
    results = collection.query(query_embeddings=[emb], n_results=n_results)
    # results is a dict with ids/documents/scores
    return results
