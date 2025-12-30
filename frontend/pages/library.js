import { useEffect, useMemo, useState } from "react";
import Layout from "../components/Layout";
import { getApiBase, setApiBase } from "../components/auth";

function pretty(obj) {
  try {
    return JSON.stringify(obj, null, 2);
  } catch {
    return String(obj);
  }
}

async function apiFetch(base, path, { method = "GET", body } = {}) {
  const headers = {};
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

function TreeItem({ depth, label, selected, onClick, children, collapsed, onToggle }) {
  return (
    <div>
      <div
        onClick={onClick}
        style={{
          padding: "6px 8px",
          marginLeft: depth * 10,
          borderRadius: 10,
          cursor: "pointer",
          display: "flex",
          alignItems: "center",
          gap: 8,
          background: selected ? "rgba(255,122,24,.12)" : "transparent",
          border: selected ? "1px solid rgba(255,122,24,.25)" : "1px solid transparent",
        }}
      >
        {onToggle ? (
          <button
            className="btn"
            onClick={(e) => {
              e.stopPropagation();
              onToggle();
            }}
            style={{ padding: "4px 8px", borderRadius: 10, height: 30 }}
            aria-label={collapsed ? "Expand" : "Collapse"}
          >
            {collapsed ? "+" : "–"}
          </button>
        ) : (
          <span style={{ width: 34 }} />
        )}
        <div style={{ fontSize: 13, fontWeight: 600, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{label}</div>
      </div>
      {children}
    </div>
  );
}

export default function LibraryPage() {
  const [apiBase, setApiBaseState] = useState("http://localhost:8000");
  const chunkIdFromUrl = useQueryParam("chunk_id");
  const documentIdFromUrl = useQueryParam("document_id");
  const versionIdFromUrl = useQueryParam("version_id");

  const [tree, setTree] = useState(null);

  const [selectedProjectId, setSelectedProjectId] = useState("");
  const [selectedKbId, setSelectedKbId] = useState("");
  const [selectedDocId, setSelectedDocId] = useState("");
  const [selectedVersionId, setSelectedVersionId] = useState("");

  const [docProfile, setDocProfile] = useState(null);
  const [chunk, setChunk] = useState(null);
  const [versionMeta, setVersionMeta] = useState(null);
  const [parsedText, setParsedText] = useState("");
  const [activeTab, setActiveTab] = useState("parsed"); // parsed|raw
  const [error, setError] = useState("");
  const [collapsed, setCollapsed] = useState({});

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
      .then((t) => setTree(t))
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
  }, [documentIdFromUrl]);

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
      await refreshTree();
    } catch (e) {
      setError(e?.message || String(e));
    }
  };

  return (
    <Layout title="Library" subtitle="VSCode-like explorer on the left; open raw file or parsed text on the right." right={right}>
      <div style={{ display: "grid", gridTemplateColumns: "320px 1fr", gap: 14, alignItems: "start" }}>
        <div className="card" style={{ padding: 14 }}>
          <div style={{ fontWeight: 800, marginBottom: 10 }}>Explorer</div>
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
            {tree?.projects?.length ? (
              tree.projects.map((p) => {
                const pKey = `p:${p.id}`;
                const pCollapsed = !!collapsed[pKey];
                const pSelected = selectedProjectId === p.id;
                return (
                  <TreeItem
                    key={p.id}
                    depth={0}
                    label={`Project: ${p.name}`}
                    selected={pSelected}
                    collapsed={pCollapsed}
                    onToggle={() => toggleCollapsed(pKey)}
                    onClick={() => {
                      setSelectedProjectId(p.id);
                      setSelectedKbId("");
                      setSelectedDocId("");
                      setSelectedVersionId("");
                    }}
                  >
                    {!pCollapsed
                      ? (p.knowledge_bases || []).map((kb) => {
                          const kbKey = `kb:${kb.id}`;
                          const kbCollapsed = !!collapsed[kbKey];
                          const kbSelected = selectedKbId === kb.id;
                          return (
                            <TreeItem
                              key={kb.id}
                              depth={1}
                              label={`KB: ${kb.name}`}
                              selected={kbSelected}
                              collapsed={kbCollapsed}
                              onToggle={() => toggleCollapsed(kbKey)}
                              onClick={() => {
                                setSelectedProjectId(p.id);
                                setSelectedKbId(kb.id);
                                setSelectedDocId("");
                                setSelectedVersionId("");
                              }}
                            >
                              {!kbCollapsed
                                ? (kb.documents || []).map((d) => {
                                    const dKey = `d:${d.id}`;
                                    const dCollapsed = !!collapsed[dKey];
                                    const dSelected = selectedDocId === d.id;
                                    return (
                                      <TreeItem
                                        key={d.id}
                                        depth={2}
                                        label={`Doc: ${d.title || "Untitled"}`}
                                        selected={dSelected}
                                        collapsed={dCollapsed}
                                        onToggle={() => toggleCollapsed(dKey)}
                                        onClick={() => {
                                          setSelectedProjectId(p.id);
                                          setSelectedKbId(kb.id);
                                          setSelectedDocId(d.id);
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
                                                  depth={3}
                                                  label={`v${v.version_number}${suffix}`}
                                                  selected={vSelected}
                                                  onClick={() => {
                                                    setSelectedProjectId(p.id);
                                                    setSelectedKbId(kb.id);
                                                    setSelectedDocId(d.id);
                                                    setSelectedVersionId(v.id);
                                                    openLink({ document_id: d.id, version_id: v.id, chunk_id: "" });
                                                  }}
                                                />
                                              );
                                            })
                                          : null}
                                      </TreeItem>
                                    );
                                  })
                                : null}
                            </TreeItem>
                          );
                        })
                      : null}
                  </TreeItem>
                );
              })
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
      </div>
    </Layout>
  );
}
