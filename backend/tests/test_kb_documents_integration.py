import requests
import pytest

BASE = "http://localhost:8000"


def _server_available():
    try:
        r = requests.get(f"{BASE}/health", timeout=1)
        return r.status_code == 200
    except Exception:
        return False


@pytest.mark.skipif(not _server_available(), reason="backend server not available at http://localhost:8000")
def test_kb_crud():
    # create
    payload = {"name": "testkb-integ", "description": "desc"}
    r = requests.post(f"{BASE}/kb/", json=payload)
    assert r.status_code == 200
    kb = r.json()
    assert kb.get("id")

    kb_id = kb["id"]

    # get
    r2 = requests.get(f"{BASE}/kb/{kb_id}")
    assert r2.status_code == 200

    # list
    r3 = requests.get(f"{BASE}/kb")
    assert r3.status_code == 200

    # update
    up = {"name": "testkb-integ-edited"}
    r4 = requests.put(f"{BASE}/kb/{kb_id}", json=up)
    assert r4.status_code == 200
    assert r4.json()["name"] == "testkb-integ-edited"

    # delete
    r5 = requests.delete(f"{BASE}/kb/{kb_id}")
    assert r5.status_code == 200

    # confirm deleted
    r6 = requests.get(f"{BASE}/kb/{kb_id}")
    assert r6.status_code == 404


@pytest.mark.skipif(not _server_available(), reason="backend server not available at http://localhost:8000")
def test_document_crud():
    # create a kb to attach
    r = requests.post(f"{BASE}/kb/", json={"name": "kb-for-doc", "description": "d"})
    assert r.status_code == 200
    kb = r.json()
    kb_id = kb["id"]

    # create document
    r2 = requests.post(f"{BASE}/documents/", json={"title": "doc1", "kb_id": kb_id})
    assert r2.status_code == 200
    doc = r2.json()
    doc_id = doc["id"]

    # get
    r3 = requests.get(f"{BASE}/documents/{doc_id}")
    assert r3.status_code == 200

    # list
    r4 = requests.get(f"{BASE}/documents", params={"kb_id": kb_id})
    assert r4.status_code == 200

    # update
    r5 = requests.put(f"{BASE}/documents/{doc_id}", json={"title": "doc1-edited"})
    assert r5.status_code == 200
    assert r5.json()["title"] == "doc1-edited"

    # delete
    r6 = requests.delete(f"{BASE}/documents/{doc_id}")
    assert r6.status_code == 200

    # cleanup kb
    requests.delete(f"{BASE}/kb/{kb_id}")


@pytest.mark.skipif(not _server_available(), reason="backend server not available at http://localhost:8000")
def test_create_document_with_invalid_kb_returns_404():
    # try to create a document referencing a non-existent kb
    payload = {"title": "doc-bad-kb", "kb_id": "00000000-0000-0000-0000-000000000000"}
    r = requests.post(f"{BASE}/documents/", json=payload)
    assert r.status_code == 404, r.text


@pytest.mark.skipif(not _server_available(), reason="backend server not available at http://localhost:8000")
def test_document_upload_and_chunking():
    # create a kb and document
    r = requests.post(f"{BASE}/kb/", json={"name": "kb-for-upload", "description": "d"})
    assert r.status_code == 200
    kb_id = r.json()["id"]

    r2 = requests.post(f"{BASE}/documents/", json={"title": "filedoc", "kb_id": kb_id})
    assert r2.status_code == 200
    doc_id = r2.json()["id"]

    small_text = "Hello world. " * 200
    files = {"file": ("hello.txt", small_text, "text/plain")}

    r3 = requests.post(f"{BASE}/documents/{doc_id}/upload", files=files)
    assert r3.status_code == 200, r3.text
    j = r3.json()
    assert j.get("version_id")
    assert j.get("chunks_created", 0) > 0

    # cleanup: remove rows via API
    requests.delete(f"{BASE}/documents/{doc_id}")
    requests.delete(f"{BASE}/kb/{kb_id}")
