import { useEffect, useMemo, useRef, useState } from "react";

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

function Bubble({ role, children }) {
  const isUser = role === "user";
  return (
    <div style={{ display: "flex", justifyContent: isUser ? "flex-end" : "flex-start", margin: "10px 0" }}>
      <div
        style={{
          maxWidth: "85%",
          padding: "10px 12px",
          borderRadius: 12,
          border: "1px solid #e6e6e6",
          background: isUser ? "#0b5fff" : "#fff",
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
  const [apiBase, setApiBase] = useState("http://localhost:8000");

  const [token, setToken] = useState("");
  const authHeaderPreview = useMemo(() => (token ? `Bearer ${token.slice(0, 16)}…` : "(none)"), [token]);

  const [email, setEmail] = useState("test@example.com");
  const [password, setPassword] = useState("test123");
  const [name, setName] = useState("Test");

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
    const saved = window.localStorage.getItem("docfoundry_token");
    if (saved) setToken(saved);
  }, []);

  useEffect(() => {
    if (token) window.localStorage.setItem("docfoundry_token", token);
    else window.localStorage.removeItem("docfoundry_token");
  }, [token]);

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

  const authRegister = async () => {
    const data = await apiFetch(apiBase, "/auth/register", { method: "POST", body: { email, password, name } });
    setToken(data.token || "");
  };

  const authLogin = async () => {
    const data = await apiFetch(apiBase, "/auth/login", { method: "POST", body: { email, password } });
    setToken(data.token || "");
  };

  const send = async () => {
    const text = draft.trim();
    if (!text || busy) return;
    setError("");
    setBusy(true);
    setDraft("");
    setMessages((m) => [...m, { role: "user", content: text }]);

    if (!token) {
      setMessages((m) => [
        ...m,
        { role: "assistant", content: "You’re not logged in. Use the login form (left) to get a JWT, then retry." },
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
          meta: { run_id: resp.run_id, steps: resp.steps || null },
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
    <div style={{ height: "100vh", display: "flex", fontFamily: "system-ui, -apple-system, Segoe UI, Roboto, Arial, sans-serif" }}>
      <aside style={{ width: 380, borderRight: "1px solid #eee", padding: 14, overflowY: "auto" }}>
        <Nav />

        <div style={{ marginTop: 12, padding: 12, border: "1px solid #eee", borderRadius: 10 }}>
          <div style={{ fontWeight: 600, marginBottom: 8 }}>Backend</div>
          <label style={{ display: "block", fontSize: 12, color: "#555" }}>
            API base
            <input value={apiBase} onChange={(e) => setApiBase(e.target.value)} style={{ width: "100%", marginTop: 6, padding: 8 }} />
          </label>
          <div style={{ display: "flex", gap: 8, marginTop: 10, flexWrap: "wrap" }}>
            <button onClick={() => apiFetch(apiBase, "/health").catch(() => {})}>/health</button>
            <a href={`${apiBase}/docs`} target="_blank" rel="noreferrer">
              /docs
            </a>
          </div>
        </div>

        <div style={{ marginTop: 12, padding: 12, border: "1px solid #eee", borderRadius: 10 }}>
          <div style={{ fontWeight: 600, marginBottom: 8 }}>Auth</div>
          <div style={{ fontSize: 12, color: "#666", marginBottom: 8 }}>Authorization: {authHeaderPreview}</div>
          <label style={{ display: "block", fontSize: 12, color: "#555" }}>
            Email
            <input value={email} onChange={(e) => setEmail(e.target.value)} style={{ width: "100%", marginTop: 6, padding: 8 }} />
          </label>
          <label style={{ display: "block", fontSize: 12, color: "#555", marginTop: 8 }}>
            Password
            <input value={password} onChange={(e) => setPassword(e.target.value)} type="password" style={{ width: "100%", marginTop: 6, padding: 8 }} />
          </label>
          <label style={{ display: "block", fontSize: 12, color: "#555", marginTop: 8 }}>
            Name (register)
            <input value={name} onChange={(e) => setName(e.target.value)} style={{ width: "100%", marginTop: 6, padding: 8 }} />
          </label>
          <div style={{ display: "flex", gap: 8, marginTop: 10, flexWrap: "wrap" }}>
            <button onClick={() => authLogin().catch((e) => setError(e?.message || String(e)))}>Login</button>
            <button onClick={() => authRegister().catch((e) => setError(e?.message || String(e)))}>Register</button>
            <button onClick={() => setToken("")}>Clear</button>
          </div>
        </div>

        <div style={{ marginTop: 12, padding: 12, border: "1px solid #eee", borderRadius: 10 }}>
          <div style={{ display: "flex", justifyContent: "space-between", gap: 8, alignItems: "center" }}>
            <div style={{ fontWeight: 600 }}>Your Data</div>
            <button onClick={() => refreshProjects().catch(() => {})}>Refresh</button>
          </div>

          <div style={{ marginTop: 10 }}>
            <div style={{ fontSize: 12, color: "#666", marginBottom: 6 }}>Project</div>
            <select value={selectedProjectId} onChange={(e) => setSelectedProjectId(e.target.value)} style={{ width: "100%", padding: 8 }}>
              <option value="">(all)</option>
              {projects.map((p) => (
                <option key={p.id} value={p.id}>
                  {p.name} ({p.id.slice(0, 6)}…)
                </option>
              ))}
            </select>
          </div>

          <div style={{ marginTop: 10 }}>
            <div style={{ fontSize: 12, color: "#666", marginBottom: 6 }}>Knowledge Base</div>
            <select value={selectedKbId} onChange={(e) => setSelectedKbId(e.target.value)} style={{ width: "100%", padding: 8 }}>
              <option value="">(all)</option>
              {kbs.map((k) => (
                <option key={k.id} value={k.id}>
                  {k.name} ({k.id.slice(0, 6)}…)
                </option>
              ))}
            </select>
          </div>

          <div style={{ marginTop: 10 }}>
            <div style={{ fontSize: 12, color: "#666", marginBottom: 6 }}>Document</div>
            <select value={selectedDocId} onChange={(e) => setSelectedDocId(e.target.value)} style={{ width: "100%", padding: 8 }}>
              <option value="">(all)</option>
              {documents.map((d) => (
                <option key={d.id} value={d.id}>
                  {d.title || "Untitled"} ({d.id.slice(0, 6)}…)
                </option>
              ))}
            </select>
          </div>

          {docProfile && selectedDocId ? (
            <div style={{ marginTop: 10, padding: 10, border: "1px solid #eee", borderRadius: 10, background: "#fff" }}>
              <div style={{ fontSize: 12, color: "#666", marginBottom: 6 }}>Document profile</div>
              <div style={{ fontSize: 13, fontWeight: 600 }}>{docProfile.title || "Untitled"}</div>
              <div style={{ fontSize: 12, color: "#666", marginTop: 4 }}>
                {docProfile.doc_type ? `type=${docProfile.doc_type}` : "type=unknown"}
                {docProfile.year_start || docProfile.year_end ? ` · years=${docProfile.year_start || "?"}–${docProfile.year_end || "?"}` : ""}
              </div>
              {docProfile.summary ? <div style={{ marginTop: 8, fontSize: 13, color: "#222" }}>{docProfile.summary}</div> : null}
              {Array.isArray(docProfile.tags) && docProfile.tags.length ? (
                <div style={{ marginTop: 8, display: "flex", flexWrap: "wrap", gap: 6 }}>
                  {docProfile.tags.slice(0, 8).map((t) => (
                    <span key={t} style={{ fontSize: 12, padding: "2px 8px", borderRadius: 999, background: "#f3f4f6", border: "1px solid #e5e7eb" }}>
                      {t}
                    </span>
                  ))}
                </div>
              ) : null}
            </div>
          ) : null}

          <div style={{ marginTop: 10, display: "flex", gap: 8, alignItems: "center", flexWrap: "wrap" }}>
            <label style={{ fontSize: 12, color: "#555" }}>
              top_k{" "}
              <input value={topK} onChange={(e) => setTopK(Number(e.target.value || 5))} type="number" min={1} max={50} style={{ width: 80, padding: 6, marginLeft: 6 }} />
            </label>
            <button onClick={() => setMessages([{ role: "assistant", content: "New chat started. Ask away." }])}>New chat</button>
          </div>
          <label style={{ display: "flex", gap: 8, alignItems: "center", marginTop: 10, fontSize: 12, color: "#555" }}>
            <input type="checkbox" checked={showTrace} onChange={(e) => setShowTrace(e.target.checked)} />
            Show agent trace (dev)
          </label>
        </div>
      </aside>

      <main style={{ flex: 1, display: "flex", flexDirection: "column" }}>
        <div style={{ padding: "12px 16px", borderBottom: "1px solid #eee", display: "flex", justifyContent: "space-between", gap: 12 }}>
          <div style={{ color: "#333" }}>
            Scope:{" "}
            <code style={{ fontSize: 12 }}>
              project={selectedProjectId ? selectedProjectId.slice(0, 8) : "∗"} kb={selectedKbId ? selectedKbId.slice(0, 8) : "∗"} doc=
              {selectedDocId ? selectedDocId.slice(0, 8) : "∗"}
            </code>
          </div>
          <div style={{ color: "#666", fontSize: 12 }}>{busy ? "Thinking…" : "Ready"}</div>
        </div>

        <div ref={listRef} style={{ flex: 1, overflowY: "auto", padding: 16, background: "#fafafa" }}>
          {messages.map((m, idx) => {
            const steps = m?.meta?.steps;
            const runId = m?.meta?.run_id;
            return (
              <div key={idx}>
                <Bubble role={m.role}>{m.content}</Bubble>
                {m.role === "assistant" && showTrace && runId ? (
                  <details style={{ marginTop: -2, marginBottom: 10 }}>
                    <summary style={{ cursor: "pointer", color: "#555", fontSize: 12 }}>Trace (run_id={runId.slice(0, 8)}…)</summary>
                    <pre style={{ marginTop: 8, padding: 10, background: "#fff", border: "1px solid #eee", borderRadius: 10, overflowX: "auto", fontSize: 12, whiteSpace: "pre-wrap" }}>
                      {steps ? pretty(steps) : "No steps returned (toggle on before sending)."}
                    </pre>
                  </details>
                ) : null}
              </div>
            );
          })}
        </div>

        <div style={{ borderTop: "1px solid #eee", padding: 12, background: "#fff" }}>
          {error ? (
            <div style={{ marginBottom: 10, color: "#b00020", whiteSpace: "pre-wrap" }}>
              {error}
            </div>
          ) : null}
          <div style={{ display: "flex", gap: 10, alignItems: "flex-end" }}>
            <textarea
              value={draft}
              onChange={(e) => setDraft(e.target.value)}
              placeholder="Type a message…"
              rows={2}
              style={{ flex: 1, resize: "vertical", padding: 10, borderRadius: 10, border: "1px solid #ddd" }}
              onKeyDown={(e) => {
                if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) send();
              }}
            />
            <button disabled={busy || !draft.trim()} onClick={send} style={{ padding: "10px 14px" }}>
              Send
            </button>
          </div>
          <div style={{ marginTop: 6, fontSize: 12, color: "#777" }}>Tip: Press Ctrl/Cmd+Enter to send.</div>
        </div>
      </main>
    </div>
  );
}

