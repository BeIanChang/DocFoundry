Backend (FastAPI)

- Run locally (Windows/PowerShell):
  - `python -m venv .venv` and activate it with `.\.venv\Scripts\activate`
  - `pip install -r requirements.txt`
  - set env (example):  
    ```
    $env:DATABASE_URL="postgresql://postgres:postgres@localhost:5432/docfoundry"
    $env:CHROMA_DIR=".\\chroma_db"
    $env:EMBED_MODEL="all-MiniLM-L6-v2"
    $env:LLM_PROVIDER="stub"      # or cerebras with API key
    $env:JWT_SECRET="dev-secret-change-me"
    ```
  - start: `uvicorn app.main:app --reload --host 0.0.0.0 --port 8000`

- Quick test commands (PowerShell):
  ```powershell
  # register + auth header
  $auth = Invoke-RestMethod -Method Post -Uri http://localhost:8000/auth/register -ContentType "application/json" -Body (@{email="test@example.com";password="test123";name="Test"} | ConvertTo-Json)
  $headers = @{ Authorization = "Bearer " + $auth.token }

  # project + KB
  $proj = Invoke-RestMethod -Method Post -Uri http://localhost:8000/projects/ -Headers $headers -ContentType "application/json" -Body (@{name="Demo Project"} | ConvertTo-Json)
  $kb = Invoke-RestMethod -Method Post -Uri http://localhost:8000/kb/ -ContentType "application/json" -Body (@{project_id=$proj.id; name="Demo KB"} | ConvertTo-Json)

  # document
  $doc = Invoke-RestMethod -Method Post -Uri http://localhost:8000/documents/ -ContentType "application/json" -Body (@{kb_id=$kb.id; title="Test Doc"} | ConvertTo-Json)

  # upload file (PS5-safe)
  Add-Type -AssemblyName System.Net.Http
  $uri  = "http://localhost:8000/documents/$($doc.id)/upload"
  $path = "F:\\Courses\\sem_9\\Projects\\ai-doc-intel-platform\\backend\\README.md"  # adjust
  $client = [System.Net.Http.HttpClient]::new()
  $multi  = [System.Net.Http.MultipartFormDataContent]::new()
  $fs = [System.IO.File]::OpenRead($path)
  $fileContent = [System.Net.Http.StreamContent]::new($fs)
  $fileContent.Headers.ContentType = [System.Net.Http.Headers.MediaTypeHeaderValue]::Parse("text/plain")
  $multi.Add($fileContent, "file", [System.IO.Path]::GetFileName($path))
  $upload = $client.PostAsync($uri, $multi).Result.Content.ReadAsStringAsync().Result | ConvertFrom-Json

  # chat session + message (RAG)
  $chat = Invoke-RestMethod -Method Post -Uri http://localhost:8000/chat/sessions -Headers $headers -ContentType "application/json" -Body (@{kb_id=$kb.id} | ConvertTo-Json)
  $msg = Invoke-RestMethod -Method Post -Uri ("http://localhost:8000/chat/sessions/{0}/messages" -f $chat.id) -Headers $headers -ContentType "application/json" -Body (@{query="What is in this doc?"; document_id=$doc.id; top_k=3} | ConvertTo-Json)
  $msg.answer.content
  ```

- Notes:
  - DB schema managed by Alembic (migration `0002_add_pw_hash_to_users` adds password hash).
  - LLM provider defaults to stub; set `LLM_PROVIDER=cerebras` + `CEREBRAS_API_KEY` to call Cerebras.
