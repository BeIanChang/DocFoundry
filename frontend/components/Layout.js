import Link from "next/link";
import { useRouter } from "next/router";
import AuthWidget from "./AuthWidget";

function Tab({ href, children }) {
  const router = useRouter();
  const active = router.pathname === href;
  return (
    <Link className={`tab ${active ? "tabActive" : ""}`} href={href}>
      {children}
    </Link>
  );
}

export default function Layout({ title, subtitle, children }) {
  return (
    <>
      <header className="topbar">
        <div className="topbarInner">
          <div className="brand">
            <div className="logo" aria-hidden="true" />
            <Link href="/">DocFoundry</Link>
          </div>
          <div className="muted" style={{ fontSize: 12 }}>
            Upload and parse your documents to uncover insights.
          </div>
          <div style={{ display: "flex", gap: 10, alignItems: "center" }}>
            <AuthWidget />
          </div>
        </div>
      </header>

      <div className="container">
        {(title || subtitle) && (
          <div style={{ margin: "8px 0 16px" }}>
            {title ? <h1 style={{ margin: 0, fontSize: 28, letterSpacing: -0.3 }}>{title}</h1> : null}
            {subtitle ? (
              <div className="muted" style={{ marginTop: 6, lineHeight: 1.4 }}>
                {subtitle}
              </div>
            ) : null}
          </div>
        )}
        {children}
      </div>
    </>
  );
}
