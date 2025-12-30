import { useEffect, useMemo, useRef, useState } from "react";
import Layout from "../components/Layout";
import { getApiBase, getToken, setApiBase } from "../components/auth";

function pretty(obj) {
  try {
    return JSON.stringify(obj, null, 2);
  } catch {
    return String(obj);
  }
}

async function apiFetch(base, path, { method = "GET", token, body } = {}) {
  const headers = {};
  if (token) headers.Authorization = `Bearer ${token}`;
  if (body) headers["Content-Type"] = "application/json";
  const res = await fetch(`${base}${path}`, {
    method,
    headers,
    body: body ? JSON.stringify(body) : undefined,
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

function Bubble({ role, children }) {
  const isUser = role === "user";
  return (
    <div style={{ display: "flex", justifyContent: isUser ? "flex-end" : "flex-start", margin: "10px 0" }}>
      <div
        style={{
          maxWidth: "85%",
          padding: "10px 12px",
          borderRadius: 14,
          border: "1px solid var(--border)",
          background: isUser ? "linear-gradient(135deg, var(--orange), var(--orange-2))" : "#fff",
          color: isUser ? "#fff" : "#111",
          whiteSpace: "pre-wrap",
          lineHeight: 1.35,
        }}
      >
        {children}
      </div>
    </div>
  );
}

export default function ChatPage() {
  const [apiBase, setApiBaseState] = useState("http://localhost:8000");

  const [projects, setProjects] = useState([]);
  const [kbs, setKbs] = useState([]);
  const [documents, setDocuments] = useState([]);
  const [docProfile, setDocProfile] = useState(null);

  const [selectedProjectId, setSelectedProjectId] = useState("");
  const [selectedKbId, setSelectedKbId] = useState("");
  const [selectedDocId, setSelectedDocId] = useState("");

  const [messages, setMessages] = useState([
    {
      role: "assistant",
      content: "Ask me about your documents. Select a KB or Document on the left to scope retrieval.",
    },
  ]);
  const [draft, setDraft] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [topK, setTopK] = useState(5);
  const [showTrace, setShowTrace] = useState(true);

  const listRef = useRef(null);
  useEffect(() => {
    listRef.current?.scrollTo?.({ top: listRef.current.scrollHeight, behavior: "smooth" });
  }, [messages.length, busy]);

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
  };

  const refreshKbs = async (projectId) => {
    const q = projectId ? `?project_id=${encodeURIComponent(projectId)}` : "";
    const data = await apiFetch(apiBase, `/kb/${q}`);
    setKbs(Array.isArray(data) ? data : []);
  };

  const refreshDocs = async (kbId) => {
    const q = kbId ? `?kb_id=${encodeURIComponent(kbId)}` : "";
    const data = await apiFetch(apiBase, `/documents/${q}`);
    setDocuments(Array.isArray(data) ? data : []);
  };

  useEffect(() => {
    refreshProjects().catch(() => {});
  }, [apiBase]);

  useEffect(() => {
    refreshKbs(selectedProjectId).catch(() => {});
    setSelectedKbId("");
    setSelectedDocId("");
    setDocuments([]);
    setDocProfile(null);
  }, [selectedProjectId]);

  useEffect(() => {
    if (!selectedKbId) return;
    refreshDocs(selectedKbId).catch(() => {});
    setSelectedDocId("");
    setDocProfile(null);
  }, [selectedKbId]);

  useEffect(() => {
    if (!selectedDocId) {
      setDocProfile(null);
      return;
    }
    apiFetch(apiBase, `/documents/${encodeURIComponent(selectedDocId)}/profile`)
      .then((p) => setDocProfile(p))
      .catch(() => setDocProfile(null));
  }, [apiBase, selectedDocId]);

  const send = async () => {
    const text = draft.trim();
    if (!text || busy) return;
    setError("");
    setBusy(true);
    setDraft("");
    setMessages((m) => [...m, { role: "user", content: text }]);

    const token = getToken();
    if (!token) {
      setMessages((m) => [
        ...m,
        { role: "assistant", content: "You’re not logged in. Use the top-right Account menu to login/register, then retry." },
      ]);
      setBusy(false);
      return;
    }

    try {
      const resp = await apiFetch(apiBase, "/agent/query", {
        method: "POST",
        token,
        body: {
          message: text,
          project_id: selectedProjectId || null,
          kb_id: selectedKbId || null,
          document_id: selectedDocId || null,
          top_k: topK,
          return_steps: !!showTrace,
        },
      });

      const citations = (resp.citations || []).slice(0, 5);
      const citeLine =
        citations.length > 0
          ? `\n\nSources:\n${citations
              .map((c, i) => {
                const meta = c.metadata || {};
                const label = meta.document_id ? `doc=${meta.document_id}` : "doc=?";
                const chunk = c.chunk_id ? `chunk=${c.chunk_id}` : "chunk=?";
                return `- [${i + 1}] ${label} ${chunk}${c.score != null ? ` score=${Number(c.score).toFixed(2)}` : ""}`;
              })
              .join("\n")}`
          : "";

      setMessages((m) => [
        ...m,
        {
          role: "assistant",
          content: `${resp.answer || ""}${citeLine}`,
          meta: { run_id: resp.run_id, steps: resp.steps || null, citations: resp.citations || [] },
        },
      ]);
    } catch (e) {
      setError(e?.message || String(e));
      setMessages((m) => [...m, { role: "assistant", content: `Request failed: ${e?.message || String(e)}` }]);
    } finally {
      setBusy(false);
    }
  };

  return (
    <Layout
      title="Chat"
      subtitle="Ask questions scoped to your project/KB/document. Turn on trace to inspect routing + retrieval."
      right={
        <span className="pill">
          {busy ? "Thinking…" : "Ready"} · <span className="mono" style={{ marginLeft: 6 }}>{selectedProjectId ? selectedProjectId.slice(0, 8) : "∗"}/{selectedKbId ? selectedKbId.slice(0, 8) : "∗"}/{selectedDocId ? selectedDocId.slice(0, 8) : "∗"}</span>
        </span>
      }
    >
      <div className="grid2" style={{ alignItems: "start" }}>
        <aside className="card" style={{ padding: 14 }}>
          <div style={{ display: "grid", gap: 12 }}>
            <div>
              <div style={{ fontWeight: 700, marginBottom: 8 }}>Backend</div>
              <label className="fieldLabel">API base</label>
              <input
                className="field"
                value={apiBase}
                onChange={(e) => {
                  setApiBaseState(e.target.value);
                  setApiBase(e.target.value);
                }}
              />
              <div style={{ display: "flex", gap: 10, marginTop: 10, flexWrap: "wrap" }}>
                <button className="btn" onClick={() => apiFetch(apiBase, "/health").catch(() => {})}>
                  /health
                </button>
                <a className="btn" href={`${apiBase}/docs`} target="_blank" rel="noreferrer">
                  /docs
                </a>
              </div>
            </div>

            <div>
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", gap: 10 }}>
                <div style={{ fontWeight: 700 }}>Scope</div>
                <button className="btn" onClick={() => refreshProjects().catch(() => {})}>
                  Refresh
                </button>
              </div>

              <div style={{ marginTop: 10 }}>
                <label className="fieldLabel">Project</label>
                <select className="field" value={selectedProjectId} onChange={(e) => setSelectedProjectId(e.target.value)}>
                  <option value="">(all)</option>
                  {projects.map((p) => (
                    <option key={p.id} value={p.id}>
                      {p.name} ({p.id.slice(0, 6)}…)
                    </option>
                  ))}
                </select>
              </div>

              <div style={{ marginTop: 10 }}>
                <label className="fieldLabel">Knowledge Base</label>
                <select className="field" value={selectedKbId} onChange={(e) => setSelectedKbId(e.target.value)}>
                  <option value="">(all)</option>
                  {kbs.map((k) => (
                    <option key={k.id} value={k.id}>
                      {k.name} ({k.id.slice(0, 6)}…)
                    </option>
                  ))}
                </select>
              </div>

              <div style={{ marginTop: 10 }}>
                <label className="fieldLabel">Document</label>
                <select className="field" value={selectedDocId} onChange={(e) => setSelectedDocId(e.target.value)}>
                  <option value="">(all)</option>
                  {documents.map((d) => (
                    <option key={d.id} value={d.id}>
                      {d.title || "Untitled"} ({d.id.slice(0, 6)}…)
                    </option>
                  ))}
                </select>
              </div>

              {docProfile && selectedDocId ? (
                <div style={{ marginTop: 12, padding: 12, border: "1px solid var(--border)", borderRadius: 14, background: "linear-gradient(180deg, rgba(255,122,24,.08), rgba(255,122,24,0))" }}>
                  <div className="muted" style={{ fontSize: 12, marginBottom: 6 }}>
                    Document profile
                  </div>
                  <div style={{ fontSize: 14, fontWeight: 700 }}>{docProfile.title || "Untitled"}</div>
                  <div className="muted" style={{ fontSize: 12, marginTop: 4 }}>
                    {docProfile.doc_type ? `type=${docProfile.doc_type}` : "type=unknown"}
                    {docProfile.year_start || docProfile.year_end ? ` · years=${docProfile.year_start || "?"}–${docProfile.year_end || "?"}` : ""}
                  </div>
                  {docProfile.summary ? <div style={{ marginTop: 10, fontSize: 13, color: "#222", lineHeight: 1.5 }}>{docProfile.summary}</div> : null}
                </div>
              ) : null}

              <div style={{ marginTop: 12, display: "flex", gap: 10, alignItems: "center", flexWrap: "wrap" }}>
                <label className="fieldLabel" style={{ margin: 0 }}>
                  top_k
                </label>
                <input className="field" value={topK} onChange={(e) => setTopK(Number(e.target.value || 5))} type="number" min={1} max={50} style={{ width: 110 }} />
                <button className="btn" onClick={() => setMessages([{ role: "assistant", content: "New chat started. Ask away." }])}>
                  New chat
                </button>
              </div>
              <label style={{ display: "flex", gap: 10, alignItems: "center", marginTop: 10, fontSize: 12, color: "var(--muted)" }}>
                <input type="checkbox" checked={showTrace} onChange={(e) => setShowTrace(e.target.checked)} />
                Show agent trace (dev)
              </label>
            </div>
          </div>
        </aside>

        <main className="card" style={{ padding: 14, display: "flex", flexDirection: "column", minHeight: "70vh" }}>
          <div ref={listRef} style={{ flex: 1, overflowY: "auto", padding: 14, background: "rgba(255,122,24,.03)", borderRadius: 14, border: "1px solid var(--border)" }}>
          {messages.map((m, idx) => {
            const steps = m?.meta?.steps;
            const runId = m?.meta?.run_id;
            return (
              <div key={idx}>
                <Bubble role={m.role}>{m.content}</Bubble>
                {m.role === "assistant" && Array.isArray(m?.meta?.citations) && m.meta.citations.length ? (
                  <div style={{ marginTop: -2, marginBottom: 12, display: "flex", gap: 8, flexWrap: "wrap" }}>
                    {m.meta.citations.slice(0, 5).map((c, i) => {
                      const meta = c.metadata || {};
                      const docId = meta.document_id || "";
                      const versionId = meta.version_id || "";
                      const chunkId = c.chunk_id || "";
                      const href = chunkId
                        ? `/library?chunk_id=${encodeURIComponent(chunkId)}&document_id=${encodeURIComponent(docId)}&version_id=${encodeURIComponent(versionId)}`
                        : `/library?document_id=${encodeURIComponent(docId)}`;
                      return (
                        <a key={`${chunkId || i}`} className="pill" href={href} style={{ cursor: "pointer" }}>
                          Source {i + 1}
                        </a>
                      );
                    })}
                  </div>
                ) : null}
                {m.role === "assistant" && showTrace && runId ? (
                  <details style={{ marginTop: -2, marginBottom: 10 }}>
                    <summary style={{ cursor: "pointer", color: "var(--muted)", fontSize: 12 }}>Trace (run_id={runId.slice(0, 8)}…)</summary>
                    <pre style={{ marginTop: 8, padding: 10, background: "#fff", border: "1px solid var(--border)", borderRadius: 14, overflowX: "auto", fontSize: 12, whiteSpace: "pre-wrap" }}>
                      {steps ? pretty(steps) : "No steps returned (toggle on before sending)."}
                    </pre>
                  </details>
                ) : null}
              </div>
            );
          })}
        </div>

          <div style={{ marginTop: 12 }}>
            {error ? (
              <div style={{ marginBottom: 10, color: "#b00020", whiteSpace: "pre-wrap" }}>
                {error}
              </div>
            ) : null}
            <div style={{ display: "flex", gap: 10, alignItems: "flex-end" }}>
              <textarea
                className="field"
                value={draft}
                onChange={(e) => setDraft(e.target.value)}
                placeholder="Type a message…"
                rows={2}
                style={{ flex: 1, resize: "vertical", minHeight: 44 }}
                onKeyDown={(e) => {
                  if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) send();
                }}
              />
              <button className="btn btnPrimary" disabled={busy || !draft.trim()} onClick={send} style={{ height: 44 }}>
                Send
              </button>
            </div>
            <div className="muted" style={{ marginTop: 8, fontSize: 12 }}>
              Tip: Press Ctrl/Cmd+Enter to send.
            </div>
          </div>
        </main>
      </div>
    </Layout>
  );
}
