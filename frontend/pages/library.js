import { useEffect, useMemo, useRef, useState } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import Layout from "../components/Layout";
import { getApiBase, getToken } from "../components/auth";

function pretty(obj) {
  try {
    return JSON.stringify(obj, null, 2);
  } catch {
    return String(obj);
  }
}

function injectCitationLinks(text) {
  const raw = String(text || "");
  if (!raw) return "";
  return raw.replace(/\[([SWD]\d+(?:\s*,\s*[SWD]\d+)*)\]/g, (_, inner) => {
    const tags = inner.split(/\s*,\s*/);
    return tags.map((t) => `[${t}](cite:${t})`).join(" ");
  });
}

async function apiFetch(base, path, { method = "GET", body, token, isForm } = {}) {
  const headers = {};
  if (token) headers.Authorization = `Bearer ${token}`;
  if (body && !isForm) headers["Content-Type"] = "application/json";
  const res = await fetch(`${base}${path}`, { method, headers, body: body ? (isForm ? body : JSON.stringify(body)) : undefined });
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

function TreeItem({ depth, label, selected, onClick, onDoubleClick, children, collapsed, onToggle, meta, icon, editing, editValue, onEditChange, onEditKeyDown, onEditBlur }) {
  return (
    <div>
      <div
        onClick={onClick}
        onDoubleClick={onDoubleClick}
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
        {icon ? <span className="treeIcon" aria-hidden="true">{icon}</span> : null}
        {editing ? (
          <input
            className="treeEditInput"
            value={editValue}
            onChange={(e) => onEditChange?.(e.target.value)}
            onKeyDown={onEditKeyDown}
            onBlur={onEditBlur}
            autoFocus
          />
        ) : (
          <div className="treeLabel" title={label}>
            {label}
          </div>
        )}
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

function renderMarkdownWithCitations(text, citations, onOpen) {
  const byTag = new Map((citations || []).map((c) => [c.tag || "", c]));
  const markdown = injectCitationLinks(text);
  return (
    <ReactMarkdown
      remarkPlugins={[remarkGfm]}
      className="chatMarkdown"
      components={{
        a: ({ href, children }) => {
          if (href && href.startsWith("cite:")) {
            const tag = href.replace("cite:", "");
            const cite = byTag.get(tag);
            if (!cite) return <span>{children}</span>;
            return (
              <button className="inlineCite" type="button" onClick={() => onOpen?.(cite)}>
                {tag}
              </button>
            );
          }
          return (
            <a href={href} target="_blank" rel="noreferrer">
              {children}
            </a>
          );
        },
      }}
    >
      {markdown}
    </ReactMarkdown>
  );
}

function sanitizeAnswer(text) {
  if (!text) return "";
  const withoutIds = text
    .replace(/[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}/gi, "")
    .replace(/\b(document_id|kb_id|project_id|chunk_id|version_id|doc_id)\s*[:=]\s*[\w-]+/gi, "")
    .replace(/Sources?\s*[:：]\s*(\[[SWD]\d+\]\s*)+/gi, "")
    .replace(/Sources?\s*[:：]\s*([SWD]\d+\s*)+/gi, "")
    .replace(/\[\[([SWD]\d+)\]\]/g, "[$1]")
    .replace(/([SWD]\d+)(?=[SWD]\d+)/g, "$1 ")
    .replace(/\b([SWD]\d+)\b/g, "[$1]")
    .replace(/\s{2,}/g, " ")
    .replace(/\n{3,}/g, "\n\n");
  return withoutIds.trim();
}

export default function LibraryPage() {
  const [apiBase, setApiBaseState] = useState(() => getApiBase());
  const chunkIdFromUrl = useQueryParam("chunk_id");
  const documentIdFromUrl = useQueryParam("document_id");

  const [tree, setTree] = useState(null);
  const [projectOptions, setProjectOptions] = useState([]);
  const [selectedProjectIds, setSelectedProjectIds] = useState([]);
  const [projectMenuOpen, setProjectMenuOpen] = useState(false);
  const projectMenuRef = useRef(null);

  const [selectedProjectId, setSelectedProjectId] = useState("");
  const [selectedKbId, setSelectedKbId] = useState("");
  const [selectedDocId, setSelectedDocId] = useState("");
  const [selectedFolderId, setSelectedFolderId] = useState("");

  const [docProfile, setDocProfile] = useState(null);
  const [profileEdit, setProfileEdit] = useState(false);
  const [profileDraft, setProfileDraft] = useState(null);
  const [chunk, setChunk] = useState(null);
  const [documentMeta, setDocumentMeta] = useState(null);
  const [parsedText, setParsedText] = useState("");
  const [activeTab, setActiveTab] = useState("parsed"); // parsed|raw
  const [error, setError] = useState("");
  const [collapsed, setCollapsed] = useState({});

  const [chatSessions, setChatSessions] = useState([
    {
      id: "default",
      name: "Chat 1",
      messages: [{ role: "assistant", content: "Ask me about your documents. Use the file tree to scope context." }],
    },
  ]);
  const [activeChatId, setActiveChatId] = useState("default");
  const [chatNameEditId, setChatNameEditId] = useState(null);
  const [chatNameDraft, setChatNameDraft] = useState("");
  const [draft, setDraft] = useState("");
  const [busy, setBusy] = useState(false);
  const [showTrace, setShowTrace] = useState(false);
  const chatRef = useRef(null);
  const [uploadFile, setUploadFile] = useState(null);
  const [uploadBusy, setUploadBusy] = useState(false);
  const filePickerRef = useRef(null);
  const [editTarget, setEditTarget] = useState(null);
  const [editValue, setEditValue] = useState("");

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
    try {
      const raw = localStorage.getItem("docfoundry_chats");
      const parsed = raw ? JSON.parse(raw) : null;
      if (parsed?.sessions && Array.isArray(parsed.sessions) && parsed.sessions.length) {
        setChatSessions(parsed.sessions);
        setActiveChatId(parsed.activeId || parsed.sessions[0].id);
      }
    } catch {}
  }, []);

  useEffect(() => {
    try {
      localStorage.setItem(
        "docfoundry_chats",
        JSON.stringify({ sessions: chatSessions, activeId: activeChatId })
      );
    } catch {}
  }, [chatSessions, activeChatId]);

  useEffect(() => {
    apiFetch(apiBase, "/library/tree")
      .then((t) => {
        const projects = (t?.projects || []).map((p) => ({ id: p.id, name: p.name }));
        setTree(t);
        setProjectOptions(projects);
        if (!selectedProjectId && projects.length) {
          setSelectedProjectId(projects[0].id);
        }
        if (!selectedProjectIds.length && projects.length) {
          setSelectedProjectIds([projects[0].id]);
        }
      })
      .catch(() => {});
  }, [apiBase]);

  useEffect(() => {
    if (!projectMenuOpen) return;
    const handleClickAway = (e) => {
      if (projectMenuRef.current && !projectMenuRef.current.contains(e.target)) {
        setProjectMenuOpen(false);
      }
    };
    window.addEventListener("mousedown", handleClickAway);
    return () => window.removeEventListener("mousedown", handleClickAway);
  }, [projectMenuOpen]);

  useEffect(() => {
    if (!selectedDocId) {
      setDocProfile(null);
      setDocumentMeta(null);
      setParsedText("");
      setProfileEdit(false);
      setProfileDraft(null);
      return;
    }
    apiFetch(apiBase, `/documents/${encodeURIComponent(selectedDocId)}/profile`)
      .then((p) => {
        setDocProfile(p);
        setProfileDraft(p);
      })
      .catch(() => setDocProfile(null));
    setError("");
    apiFetch(apiBase, `/library/documents/${encodeURIComponent(selectedDocId)}`)
      .then((v) => setDocumentMeta(v))
      .catch((e) => setError(e?.message || String(e)));
    apiFetch(apiBase, `/library/documents/${encodeURIComponent(selectedDocId)}/text`)
      .then((t) => setParsedText(t?.text || ""))
      .catch(() => setParsedText(""));
  }, [apiBase, selectedDocId]);

  useEffect(() => {
    if (!chunkIdFromUrl) return;
    setError("");
    apiFetch(apiBase, `/chunks/${encodeURIComponent(chunkIdFromUrl)}`)
      .then((c) => {
        setChunk(c);
        if (c?.document_id) setSelectedDocId(c.document_id);
      })
      .catch((e) => setError(e?.message || String(e)));
  }, [apiBase, chunkIdFromUrl]);

  useEffect(() => {
    if (documentIdFromUrl) setSelectedDocId(documentIdFromUrl);
  }, [documentIdFromUrl]);

  useEffect(() => {
    chatRef.current?.scrollTo?.({ top: chatRef.current.scrollHeight, behavior: "smooth" });
  }, [chatSessions, activeChatId, busy]);

  const openLink = (params) => {
    const url = new URL(window.location.href);
    Object.entries(params).forEach(([k, v]) => {
      if (!v) url.searchParams.delete(k);
      else url.searchParams.set(k, v);
    });
    window.history.pushState({}, "", url.toString());
    window.dispatchEvent(new PopStateEvent("popstate"));
  };

  const toggleCollapsed = (key) => setCollapsed((c) => ({ ...c, [key]: !c[key] }));

  const refreshTree = async () => {
    const t = await apiFetch(apiBase, "/library/tree");
    setTree(t);
    const projects = (t?.projects || []).map((p) => ({ id: p.id, name: p.name }));
    setProjectOptions(projects);
    if (!selectedProjectIds.length && projects.length) {
      setSelectedProjectIds([projects[0].id]);
    }
    return t;
  };

  const createProject = async () => {
    const name = window.prompt("Project name?");
    if (!name || !name.trim()) return;
    setError("");
    try {
      const proj = await apiFetch(apiBase, "/projects/", { method: "POST", body: { name: name.trim() } });
      await refreshTree();
      setSelectedProjectId(proj.id || "");
      setSelectedProjectIds((ids) => (proj.id ? Array.from(new Set([...(ids || []), proj.id])) : ids));
    } catch (e) {
      setError(e?.message || String(e));
    }
  };

  const deleteProject = async () => {
    if (!selectedProjectId) return;
    const ok = window.confirm("Delete this project and all its KBs/documents? This cannot be undone.");
    if (!ok) return;
    setError("");
    try {
      await apiFetch(apiBase, `/projects/${encodeURIComponent(selectedProjectId)}`, { method: "DELETE" });
      setSelectedProjectId("");
      setSelectedKbId("");
      setSelectedDocId("");
      setSelectedFolderId("");
      const t = await refreshTree();
      const remaining = (t?.projects || []).map((p) => p.id);
      if (remaining.length) {
        setSelectedProjectId(remaining[0]);
        setSelectedProjectIds([remaining[0]]);
      } else {
        setSelectedProjectIds([]);
      }
    } catch (e) {
      setError(e?.message || String(e));
    }
  };

  const createKb = async () => {
    if (!selectedProjectId) return;
    const name = window.prompt("KB name?");
    if (!name || !name.trim()) return;
    setError("");
    try {
      await apiFetch(apiBase, "/kb/", { method: "POST", body: { project_id: selectedProjectId, name: name.trim() } });
      await refreshTree();
    } catch (e) {
      setError(e?.message || String(e));
    }
  };

  const createDocument = async () => {
    if (!selectedKbId) return;
    filePickerRef.current?.click();
  };

  const startRename = (type, id, currentName) => {
    setEditTarget({ type, id });
    setEditValue(currentName || "");
  };

  const cancelRename = () => {
    setEditTarget(null);
    setEditValue("");
  };

  const saveRename = async () => {
    if (!editTarget) return;
    const name = editValue.trim();
    if (!name) {
      cancelRename();
      return;
    }
    setError("");
    try {
      if (editTarget.type === "project") {
        await apiFetch(apiBase, `/projects/${encodeURIComponent(editTarget.id)}`, { method: "PUT", body: { name } });
      } else if (editTarget.type === "kb") {
        await apiFetch(apiBase, `/kb/${encodeURIComponent(editTarget.id)}`, { method: "PUT", body: { name } });
      } else if (editTarget.type === "folder") {
        await apiFetch(apiBase, `/folders/${encodeURIComponent(editTarget.id)}`, { method: "PUT", body: { name } });
      } else if (editTarget.type === "doc") {
        await apiFetch(apiBase, `/documents/${encodeURIComponent(editTarget.id)}`, { method: "PUT", body: { title: name } });
      }
      await refreshTree();
    } catch (e) {
      setError(e?.message || String(e));
    } finally {
      cancelRename();
    }
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

  const deleteSelectedTarget = async () => {
    if (selectedDocId) {
      const ok = window.confirm("Delete this document and all chunks? This cannot be undone.");
      if (!ok) return;
      setError("");
      try {
        await apiFetch(apiBase, `/documents/${encodeURIComponent(selectedDocId)}`, { method: "DELETE" });
        setSelectedDocId("");
        setChunk(null);
        setParsedText("");
        setDocumentMeta(null);
        setDocProfile(null);
        setSelectedFolderId("");
        await refreshTree();
      } catch (e) {
        setError(e?.message || String(e));
      }
      return;
    }
    if (selectedFolderId) {
      const ok = window.confirm("Delete this folder? It must be empty.");
      if (!ok) return;
      setError("");
      try {
        await apiFetch(apiBase, `/folders/${encodeURIComponent(selectedFolderId)}`, { method: "DELETE" });
        setSelectedFolderId("");
        await refreshTree();
      } catch (e) {
        setError(e?.message || String(e));
      }
      return;
    }
    if (selectedKbId) {
      const ok = window.confirm("Delete this KB and all documents/folders? This cannot be undone.");
      if (!ok) return;
      setError("");
      try {
        await apiFetch(apiBase, `/kb/${encodeURIComponent(selectedKbId)}`, { method: "DELETE" });
        setSelectedKbId("");
        setSelectedDocId("");
        setSelectedFolderId("");
        await refreshTree();
      } catch (e) {
        setError(e?.message || String(e));
      }
    }
  };

  const uploadDocument = async (fileOverride) => {
    const fileToUpload = fileOverride || uploadFile;
    if (!fileToUpload || uploadBusy) return;
    if (!selectedKbId) {
      setError("Select a KB first.");
      return;
    }
    setError("");
    setUploadBusy(true);
    try {
      let docId = selectedDocId;
      if (!docId) {
        const baseTitle = uploadFile?.name ? uploadFile.name.replace(/\.[^/.]+$/, "") : "New Document";
        const doc = await apiFetch(apiBase, "/documents/", {
          method: "POST",
          body: { kb_id: selectedKbId, title: baseTitle, folder_id: selectedFolderId || null },
        });
        docId = doc.id;
        setSelectedDocId(docId);
        await refreshTree();
      }
      const form = new FormData();
      form.append("file", fileToUpload);
      await apiFetch(apiBase, `/documents/${encodeURIComponent(docId)}/upload`, { method: "POST", body: form, isForm: true });
      setUploadFile(null);
      await refreshTree();
    } catch (e) {
      setError(e?.message || String(e));
    } finally {
      setUploadBusy(false);
    }
  };

  const send = async () => {
    const text = draft.trim();
    if (!text || busy) return;
    setError("");
    setBusy(true);
    setDraft("");
    setChatSessions((sessions) =>
      sessions.map((s) =>
        s.id === activeChatId ? { ...s, messages: [...s.messages, { role: "user", content: text }] } : s
      )
    );

    const token = getToken();
    if (!token) {
      setChatSessions((sessions) =>
        sessions.map((s) =>
          s.id === activeChatId
            ? {
                ...s,
                messages: [
                  ...s.messages,
                  { role: "assistant", content: "You’re not logged in. Use the top-right Account menu to login/register, then retry." },
                ],
              }
            : s
        )
      );
      setBusy(false);
      return;
    }

    try {
      const resp = await apiFetch(apiBase, "/agent/query", {
        method: "POST",
        token,
        body: {
          message: text,
          project_id: selectedProjectIds.length === 1 ? selectedProjectIds[0] : null,
          project_ids: selectedProjectIds.length ? selectedProjectIds : null,
          kb_id: selectedKbId || null,
          folder_id: selectedDocId ? null : (selectedFolderId || null),
          document_id: selectedDocId || null,
          return_steps: !!showTrace,
        },
      });

      const citations = (resp.citations || []).slice(0, 5);
      const cleanAnswer = sanitizeAnswer(resp.answer || "");

      setChatSessions((sessions) =>
        sessions.map((s) =>
          s.id === activeChatId
            ? {
                ...s,
                messages: [
                  ...s.messages,
                  {
                    role: "assistant",
                    content: cleanAnswer,
                    meta: { run_id: resp.run_id, steps: resp.steps || null, citations: resp.citations || [] },
                  },
                ],
              }
            : s
        )
      );
    } catch (e) {
      setError(e?.message || String(e));
      setChatSessions((sessions) =>
        sessions.map((s) =>
          s.id === activeChatId
            ? { ...s, messages: [...s.messages, { role: "assistant", content: `Request failed: ${e?.message || String(e)}` }] }
            : s
        )
      );
    } finally {
      setBusy(false);
    }
  };

  const renameChat = (id, name) => {
    setChatSessions((sessions) => sessions.map((s) => (s.id === id ? { ...s, name } : s)));
  };

  const clearChatHistory = () => {
    const current = chatSessions.find((s) => s.id === activeChatId);
    if (!current) return;
    const ok = window.confirm(`Clear all messages in "${current.name}"? This cannot be undone.`);
    if (!ok) return;
    setChatSessions((sessions) =>
      sessions.map((s) =>
        s.id === activeChatId
          ? { ...s, messages: [{ role: "assistant", content: "Chat cleared. Ask anything to restart." }] }
          : s
      )
    );
  };

  const formattedParsedText = useMemo(() => {
    const raw = parsedText || "";
    const normalized = raw
      .replace(/\r\n/g, "\n")
      .replace(/[ \t]+\n/g, "\n")
      .replace(/-\n(?=\w)/g, "")
      .trim();
    const paragraphs = normalized
      .split(/\n{2,}/)
      .map((p) => p.replace(/\n/g, " ").replace(/\s{2,}/g, " ").trim())
      .filter(Boolean);
    return paragraphs.join("\n\n");
  }, [parsedText]);

  const scopeLabels = useMemo(() => {
    const out = [];
    if (selectedProjectIds.length) {
      out.push(`Projects: ${selectedProjectIds.length}`);
    }
    const selectedProject = projectOptions.find((p) => p.id === selectedProjectId);
    if (selectedProject) {
      out.push(`Current: ${selectedProject.name}`);
    }
    let kbName = null;
    let folderName = null;
    let docName = null;
    (tree?.projects || []).forEach((p) => {
      (p.knowledge_bases || []).forEach((kb) => {
        if (kb.id === selectedKbId) kbName = kb.name;
        const scanFolder = (f) => {
          if (f.id === selectedFolderId) folderName = f.name;
          (f.folders || []).forEach(scanFolder);
          (f.documents || []).forEach((d) => {
            if (d.id === selectedDocId) docName = d.title || "Untitled";
          });
        };
        (kb.folders || []).forEach(scanFolder);
        (kb.documents || []).forEach((d) => {
          if (d.id === selectedDocId) docName = d.title || "Untitled";
        });
      });
    });
    if (kbName) out.push(`KB: ${kbName}`);
    if (folderName) out.push(`Folder: ${folderName}`);
    if (docName) out.push(`Doc: ${docName}`);
    return out;
  }, [tree, projectOptions, selectedProjectId, selectedProjectIds, selectedKbId, selectedFolderId, selectedDocId]);

  return (
    <Layout title="Workspace">
      <div className="layout3">
        <div className="card" style={{ padding: 14 }}>
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", gap: 10 }}>
            <div style={{ fontWeight: 800 }}>Explorer</div>
            <div className="treeActions">
              <button className="iconBtn" title="New KB" onClick={createKb} disabled={!selectedProjectId}>
                🗂️
              </button>
              <button className="iconBtn" title="New folder" onClick={createFolder} disabled={!selectedKbId}>
                📁
              </button>
              <button className="iconBtn" title="New file" onClick={createDocument} disabled={!selectedKbId}>
                📄
              </button>
              <button
                className="iconBtn"
                title="Delete selected"
                onClick={deleteSelectedTarget}
                disabled={!selectedDocId && !selectedFolderId && !selectedKbId}
              >
                🗑️
              </button>
            </div>
          </div>
          <input
            type="file"
            ref={filePickerRef}
            style={{ display: "none" }}
            onChange={(e) => {
              const f = e.target.files?.[0] || null;
              if (f) {
                setUploadFile(f);
                uploadDocument(f);
              }
            }}
          />
          <div style={{ marginTop: 12 }}>
            <label className="fieldLabel">Projects</label>
            <div ref={projectMenuRef} style={{ position: "relative", display: "flex", gap: 8, alignItems: "center" }}>
              <button
                type="button"
                className="field dropdownTrigger"
                onClick={() => setProjectMenuOpen((v) => !v)}
              >
                {projectOptions.find((p) => p.id === selectedProjectId)?.name || (projectOptions.length ? "Select project" : "No projects yet")}
              </button>
              <button
                className="iconBtn"
                title="Rename project"
                onClick={() => {
                  const current = projectOptions.find((p) => p.id === selectedProjectId);
                  if (current) startRename("project", current.id, current.name);
                }}
                disabled={!selectedProjectId}
              >
                ✎
              </button>
              <button className="iconBtn" title="Delete project" onClick={deleteProject} disabled={!selectedProjectId}>
                🗑️
              </button>
              <button className="iconBtn" title="New project" onClick={createProject}>
                ＋
              </button>
              {projectMenuOpen ? (
                <div className="dropdownMenu">
                  <div className="dropdownHeader">
                    <span>Projects</span>
                    <button
                      className="iconBtn"
                      title="Select all"
                      onClick={() => setSelectedProjectIds(projectOptions.map((p) => p.id))}
                      disabled={!projectOptions.length}
                    >
                      All
                    </button>
                  </div>
                  {projectOptions.length ? (
                    projectOptions.map((p) => (
                      <label key={p.id} className="dropdownItem">
                        <input
                          type="checkbox"
                          checked={selectedProjectIds.includes(p.id)}
                          onChange={(e) => {
                            const checked = e.target.checked;
                            setSelectedProjectIds((ids) => {
                              if (checked) return Array.from(new Set([...(ids || []), p.id]));
                              return (ids || []).filter((id) => id !== p.id);
                            });
                          }}
                        />
                        <span
                          className="dropdownLabel"
                          onClick={() => {
                            setSelectedProjectId(p.id);
                            setSelectedKbId("");
                            setSelectedDocId("");
                            setSelectedFolderId("");
                            setSelectedProjectIds((ids) => (p.id ? Array.from(new Set([...(ids || []), p.id])) : ids));
                            setProjectMenuOpen(false);
                          }}
                        >
                          {p.name}
                        </span>
                      </label>
                    ))
                  ) : (
                    <div className="dropdownEmpty">No projects yet.</div>
                  )}
                </div>
              ) : null}
            </div>
            {editTarget?.type === "project" ? (
              <div style={{ marginTop: 8 }}>
                <input
                  className="field"
                  value={editValue}
                  onChange={(e) => setEditValue(e.target.value)}
                  onKeyDown={(e) => {
                    if (e.key === "Enter") saveRename();
                    if (e.key === "Escape") cancelRename();
                  }}
                  onBlur={saveRename}
                  autoFocus
                />
              </div>
            ) : null}
            <div style={{ marginTop: 12 }}>
              {(tree?.projects || []).length ? (
                (tree?.projects || [])
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
                        const docLabel = d.file_name || d.title || "Untitled";
                        const ext = d.file_name && d.file_name.includes(".") ? d.file_name.split(".").pop().toUpperCase() : null;
                        const isEditing = editTarget?.type === "doc" && editTarget?.id === d.id;
                        return (
                          <TreeItem
                            key={d.id}
                            depth={depth}
                            label={docLabel}
                            selected={dSelected}
                            icon="📄"
                            meta={ext || undefined}
                            collapsed={dCollapsed}
                            onToggle={() => toggleCollapsed(dKey)}
                            onClick={() => {
                              setSelectedKbId(kb.id);
                              setSelectedDocId(d.id);
                              setSelectedFolderId("");
                              openLink({ document_id: d.id, chunk_id: "" });
                            }}
                            onDoubleClick={() => startRename("doc", d.id, d.title || "")}
                            editing={isEditing}
                            editValue={isEditing ? editValue : ""}
                            onEditChange={setEditValue}
                            onEditKeyDown={(e) => {
                              if (e.key === "Enter") saveRename();
                              if (e.key === "Escape") cancelRename();
                            }}
                            onEditBlur={saveRename}
                          >
                            {null}
                          </TreeItem>
                        );
                      };

                      const renderFolder = (f, depth) => {
                        const fKey = `f:${f.id}`;
                        const fCollapsed = !!collapsed[fKey];
                        const fSelected = selectedFolderId === f.id;
                        const isEditing = editTarget?.type === "folder" && editTarget?.id === f.id;
                        return (
                          <TreeItem
                            key={f.id}
                            depth={depth}
                            label={f.name}
                            selected={fSelected}
                            icon="📁"
                            collapsed={fCollapsed}
                            onToggle={() => toggleCollapsed(fKey)}
                            meta="folder"
                            onClick={() => {
                              setSelectedKbId(kb.id);
                              setSelectedDocId("");
                              setSelectedFolderId(f.id);
                            }}
                            onDoubleClick={() => startRename("folder", f.id, f.name)}
                            editing={isEditing}
                            editValue={isEditing ? editValue : ""}
                            onEditChange={setEditValue}
                            onEditKeyDown={(e) => {
                              if (e.key === "Enter") saveRename();
                              if (e.key === "Escape") cancelRename();
                            }}
                            onEditBlur={saveRename}
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
                          icon="🗂️"
                          collapsed={kbCollapsed}
                          onToggle={() => toggleCollapsed(kbKey)}
                          meta="kb"
                          onClick={() => {
                            setSelectedKbId(kb.id);
                            setSelectedDocId("");
                            setSelectedFolderId("");
                          }}
                          onDoubleClick={() => startRename("kb", kb.id, kb.name)}
                          editing={editTarget?.type === "kb" && editTarget?.id === kb.id}
                          editValue={editTarget?.type === "kb" && editTarget?.id === kb.id ? editValue : ""}
                          onEditChange={setEditValue}
                          onEditKeyDown={(e) => {
                            if (e.key === "Enter") saveRename();
                            if (e.key === "Escape") cancelRename();
                          }}
                          onEditBlur={saveRename}
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
                  )
              ) : (
                <div className="muted" style={{ marginTop: 10 }}>
                  No projects yet.
                </div>
              )}
            </div>
          </div>
        </div>

        <div style={{ display: "grid", gap: 14 }}>
          <div className="card" style={{ padding: 16 }}>
            <div style={{ display: "flex", justifyContent: "space-between", gap: 12, flexWrap: "wrap", alignItems: "center" }}>
              <div style={{ fontWeight: 800 }}>Document</div>
              {selectedDocId ? <span className="pill">Selected</span> : <span className="pill">No document selected</span>}
            </div>
            <div style={{ marginTop: 12, display: "flex", gap: 8, flexWrap: "wrap", alignItems: "center" }}>
              <button
                className="iconBtn"
                title="Edit profile"
                onClick={() => {
                  if (!profileDraft) {
                    setProfileDraft({
                      title: "",
                      file_name: "",
                      doc_type: "",
                      year_start: "",
                      year_end: "",
                      summary: "",
                      tags: [],
                      meta: {},
                    });
                  }
                  setProfileEdit((v) => !v);
                }}
                disabled={!selectedDocId}
              >
                ✎
              </button>
            </div>
            {selectedDocId ? (
              <div style={{ marginTop: 12 }}>
                {profileEdit ? (
                  <div style={{ display: "flex", gap: 8, alignItems: "center", flexWrap: "wrap" }}>
                    <button
                      className="btn btnPrimary"
                      onClick={async () => {
                        if (!profileDraft) return;
                        setError("");
                        try {
                          const updated = await apiFetch(apiBase, `/documents/${encodeURIComponent(selectedDocId)}/profile`, {
                            method: "PUT",
                            body: {
                              title: profileDraft.title || null,
                              file_name: profileDraft.file_name || null,
                              doc_type: profileDraft.doc_type || null,
                              year_start: profileDraft.year_start ? Number(profileDraft.year_start) : null,
                              year_end: profileDraft.year_end ? Number(profileDraft.year_end) : null,
                              summary: profileDraft.summary || null,
                              tags: profileDraft.tags || [],
                              meta: profileDraft.meta || {},
                            },
                          });
                          setDocProfile(updated);
                          setProfileDraft(updated);
                          setProfileEdit(false);
                        } catch (e) {
                          setError(e?.message || String(e));
                        }
                      }}
                    >
                      Save
                    </button>
                    <button className="btn" onClick={() => setProfileEdit(false)}>
                      Cancel
                    </button>
                  </div>
                ) : null}
                {!profileEdit ? (
                  docProfile?.summary ? (
                    <div style={{ marginTop: 12, lineHeight: 1.55 }}>
                      <div style={{ display: "flex", gap: 6, flexWrap: "wrap" }}>
                        <span className="pill">{docProfile.doc_type ? `Type: ${docProfile.doc_type}` : "Type: unknown"}</span>
                        {(docProfile.year_start || docProfile.year_end) ? (
                          <span className="pill">{`Years: ${docProfile.year_start || "?"}–${docProfile.year_end || "?"}`}</span>
                        ) : null}
                        {Array.isArray(docProfile.tags) ? docProfile.tags.slice(0, 4).map((t) => (
                          <span key={t} className="pill">{t}</span>
                        )) : null}
                      </div>
                      <div style={{ marginTop: 8, maxHeight: 140, overflow: "auto" }}>
                        {docProfile.summary}
                      </div>
                    </div>
                  ) : (
                    <div className="muted" style={{ marginTop: 12 }}>
                      No profile yet (upload a file to generate one).
                    </div>
                  )
                ) : (
                  <div style={{ marginTop: 12, display: "grid", gap: 10 }}>
                    <div>
                      <label className="fieldLabel">Title</label>
                      <input
                        className="field"
                        value={profileDraft?.title || ""}
                        onChange={(e) => setProfileDraft((d) => ({ ...d, title: e.target.value }))}
                      />
                    </div>
                    <div>
                      <label className="fieldLabel">File name</label>
                      <input
                        className="field"
                        value={profileDraft?.file_name || ""}
                        onChange={(e) => setProfileDraft((d) => ({ ...d, file_name: e.target.value }))}
                      />
                    </div>
                    <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr 1fr", gap: 10 }}>
                      <div>
                        <label className="fieldLabel">Type</label>
                        <input
                          className="field"
                          value={profileDraft?.doc_type || ""}
                          onChange={(e) => setProfileDraft((d) => ({ ...d, doc_type: e.target.value }))}
                        />
                      </div>
                      <div>
                        <label className="fieldLabel">Year start</label>
                        <input
                          className="field"
                          value={profileDraft?.year_start || ""}
                          onChange={(e) => setProfileDraft((d) => ({ ...d, year_start: e.target.value }))}
                        />
                      </div>
                      <div>
                        <label className="fieldLabel">Year end</label>
                        <input
                          className="field"
                          value={profileDraft?.year_end || ""}
                          onChange={(e) => setProfileDraft((d) => ({ ...d, year_end: e.target.value }))}
                        />
                      </div>
                    </div>
                    <div>
                      <label className="fieldLabel">Tags (comma separated)</label>
                      <input
                        className="field"
                        value={Array.isArray(profileDraft?.tags) ? profileDraft.tags.join(", ") : profileDraft?.tags || ""}
                        onChange={(e) => {
                          const raw = e.target.value;
                          const tags = raw.split(",").map((t) => t.trim()).filter(Boolean);
                          setProfileDraft((d) => ({ ...d, tags }));
                        }}
                      />
                    </div>
                    <div>
                      <label className="fieldLabel">Summary</label>
                      <textarea
                        className="field"
                        rows={4}
                        value={profileDraft?.summary || ""}
                        onChange={(e) => setProfileDraft((d) => ({ ...d, summary: e.target.value }))}
                      />
                    </div>
                  </div>
                )}
              </div>
            ) : (
              <div className="muted" style={{ marginTop: 12 }}>
                Select a document to see its profile.
              </div>
            )}
          </div>

          <div className="card" style={{ padding: 16 }}>
            <div style={{ display: "flex", justifyContent: "space-between", gap: 12, flexWrap: "wrap", alignItems: "center" }}>
              <div style={{ fontWeight: 800 }}>Viewer</div>
              {selectedDocId ? <span className="pill">Selected</span> : <span className="pill">No document selected</span>}
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

            {selectedDocId ? (
              <div style={{ marginTop: 12 }}>
                <div className="muted" style={{ fontSize: 12, marginBottom: 8 }}>
                  {documentMeta?.file_name ? `file=${documentMeta.file_name}` : null}
                </div>
                {activeTab === "raw" ? (
                  <div style={{ border: "1px solid var(--border)", borderRadius: 14, overflow: "hidden", background: "#fff" }}>
                    <iframe
                      title="raw"
                      src={`${apiBase}/library/documents/${encodeURIComponent(selectedDocId)}/raw`}
                      style={{ width: "100%", height: "70vh", border: 0 }}
                    />
                  </div>
                ) : (
                  <pre style={{ margin: 0, padding: 12, borderRadius: 14, border: "1px solid var(--border)", background: "rgba(255,122,24,.03)", whiteSpace: "pre-wrap", lineHeight: 1.5, maxHeight: "70vh", overflow: "auto" }}>
                    {formattedParsedText || "(no parsed text stored for this document yet)"}
                  </pre>
                )}
              </div>
            ) : (
              <div className="muted" style={{ marginTop: 12 }}>Select a document from the explorer to view raw/parsed content.</div>
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

        <div className="card" style={{ padding: 14, display: "flex", flexDirection: "column", minHeight: "70vh", height: "72vh", maxHeight: "72vh", overflow: "hidden" }}>
          <div style={{ display: "flex", justifyContent: "space-between", gap: 10, alignItems: "center" }}>
            <div style={{ fontWeight: 800 }}>Agent Chat</div>
          </div>
          {scopeLabels.length ? (
            <div style={{ marginTop: 8, display: "flex", gap: 6, flexWrap: "wrap" }}>
              {scopeLabels.map((s) => (
                <span key={s} className="pill">{s}</span>
              ))}
            </div>
          ) : null}

          <div style={{ marginTop: 10, display: "grid", gap: 10 }}>
            <div style={{ display: "flex", gap: 8, alignItems: "center", flexWrap: "wrap" }}>
              <label className="fieldLabel" style={{ margin: 0 }}>
                Chat
              </label>
              <select
                className="field"
                value={activeChatId}
                onChange={(e) => setActiveChatId(e.target.value)}
                style={{ maxWidth: 220 }}
              >
                {chatSessions.map((s) => (
                  <option key={s.id} value={s.id}>
                    {s.name}
                  </option>
                ))}
              </select>
              <button
                className="iconBtn"
                title="New chat"
                onClick={() => {
                  const nextIndex = chatSessions.length + 1;
                  const id = `chat-${Date.now()}`;
                  const next = {
                    id,
                    name: `Chat ${nextIndex}`,
                    messages: [{ role: "assistant", content: "New chat started. Ask away." }],
                  };
                  setChatSessions((s) => [...s, next]);
                  setActiveChatId(id);
                  setChatNameEditId(id);
                  setChatNameDraft(next.name);
                }}
              >
                ＋
              </button>
              <button
                className="iconBtn"
                title="Rename chat"
                onClick={() => {
                  const current = chatSessions.find((s) => s.id === activeChatId);
                  if (!current) return;
                  setChatNameEditId(current.id);
                  setChatNameDraft(current.name);
                }}
              >
                ✎
              </button>
              <button className="iconBtn" title="Clear chat history" onClick={clearChatHistory}>
                🗑️
              </button>
              <label style={{ display: "flex", gap: 8, alignItems: "center", fontSize: 12, color: "var(--muted)" }}>
                <input type="checkbox" checked={showTrace} onChange={(e) => setShowTrace(e.target.checked)} />
                Show trace
              </label>
            </div>
            {chatNameEditId ? (
              <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
                <input
                  className="field"
                  value={chatNameDraft}
                  onChange={(e) => setChatNameDraft(e.target.value)}
                  onKeyDown={(e) => {
                    if (e.key === "Enter") {
                      renameChat(chatNameEditId, chatNameDraft.trim() || "Untitled");
                      setChatNameEditId(null);
                      setChatNameDraft("");
                    }
                    if (e.key === "Escape") {
                      setChatNameEditId(null);
                      setChatNameDraft("");
                    }
                  }}
                  onBlur={() => {
                    if (chatNameEditId) {
                      renameChat(chatNameEditId, chatNameDraft.trim() || "Untitled");
                      setChatNameEditId(null);
                      setChatNameDraft("");
                    }
                  }}
                />
                <button
                  className="btn btnPrimary"
                  onClick={() => {
                    renameChat(chatNameEditId, chatNameDraft.trim() || "Untitled");
                    setChatNameEditId(null);
                    setChatNameDraft("");
                  }}
                >
                  Save
                </button>
              </div>
            ) : null}
          </div>

          <div ref={chatRef} style={{ flex: 1, overflowY: "auto", marginTop: 12, padding: 12, background: "rgba(255,122,24,.03)", borderRadius: 14, border: "1px solid var(--border)" }}>
            {(chatSessions.find((s) => s.id === activeChatId)?.messages || []).map((m, idx) => {
              const steps = m?.meta?.steps;
              const runId = m?.meta?.run_id;
              const citations = m?.meta?.citations || [];
              return (
                <div key={idx}>
                  <Bubble role={m.role}>
                    {m.role === "assistant"
                      ? renderMarkdownWithCitations(m.content, citations, (cite) => {
                          const meta = cite.metadata || {};
                          const docId = meta.document_id || "";
                          const chunkId = cite.chunk_id || "";
                          const isWeb = meta.source === "web" && meta.url;
                          if (isWeb && meta.url) {
                            window.open(meta.url, "_blank", "noreferrer");
                            return;
                          }
                          openLink({
                            chunk_id: chunkId || "",
                            document_id: docId || "",
                          });
                        })
                      : m.content}
                  </Bubble>
                  {m.role === "assistant" && Array.isArray(m?.meta?.citations) && m.meta.citations.length ? (
                    <div style={{ marginTop: -2, marginBottom: 12, display: "flex", gap: 8, flexWrap: "wrap" }}>
                      {m.meta.citations.slice(0, 2).map((c, i) => {
                        const meta = c.metadata || {};
                        const docId = meta.document_id || "";
                        const chunkId = c.chunk_id || "";
                        const isWeb = meta.source === "web" && meta.url;
                        const label = c.tag ? c.tag : `Source ${i + 1}`;
                        return (
                          <button
                            key={`${chunkId || i}`}
                            className="pill"
                            onClick={() => {
                              if (isWeb && meta.url) {
                                window.location.assign(meta.url);
                                return;
                              }
                              openLink({
                                chunk_id: chunkId || "",
                                document_id: docId || "",
                              });
                            }}
                          >
                            {label}
                          </button>
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
