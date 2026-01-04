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

async function apiFetch(base, path, { method = "GET", body, token } = {}) {
  const headers = {};
  if (token) headers.Authorization = `Bearer ${token}`;
  if (body) headers["Content-Type"] = "application/json";
  const res = await fetch(`${base}${path}`, { method, headers, body: body ? JSON.stringify(body) : undefined });
  const text = await res.text();
  let data = text;
  try {
    data = text ? JSON.parse(text) : null;
  } catch {}
  if (!res.ok) {
    const msg = typeof data === "string" ? data : data?.detail || text;
    throw new Error(`${res.status} ${res.statusText}: ${msg}`);
  }
  return data;
}

function useQueryParam(name) {
  const [val, setVal] = useState("");
  useEffect(() => {
    const sync = () => {
      const params = new URLSearchParams(window.location.search);
      setVal(params.get(name) || "");
    };
    sync();
    window.addEventListener("popstate", sync);
    return () => window.removeEventListener("popstate", sync);
  }, [name]);
  return val;
}

function TreeItem({ depth, label, selected, onClick, children, collapsed, onToggle, meta }) {
  return (
    <div>
      <div
        onClick={onClick}
        className={`treeRow ${selected ? "treeSelected" : ""}`}
        style={{ paddingLeft: 8 + depth * 12 }}
      >
        {onToggle ? (
          <button
            className="treeToggle"
            onClick={(e) => {
              e.stopPropagation();
              onToggle();
            }}
            aria-label={collapsed ? "Expand" : "Collapse"}
          >
            {collapsed ? ">" : "v"}
          </button>
        ) : (
          <span className="treeToggleSpacer" />
        )}
        <div className="treeLabel" title={label}>
          {label}
        </div>
        {meta ? <div className="treeMeta">{meta}</div> : null}
      </div>
      {children}
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

export default function LibraryPage() {
  const [apiBase, setApiBaseState] = useState("http://localhost:8000");
  const chunkIdFromUrl = useQueryParam("chunk_id");
  const documentIdFromUrl = useQueryParam("document_id");
  const versionIdFromUrl = useQueryParam("version_id");

  const [tree, setTree] = useState(null);
  const [projectOptions, setProjectOptions] = useState([]);

  const [selectedProjectId, setSelectedProjectId] = useState("");
  const [selectedKbId, setSelectedKbId] = useState("");
  const [selectedDocId, setSelectedDocId] = useState("");
  const [selectedVersionId, setSelectedVersionId] = useState("");
  const [selectedFolderId, setSelectedFolderId] = useState("");

  const [docProfile, setDocProfile] = useState(null);
  const [chunk, setChunk] = useState(null);
  const [versionMeta, setVersionMeta] = useState(null);
  const [parsedText, setParsedText] = useState("");
  const [activeTab, setActiveTab] = useState("parsed"); // parsed|raw
  const [error, setError] = useState("");
  const [collapsed, setCollapsed] = useState({});

  const [messages, setMessages] = useState([
    { role: "assistant", content: "Ask me about your documents. Use the file tree to scope context." },
  ]);
  const [draft, setDraft] = useState("");
  const [busy, setBusy] = useState(false);
  const [showTrace, setShowTrace] = useState(false);
  const [topK, setTopK] = useState(5);
  const chatRef = useRef(null);

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

  useEffect(() => {
    apiFetch(apiBase, "/library/tree")
      .then((t) => {
        setTree(t);
        const projects = (t?.projects || []).map((p) => ({ id: p.id, name: p.name }));
        setProjectOptions(projects);
        if (!selectedProjectId && projects.length) {
          setSelectedProjectId(projects[0].id);
        }
      })
      .catch(() => {});
  }, [apiBase]);

  useEffect(() => {
    if (!selectedDocId) {
      setDocProfile(null);
      return;
    }
    apiFetch(apiBase, `/documents/${encodeURIComponent(selectedDocId)}/profile`)
      .then((p) => setDocProfile(p))
      .catch(() => setDocProfile(null));
  }, [apiBase, selectedDocId]);

  useEffect(() => {
    if (!selectedVersionId) {
      setVersionMeta(null);
      setParsedText("");
      return;
    }
    setError("");
    apiFetch(apiBase, `/library/versions/${encodeURIComponent(selectedVersionId)}`)
      .then((v) => setVersionMeta(v))
      .catch((e) => setError(e?.message || String(e)));
    apiFetch(apiBase, `/library/versions/${encodeURIComponent(selectedVersionId)}/text`)
      .then((t) => setParsedText(t?.text || ""))
      .catch(() => setParsedText(""));
  }, [apiBase, selectedVersionId]);

  useEffect(() => {
    if (!chunkIdFromUrl) return;
    setError("");
    apiFetch(apiBase, `/chunks/${encodeURIComponent(chunkIdFromUrl)}`)
      .then((c) => {
        setChunk(c);
        if (c?.document_id) setSelectedDocId(c.document_id);
        if (c?.version_id) setSelectedVersionId(c.version_id);
      })
      .catch((e) => setError(e?.message || String(e)));
  }, [apiBase, chunkIdFromUrl]);

  useEffect(() => {
    if (documentIdFromUrl) setSelectedDocId(documentIdFromUrl);
    if (versionIdFromUrl) setSelectedVersionId(versionIdFromUrl);
  }, [documentIdFromUrl, versionIdFromUrl]);

  useEffect(() => {
    chatRef.current?.scrollTo?.({ top: chatRef.current.scrollHeight, behavior: "smooth" });
  }, [messages.length, busy]);

  const openLink = (params) => {
    const url = new URL(window.location.href);
    Object.entries(params).forEach(([k, v]) => {
      if (!v) url.searchParams.delete(k);
      else url.searchParams.set(k, v);
    });
    window.history.pushState({}, "", url.toString());
    window.dispatchEvent(new PopStateEvent("popstate"));
  };

  const right = useMemo(
    () => (
      <span className="pill">
        <span className="mono">{apiBase}</span>
      </span>
    ),
    [apiBase]
  );

  const toggleCollapsed = (key) => setCollapsed((c) => ({ ...c, [key]: !c[key] }));

  const refreshTree = async () => {
    const t = await apiFetch(apiBase, "/library/tree");
    setTree(t);
  };

  const createFolder = async () => {
    if (!selectedKbId) return;
    const name = window.prompt("Folder name?");
    if (!name) return;
    setError("");
    try {
      await apiFetch(apiBase, "/folders/", { method: "POST", body: { kb_id: selectedKbId, parent_id: selectedFolderId || null, name } });
      await refreshTree();
    } catch (e) {
      setError(e?.message || String(e));
    }
  };

  const deleteSelectedKb = async () => {
    if (!selectedKbId) return;
    const ok = window.confirm("Delete this KB and all documents/folders? This cannot be undone.");
    if (!ok) return;
    setError("");
    try {
      await apiFetch(apiBase, `/kb/${encodeURIComponent(selectedKbId)}`, { method: "DELETE" });
      setSelectedKbId("");
      setSelectedDocId("");
      setSelectedFolderId("");
      setSelectedVersionId("");
      await refreshTree();
    } catch (e) {
      setError(e?.message || String(e));
    }
  };

  const deleteSelectedDocument = async () => {
    if (!selectedDocId) return;
    const ok = window.confirm("Delete this document and all versions/chunks? This cannot be undone.");
    if (!ok) return;
    setError("");
    try {
      await apiFetch(apiBase, `/documents/${encodeURIComponent(selectedDocId)}`, { method: "DELETE" });
      setSelectedVersionId("");
      setSelectedDocId("");
      setChunk(null);
      setParsedText("");
      setVersionMeta(null);
      setDocProfile(null);
      setSelectedFolderId("");
      await refreshTree();
    } catch (e) {
      setError(e?.message || String(e));
    }
  };

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
    <Layout title="Workspace" subtitle="Left: document tree. Middle: raw/parsed viewer. Right: agent chat with citations." right={right}>
      <div className="layout3">
        <div className="card" style={{ padding: 14 }}>
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", gap: 10 }}>
            <div style={{ fontWeight: 800 }}>Explorer</div>
            <button className="btn" onClick={() => refreshTree().catch(() => {})}>
              Refresh
            </button>
          </div>
          <label className="fieldLabel">API base</label>
          <input
            className="field"
            value={apiBase}
            onChange={(e) => {
              setApiBaseState(e.target.value);
              setApiBase(e.target.value);
            }}
          />

          <div style={{ marginTop: 12 }}>
            {projectOptions.length ? (
              <>
                <label className="fieldLabel">Project domain</label>
                <select
                  className="field"
                  value={selectedProjectId}
                  onChange={(e) => {
                    setSelectedProjectId(e.target.value);
                    setSelectedKbId("");
                    setSelectedDocId("");
                    setSelectedFolderId("");
                    setSelectedVersionId("");
                  }}
                >
                  {projectOptions.map((p) => (
                    <option key={p.id} value={p.id}>
                      {p.name} ({p.id.slice(0, 6)}…)
                    </option>
                  ))}
                </select>
                <div className="treeActions">
                  <button className="btn" disabled={!selectedKbId} onClick={createFolder}>
                    New folder
                  </button>
                  <button className="btn" disabled={!selectedKbId} onClick={deleteSelectedKb}>
                    Delete KB
                  </button>
                </div>
                <div style={{ marginTop: 12 }}>
                  {(tree?.projects || [])
                    .filter((p) => p.id === selectedProjectId)
                    .map((p) =>
                      (p.knowledge_bases || []).map((kb) => {
                        const kbKey = `kb:${kb.id}`;
                        const kbCollapsed = !!collapsed[kbKey];
                        const kbSelected = selectedKbId === kb.id;

                        const renderDoc = (d, depth) => {
                          const dKey = `d:${d.id}`;
                          const dCollapsed = !!collapsed[dKey];
                          const dSelected = selectedDocId === d.id;
                          return (
                            <TreeItem
                              key={d.id}
                              depth={depth}
                              label={d.title || "Untitled"}
                              selected={dSelected}
                              collapsed={dCollapsed}
                              onToggle={() => toggleCollapsed(dKey)}
                              onClick={() => {
                                setSelectedKbId(kb.id);
                                setSelectedDocId(d.id);
                                setSelectedFolderId("");
                                setSelectedVersionId("");
                                openLink({ document_id: d.id, version_id: "", chunk_id: "" });
                              }}
                            >
                              {!dCollapsed
                                ? (d.versions || []).map((v) => {
                                    const vSelected = selectedVersionId === v.id;
                                    const suffix = v.file_name ? ` — ${v.file_name}` : "";
                                    return (
                                      <TreeItem
                                        key={v.id}
                                        depth={depth + 1}
                                        label={`v${v.version_number}${suffix}`}
                                        selected={vSelected}
                                        onClick={() => {
                                          setSelectedKbId(kb.id);
                                          setSelectedDocId(d.id);
                                          setSelectedFolderId("");
                                          setSelectedVersionId(v.id);
                                          openLink({ document_id: d.id, version_id: v.id, chunk_id: "" });
                                        }}
                                      />
                                    );
                                  })
                                : null}
                            </TreeItem>
                          );
                        };

                        const renderFolder = (f, depth) => {
                          const fKey = `f:${f.id}`;
                          const fCollapsed = !!collapsed[fKey];
                          const fSelected = selectedFolderId === f.id;
                          return (
                            <TreeItem
                              key={f.id}
                              depth={depth}
                              label={f.name}
                              selected={fSelected}
                              collapsed={fCollapsed}
                              onToggle={() => toggleCollapsed(fKey)}
                              meta="folder"
                              onClick={() => {
                                setSelectedKbId(kb.id);
                                setSelectedDocId("");
                                setSelectedVersionId("");
                                setSelectedFolderId(f.id);
                              }}
                            >
                              {!fCollapsed
                                ? [
                                    ...(f.folders || []).map((child) => renderFolder(child, depth + 1)),
                                    ...(f.documents || []).map((d) => renderDoc(d, depth + 1)),
                                  ]
                                : null}
                            </TreeItem>
                          );
                        };

                        return (
                          <TreeItem
                            key={kb.id}
                            depth={0}
                            label={kb.name}
                            selected={kbSelected}
                            collapsed={kbCollapsed}
                            onToggle={() => toggleCollapsed(kbKey)}
                            meta="kb"
                            onClick={() => {
                              setSelectedKbId(kb.id);
                              setSelectedDocId("");
                              setSelectedFolderId("");
                              setSelectedVersionId("");
                            }}
                          >
                            {!kbCollapsed
                              ? [
                                  ...(kb.folders || []).map((f) => renderFolder(f, 1)),
                                  ...(kb.documents || []).map((d) => renderDoc(d, 1)),
                                ]
                              : null}
                          </TreeItem>
                        );
                      })
                    )}
                </div>
              </>
            ) : (
              <div className="muted" style={{ marginTop: 10 }}>
                No projects yet. Create and upload in the Upload page.
              </div>
            )}
          </div>
        </div>

        <div style={{ display: "grid", gap: 14 }}>
          <div className="card" style={{ padding: 16 }}>
            <div style={{ display: "flex", justifyContent: "space-between", gap: 12, flexWrap: "wrap", alignItems: "center" }}>
              <div style={{ fontWeight: 800 }}>Document</div>
              {selectedDocId ? <span className="pill mono">{selectedDocId}</span> : <span className="pill">No document selected</span>}
            </div>
          <div style={{ marginTop: 12, display: "flex", gap: 10, flexWrap: "wrap" }}>
            <button className="btn" disabled={!selectedDocId} onClick={deleteSelectedDocument}>
              Delete document
            </button>
            <button
              className="btn"
              onClick={() => {
                refreshTree().catch(() => {});
              }}
            >
              Refresh
            </button>
          </div>
            {docProfile?.summary ? (
              <div style={{ marginTop: 12, lineHeight: 1.55 }}>
                <div className="muted" style={{ fontSize: 12 }}>
                  {docProfile.doc_type ? `type=${docProfile.doc_type}` : "type=unknown"}
                  {docProfile.year_start || docProfile.year_end ? ` · years=${docProfile.year_start || "?"}–${docProfile.year_end || "?"}` : ""}
                </div>
                <div style={{ marginTop: 8 }}>{docProfile.summary}</div>
              </div>
            ) : (
              <div className="muted" style={{ marginTop: 12 }}>
                {selectedDocId ? "No profile yet (upload a file to generate one)." : "Select a document to see its profile."}
              </div>
            )}
          </div>

          <div className="card" style={{ padding: 16 }}>
            <div style={{ display: "flex", justifyContent: "space-between", gap: 12, flexWrap: "wrap", alignItems: "center" }}>
              <div style={{ fontWeight: 800 }}>Viewer</div>
              {selectedVersionId ? <span className="pill mono">{selectedVersionId}</span> : <span className="pill">No version selected</span>}
            </div>

            <div style={{ marginTop: 12, display: "flex", gap: 8, flexWrap: "wrap" }}>
              <button className={`tab ${activeTab === "parsed" ? "tabActive" : ""}`} onClick={() => setActiveTab("parsed")}>
                Parsed
              </button>
              <button className={`tab ${activeTab === "raw" ? "tabActive" : ""}`} onClick={() => setActiveTab("raw")}>
                Raw
              </button>
              {chunkIdFromUrl ? <span className="pill mono">chunk={chunkIdFromUrl}</span> : null}
            </div>

            {error ? <div style={{ marginTop: 12, color: "#b00020", whiteSpace: "pre-wrap" }}>{error}</div> : null}

            {selectedVersionId ? (
              <div style={{ marginTop: 12 }}>
                <div className="muted" style={{ fontSize: 12, marginBottom: 8 }}>
                  {versionMeta?.file_name ? `file=${versionMeta.file_name}` : null}
                </div>
                {activeTab === "raw" ? (
                  <div style={{ border: "1px solid var(--border)", borderRadius: 14, overflow: "hidden", background: "#fff" }}>
                    <iframe
                      title="raw"
                      src={`${apiBase}/library/versions/${encodeURIComponent(selectedVersionId)}/raw`}
                      style={{ width: "100%", height: "70vh", border: 0 }}
                    />
                  </div>
                ) : (
                  <pre style={{ margin: 0, padding: 12, borderRadius: 14, border: "1px solid var(--border)", background: "rgba(255,122,24,.03)", whiteSpace: "pre-wrap", lineHeight: 1.5, maxHeight: "70vh", overflow: "auto" }}>
                    {parsedText || "(no parsed text stored for this version yet)"}
                  </pre>
                )}
              </div>
            ) : (
              <div className="muted" style={{ marginTop: 12 }}>Select a document version from the explorer to view raw/parsed content.</div>
            )}

            {chunk?.text ? (
              <div style={{ marginTop: 14, paddingTop: 14, borderTop: "1px solid var(--border)" }}>
                <div className="muted" style={{ fontSize: 12, marginBottom: 8 }}>
                  Citation chunk preview {chunk.start_pos != null && chunk.end_pos != null ? `· pos=${chunk.start_pos}–${chunk.end_pos}` : ""}
                </div>
                <pre style={{ margin: 0, padding: 12, borderRadius: 14, border: "1px solid var(--border)", background: "#fff", whiteSpace: "pre-wrap", lineHeight: 1.5 }}>
                  {chunk.text}
                </pre>
              </div>
            ) : null}
          </div>
        </div>

        <div className="card" style={{ padding: 14, display: "flex", flexDirection: "column", minHeight: "70vh" }}>
          <div style={{ display: "flex", justifyContent: "space-between", gap: 10, alignItems: "center" }}>
            <div style={{ fontWeight: 800 }}>Agent Chat</div>
            <div className="pill mono">
              {selectedProjectId ? selectedProjectId.slice(0, 6) : "∗"}/{selectedKbId ? selectedKbId.slice(0, 6) : "∗"}/{selectedDocId ? selectedDocId.slice(0, 6) : "∗"}
            </div>
          </div>

          <div style={{ marginTop: 10, display: "flex", gap: 8, flexWrap: "wrap", alignItems: "center" }}>
            <label className="fieldLabel" style={{ margin: 0 }}>
              top_k
            </label>
            <input className="field" value={topK} onChange={(e) => setTopK(Number(e.target.value || 5))} type="number" min={1} max={50} style={{ width: 110 }} />
            <button className="btn" onClick={() => setMessages([{ role: "assistant", content: "New chat started. Ask away." }])}>
              New chat
            </button>
            <label style={{ display: "flex", gap: 8, alignItems: "center", fontSize: 12, color: "var(--muted)" }}>
              <input type="checkbox" checked={showTrace} onChange={(e) => setShowTrace(e.target.checked)} />
              Show trace
            </label>
          </div>

          <div ref={chatRef} style={{ flex: 1, overflowY: "auto", marginTop: 12, padding: 12, background: "rgba(255,122,24,.03)", borderRadius: 14, border: "1px solid var(--border)" }}>
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
                        const isWeb = meta.source === "web" && meta.url;
                        const href = isWeb
                          ? meta.url
                          : chunkId
                          ? `/library?chunk_id=${encodeURIComponent(chunkId)}&document_id=${encodeURIComponent(docId)}&version_id=${encodeURIComponent(versionId)}`
                          : `/library?document_id=${encodeURIComponent(docId)}`;
                        return (
                          <a key={`${chunkId || i}`} className="pill" href={href} style={{ cursor: "pointer" }} target={isWeb ? "_blank" : undefined} rel={isWeb ? "noreferrer" : undefined}>
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
                placeholder="Ask the agent…"
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
        </div>
      </div>
    </Layout>
  );
}
