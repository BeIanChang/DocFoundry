import { useEffect, useMemo, useState } from "react";

function pretty(obj) {
  try {
    return JSON.stringify(obj, null, 2);
  } catch {
    return String(obj);
  }
}

async function apiFetch(base, path, { method = "GET", token, body, isForm } = {}) {
  const headers = {};
  if (token) headers.Authorization = `Bearer ${token}`;
  if (body && !isForm) headers["Content-Type"] = "application/json";
  const res = await fetch(`${base}${path}`, {
    method,
    headers,
    body: body ? (isForm ? body : JSON.stringify(body)) : undefined,
  });
  const text = await res.text();
  let data = text;
  try {
    data = text ? JSON.parse(text) : null;
  } catch {}
  if (!res.ok) {
    const msg = typeof data === "string" ? data : data?.detail || pretty(data);
    throw new Error(`${res.status} ${res.statusText}: ${msg}`);
  }
  return data;
}

function Nav() {
  return (
    <div style={{ display: "flex", gap: 12, alignItems: "center" }}>
      <a href="/" style={{ fontWeight: 700, color: "#111", textDecoration: "none" }}>
        DocFoundry
      </a>
      <a href="/chat">Chat</a>
      <a href="/upload">Upload</a>
    </div>
  );
}

export default function UploadPage() {
  const [apiBase, setApiBase] = useState("http://localhost:8000");
  const [token, setToken] = useState("");
  const authHeaderPreview = useMemo(() => (token ? `Bearer ${token.slice(0, 16)}…` : "(none)"), [token]);

  const [email, setEmail] = useState("test@example.com");
  const [password, setPassword] = useState("test123");
  const [name, setName] = useState("Test");

  const [projects, setProjects] = useState([]);
  const [kbs, setKbs] = useState([]);
  const [documents, setDocuments] = useState([]);

  const [projectName, setProjectName] = useState("Demo Project");
  const [kbName, setKbName] = useState("Demo KB");
  const [kbDescription, setKbDescription] = useState("");
  const [docTitle, setDocTitle] = useState("New Document");

  const [projectId, setProjectId] = useState("");
  const [kbId, setKbId] = useState("");
  const [docId, setDocId] = useState("");

  const [file, setFile] = useState(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [output, setOutput] = useState(null);

  useEffect(() => {
    const saved = window.localStorage.getItem("docfoundry_token");
    if (saved) setToken(saved);
  }, []);

  useEffect(() => {
    if (token) window.localStorage.setItem("docfoundry_token", token);
    else window.localStorage.removeItem("docfoundry_token");
  }, [token]);

  const authRegister = async () => {
    const data = await apiFetch(apiBase, "/auth/register", { method: "POST", body: { email, password, name } });
    setToken(data.token || "");
    return data;
  };

  const authLogin = async () => {
    const data = await apiFetch(apiBase, "/auth/login", { method: "POST", body: { email, password } });
    setToken(data.token || "");
    return data;
  };

  const refreshProjects = async () => {
    const data = await apiFetch(apiBase, "/projects/");
    setProjects(Array.isArray(data) ? data : []);
    return data;
  };

  const refreshKbs = async (pId) => {
    const q = pId ? `?project_id=${encodeURIComponent(pId)}` : "";
    const data = await apiFetch(apiBase, `/kb/${q}`);
    setKbs(Array.isArray(data) ? data : []);
    return data;
  };

  const refreshDocs = async (kId) => {
    const q = kId ? `?kb_id=${encodeURIComponent(kId)}` : "";
    const data = await apiFetch(apiBase, `/documents/${q}`);
    setDocuments(Array.isArray(data) ? data : []);
    return data;
  };

  useEffect(() => {
    refreshProjects().catch(() => {});
  }, [apiBase]);

  const run = async (fn) => {
    setError("");
    setOutput(null);
    setBusy(true);
    try {
      const data = await fn();
      setOutput(data);
      return data;
    } catch (e) {
      setError(e?.message || String(e));
      throw e;
    } finally {
      setBusy(false);
    }
  };

  return (
    <div style={{ padding: 18, fontFamily: "system-ui, -apple-system, Segoe UI, Roboto, Arial, sans-serif", maxWidth: 980, margin: "0 auto" }}>
      <Nav />

      <h1 style={{ marginTop: 16, marginBottom: 6 }}>Upload</h1>
      <p style={{ marginTop: 0, color: "#444" }}>Create Project/KB/Document, then upload a file to create chunks + a document profile.</p>

      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 14 }}>
        <section style={{ border: "1px solid #eee", borderRadius: 10, padding: 14 }}>
          <h2 style={{ marginTop: 0 }}>Backend + Auth</h2>
          <label style={{ display: "block", fontSize: 12, color: "#555" }}>
            API base
            <input value={apiBase} onChange={(e) => setApiBase(e.target.value)} style={{ width: "100%", marginTop: 6, padding: 8 }} />
          </label>
          <div style={{ fontSize: 12, color: "#666", marginTop: 8 }}>Authorization: {authHeaderPreview}</div>

          <div style={{ display: "grid", gap: 8, marginTop: 10 }}>
            <label style={{ fontSize: 12, color: "#555" }}>
              Email
              <input value={email} onChange={(e) => setEmail(e.target.value)} style={{ width: "100%", marginTop: 6, padding: 8 }} />
            </label>
            <label style={{ fontSize: 12, color: "#555" }}>
              Password
              <input value={password} onChange={(e) => setPassword(e.target.value)} type="password" style={{ width: "100%", marginTop: 6, padding: 8 }} />
            </label>
            <label style={{ fontSize: 12, color: "#555" }}>
              Name (register)
              <input value={name} onChange={(e) => setName(e.target.value)} style={{ width: "100%", marginTop: 6, padding: 8 }} />
            </label>
            <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
              <button disabled={busy} onClick={() => run(authLogin)}>Login</button>
              <button disabled={busy} onClick={() => run(authRegister)}>Register</button>
              <button disabled={busy} onClick={() => setToken("")}>
                Clear token
              </button>
            </div>
          </div>
        </section>

        <section style={{ border: "1px solid #eee", borderRadius: 10, padding: 14 }}>
          <h2 style={{ marginTop: 0 }}>Create</h2>

          <div style={{ display: "grid", gap: 10 }}>
            <div style={{ display: "flex", gap: 8, alignItems: "flex-end", flexWrap: "wrap" }}>
              <label style={{ fontSize: 12, color: "#555" }}>
                Project name
                <input value={projectName} onChange={(e) => setProjectName(e.target.value)} style={{ width: 260, marginTop: 6, padding: 8 }} />
              </label>
              <button
                disabled={busy}
                onClick={() =>
                  run(async () => {
                    const proj = await apiFetch(apiBase, "/projects/", { method: "POST", body: { name: projectName } });
                    setProjectId(proj.id || "");
                    await refreshProjects();
                    await refreshKbs(proj.id);
                    return proj;
                  })
                }
              >
                Create project
              </button>
            </div>

            <div style={{ display: "flex", gap: 8, alignItems: "flex-end", flexWrap: "wrap" }}>
              <label style={{ fontSize: 12, color: "#555" }}>
                project_id
                <select value={projectId} onChange={(e) => setProjectId(e.target.value)} style={{ width: 360, marginTop: 6, padding: 8 }}>
                  <option value="">(select)</option>
                  {projects.map((p) => (
                    <option key={p.id} value={p.id}>
                      {p.name} ({p.id.slice(0, 6)}…)
                    </option>
                  ))}
                </select>
              </label>
              <button disabled={busy || !projectId} onClick={() => run(() => refreshKbs(projectId))}>
                Load KBs
              </button>
            </div>

            <div style={{ display: "flex", gap: 8, alignItems: "flex-end", flexWrap: "wrap" }}>
              <label style={{ fontSize: 12, color: "#555" }}>
                KB name
                <input value={kbName} onChange={(e) => setKbName(e.target.value)} style={{ width: 240, marginTop: 6, padding: 8 }} />
              </label>
              <label style={{ fontSize: 12, color: "#555" }}>
                KB description
                <input value={kbDescription} onChange={(e) => setKbDescription(e.target.value)} style={{ width: 260, marginTop: 6, padding: 8 }} />
              </label>
              <button
                disabled={busy || !projectId}
                onClick={() =>
                  run(async () => {
                    const kb = await apiFetch(apiBase, "/kb/", { method: "POST", body: { project_id: projectId, name: kbName, description: kbDescription || null } });
                    setKbId(kb.id || "");
                    await refreshKbs(projectId);
                    await refreshDocs(kb.id);
                    return kb;
                  })
                }
              >
                Create KB
              </button>
            </div>

            <div style={{ display: "flex", gap: 8, alignItems: "flex-end", flexWrap: "wrap" }}>
              <label style={{ fontSize: 12, color: "#555" }}>
                kb_id
                <select value={kbId} onChange={(e) => setKbId(e.target.value)} style={{ width: 360, marginTop: 6, padding: 8 }}>
                  <option value="">(select)</option>
                  {kbs.map((k) => (
                    <option key={k.id} value={k.id}>
                      {k.name} ({k.id.slice(0, 6)}…)
                    </option>
                  ))}
                </select>
              </label>
              <button disabled={busy || !kbId} onClick={() => run(() => refreshDocs(kbId))}>
                Load documents
              </button>
            </div>

            <div style={{ display: "flex", gap: 8, alignItems: "flex-end", flexWrap: "wrap" }}>
              <label style={{ fontSize: 12, color: "#555" }}>
                Document title
                <input value={docTitle} onChange={(e) => setDocTitle(e.target.value)} style={{ width: 360, marginTop: 6, padding: 8 }} />
              </label>
              <button
                disabled={busy || !kbId}
                onClick={() =>
                  run(async () => {
                    const doc = await apiFetch(apiBase, "/documents/", { method: "POST", body: { kb_id: kbId, title: docTitle } });
                    setDocId(doc.id || "");
                    await refreshDocs(kbId);
                    return doc;
                  })
                }
              >
                Create document
              </button>
            </div>

            <div style={{ display: "flex", gap: 8, alignItems: "flex-end", flexWrap: "wrap" }}>
              <label style={{ fontSize: 12, color: "#555" }}>
                doc_id
                <select value={docId} onChange={(e) => setDocId(e.target.value)} style={{ width: 360, marginTop: 6, padding: 8 }}>
                  <option value="">(select)</option>
                  {documents.map((d) => (
                    <option key={d.id} value={d.id}>
                      {d.title || "Untitled"} ({d.id.slice(0, 6)}…)
                    </option>
                  ))}
                </select>
              </label>
            </div>
          </div>
        </section>
      </div>

      <section style={{ border: "1px solid #eee", borderRadius: 10, padding: 14, marginTop: 14 }}>
        <h2 style={{ marginTop: 0 }}>Upload file</h2>
        <div style={{ display: "flex", gap: 10, alignItems: "center", flexWrap: "wrap" }}>
          <input type="file" onChange={(e) => setFile(e.target.files?.[0] || null)} />
          <button
            disabled={busy || !docId || !file}
            onClick={() =>
              run(async () => {
                const form = new FormData();
                form.append("file", file);
                return apiFetch(apiBase, `/documents/${encodeURIComponent(docId)}/upload`, { method: "POST", body: form, isForm: true });
              })
            }
          >
            Upload to selected doc
          </button>
          <span style={{ fontSize: 12, color: "#666" }}>{docId ? `doc_id=${docId}` : "Select a document first"}</span>
        </div>
      </section>

      <section style={{ border: "1px solid #eee", borderRadius: 10, padding: 14, marginTop: 14 }}>
        <h2 style={{ marginTop: 0 }}>Result</h2>
        {error ? <pre style={{ color: "#b00020", whiteSpace: "pre-wrap" }}>{error}</pre> : null}
        <pre style={{ background: "#fafafa", border: "1px solid #eee", borderRadius: 10, padding: 12, overflowX: "auto" }}>{output ? pretty(output) : "—"}</pre>
      </section>
    </div>
  );
}

