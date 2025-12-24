export default function Home() {
  return (
    <div style={{ padding: 32, fontFamily: "system-ui, -apple-system, Segoe UI, Roboto, Arial, sans-serif", maxWidth: 860, margin: "0 auto" }}>
      <h1 style={{ marginBottom: 8 }}>DocFoundry</h1>
      <p style={{ marginTop: 0, color: "#444" }}>Pick a page:</p>
      <ul style={{ lineHeight: 1.9 }}>
        <li>
          <a href="/chat">Chat</a> — agent chat with trace + scoping
        </li>
        <li>
          <a href="/upload">Upload</a> — create project/KB/document and upload files
        </li>
      </ul>
    </div>
  );
}

