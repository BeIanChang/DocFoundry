import { useEffect, useMemo, useState } from "react";
import Layout from "../components/Layout";
import { getApiBase, getToken, setApiBase } from "../components/auth";

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

export default function UploadPage() {
  const [apiBase, setApiBaseState] = useState("http://localhost:8000");

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
    setApiBaseState(getApiBase());
    const sync = () => setApiBaseState(getApiBase());
    window.addEventListener("docfoundry_api_base_change", sync);
    window.addEventListener("storage", sync);
    return () => {
      window.removeEventListener("docfoundry_api_base_change", sync);
      window.removeEventListener("storage", sync);
    };
  }, []);

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
    <Layout title="Upload" subtitle="Create Project/KB/Document, then upload a file to generate chunks + a document profile.">
      <div className="grid2">
        <section className="card" style={{ padding: 16 }}>
          <h2 style={{ marginTop: 0 }}>Backend</h2>
          <label className="fieldLabel">API base</label>
          <input
            className="field"
            value={apiBase}
            onChange={(e) => {
              setApiBaseState(e.target.value);
              setApiBase(e.target.value);
            }}
          />
          <div className="muted" style={{ fontSize: 12, marginTop: 10, lineHeight: 1.4 }}>
            Upload endpoints are open in dev. Agent/chat requires auth via the top-right Account menu.
          </div>
        </section>

        <section className="card" style={{ padding: 16 }}>
          <h2 style={{ marginTop: 0 }}>Create</h2>

          <div style={{ display: "grid", gap: 14 }}>
            <div>
              <label className="fieldLabel">Project name</label>
              <div style={{ display: "flex", gap: 10, flexWrap: "wrap", alignItems: "center" }}>
                <input className="field" value={projectName} onChange={(e) => setProjectName(e.target.value)} style={{ flex: "1 1 320px" }} />
                <button
                  className="btn btnPrimary"
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
                  Create
                </button>
              </div>
            </div>

            <div>
              <label className="fieldLabel">Project</label>
              <div style={{ display: "flex", gap: 10, flexWrap: "wrap", alignItems: "center" }}>
                <select className="field" value={projectId} onChange={(e) => setProjectId(e.target.value)} style={{ flex: "1 1 320px" }}>
                  <option value="">(select)</option>
                  {projects.map((p) => (
                    <option key={p.id} value={p.id}>
                      {p.name} ({p.id.slice(0, 6)}…)
                    </option>
                  ))}
                </select>
                <button className="btn" disabled={busy || !projectId} onClick={() => run(() => refreshKbs(projectId))}>
                  Load KBs
                </button>
              </div>
            </div>

            <div>
              <label className="fieldLabel">KB name</label>
              <input className="field" value={kbName} onChange={(e) => setKbName(e.target.value)} />
              <div style={{ height: 10 }} />
              <label className="fieldLabel">KB description</label>
              <input className="field" value={kbDescription} onChange={(e) => setKbDescription(e.target.value)} />
              <div style={{ marginTop: 10 }}>
                <button
                  className="btn btnPrimary"
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
            </div>

            <div>
              <label className="fieldLabel">KB</label>
              <div style={{ display: "flex", gap: 10, flexWrap: "wrap", alignItems: "center" }}>
                <select className="field" value={kbId} onChange={(e) => setKbId(e.target.value)} style={{ flex: "1 1 320px" }}>
                  <option value="">(select)</option>
                  {kbs.map((k) => (
                    <option key={k.id} value={k.id}>
                      {k.name} ({k.id.slice(0, 6)}…)
                    </option>
                  ))}
                </select>
                <button className="btn" disabled={busy || !kbId} onClick={() => run(() => refreshDocs(kbId))}>
                  Load docs
                </button>
              </div>
            </div>

            <div>
              <label className="fieldLabel">Document title</label>
              <div style={{ display: "flex", gap: 10, flexWrap: "wrap", alignItems: "center" }}>
                <input className="field" value={docTitle} onChange={(e) => setDocTitle(e.target.value)} style={{ flex: "1 1 320px" }} />
                <button
                  className="btn btnPrimary"
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
                  Create
                </button>
              </div>
            </div>

            <div>
              <label className="fieldLabel">Document</label>
              <select className="field" value={docId} onChange={(e) => setDocId(e.target.value)}>
                <option value="">(select)</option>
                {documents.map((d) => (
                  <option key={d.id} value={d.id}>
                    {d.title || "Untitled"} ({d.id.slice(0, 6)}…)
                  </option>
                ))}
              </select>
            </div>
          </div>
        </section>
      </div>

      <section className="card" style={{ padding: 16, marginTop: 14 }}>
        <h2 style={{ marginTop: 0 }}>Upload file</h2>
        <div style={{ display: "flex", gap: 10, alignItems: "center", flexWrap: "wrap" }}>
          <input type="file" onChange={(e) => setFile(e.target.files?.[0] || null)} />
          <button
            className="btn btnPrimary"
            disabled={busy || !docId || !file}
            onClick={() =>
              run(async () => {
                const form = new FormData();
                form.append("file", file);
                return apiFetch(apiBase, `/documents/${encodeURIComponent(docId)}/upload`, { method: "POST", body: form, isForm: true });
              })
            }
          >
            Upload
          </button>
          <span className="muted" style={{ fontSize: 12 }}>
            {docId ? `doc_id=${docId}` : "Select a document first"}
          </span>
        </div>
      </section>

      <section className="card" style={{ padding: 16, marginTop: 14 }}>
        <h2 style={{ marginTop: 0 }}>Result</h2>
        {error ? <pre style={{ color: "#b00020", whiteSpace: "pre-wrap" }}>{error}</pre> : null}
        <pre style={{ background: "rgba(255,122,24,.03)", border: "1px solid var(--border)", borderRadius: 14, padding: 12, overflowX: "auto" }}>
          {output ? pretty(output) : "—"}
        </pre>
      </section>
    </Layout>
  );
}
