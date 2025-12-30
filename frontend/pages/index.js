import Layout from "../components/Layout";

export default function Home() {
  return (
    <Layout
      title="DocFoundry"
      subtitle="An agentic document intelligence demo: upload documents, generate lightweight profiles, and chat with grounded answers + traces."
    >
      <div className="grid2">
        <div className="card" style={{ padding: 18 }}>
          <div className="pill">Chat</div>
          <h2 style={{ margin: "10px 0 6px" }}>Agent Chat</h2>
          <div className="muted" style={{ lineHeight: 1.5 }}>
            Ask questions scoped to a project/KB/document. View retrieval + tool traces in dev mode.
          </div>
          <div style={{ marginTop: 14 }}>
            <a className="btn btnPrimary" href="/chat">
              Open Chat
            </a>
          </div>
        </div>
        <div className="card" style={{ padding: 18 }}>
          <div className="pill">Upload</div>
          <h2 style={{ margin: "10px 0 6px" }}>Ingest Documents</h2>
          <div className="muted" style={{ lineHeight: 1.5 }}>
            Create a project/KB/document and upload files. Upload generates chunks + a document profile.
          </div>
          <div style={{ marginTop: 14 }}>
            <a className="btn btnPrimary" href="/upload">
              Open Upload
            </a>
          </div>
        </div>
      </div>
    </Layout>
  );
}
