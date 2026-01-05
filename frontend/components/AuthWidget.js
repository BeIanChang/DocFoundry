import { useEffect, useMemo, useState } from "react";
import { decodeJwtPayload, getApiBase, getToken, setToken } from "./auth";

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

export default function AuthWidget() {
  const [open, setOpen] = useState(false);
  const [token, setTokenState] = useState("");
  const [email, setEmail] = useState("test@example.com");
  const [password, setPassword] = useState("test123");
  const [name, setName] = useState("Test");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    const sync = () => setTokenState(getToken());
    sync();
    window.addEventListener("docfoundry_token_change", sync);
    window.addEventListener("storage", sync);
    return () => {
      window.removeEventListener("docfoundry_token_change", sync);
      window.removeEventListener("storage", sync);
    };
  }, []);

  const identity = useMemo(() => {
    if (!token) return { loggedIn: false, label: "Not logged in" };
    const payload = decodeJwtPayload(token) || {};
    const label = payload.email ? `Logged in: ${payload.email}` : "Logged in";
    return { loggedIn: true, label };
  }, [token]);

  const doLogin = async () => {
    setBusy(true);
    setError("");
    try {
      const base = getApiBase();
      const data = await apiFetch(base, "/auth/login", { method: "POST", body: { email, password } });
      setToken(data.token || "");
      setOpen(false);
    } catch (e) {
      setError(e?.message || String(e));
    } finally {
      setBusy(false);
    }
  };

  const doRegister = async () => {
    setBusy(true);
    setError("");
    try {
      const base = getApiBase();
      const data = await apiFetch(base, "/auth/register", { method: "POST", body: { email, password, name } });
      setToken(data.token || "");
      setOpen(false);
    } catch (e) {
      setError(e?.message || String(e));
    } finally {
      setBusy(false);
    }
  };

  const doLogout = () => {
    setToken("");
    setOpen(false);
  };

  return (
    <div style={{ position: "relative" }}>
      <button className={`tab ${identity.loggedIn ? "tabActive" : ""}`} onClick={() => setOpen((v) => !v)}>
        {identity.label}
      </button>
      {open ? (
        <div
          className="card"
          style={{
            position: "absolute",
            right: 0,
            top: 44,
            width: 320,
            padding: 14,
          }}
        >
          <div style={{ display: "flex", justifyContent: "space-between", gap: 10, alignItems: "center" }}>
            <div style={{ fontWeight: 800 }}>Account</div>
            <button className="btn" onClick={() => setOpen(false)}>
              Close
            </button>
          </div>

          {identity.loggedIn ? (
            <div style={{ marginTop: 12 }}>
              <div className="muted" style={{ fontSize: 12, lineHeight: 1.4 }}>
                You’re authenticated for agent/chat endpoints.
              </div>
              <div style={{ marginTop: 12 }}>
                <button className="btn btnPrimary" onClick={doLogout} disabled={busy}>
                  Logout
                </button>
              </div>
            </div>
          ) : (
            <div style={{ marginTop: 12, display: "grid", gap: 10 }}>
              <div>
                <label className="fieldLabel">Email</label>
                <input className="field" value={email} onChange={(e) => setEmail(e.target.value)} />
              </div>
              <div>
                <label className="fieldLabel">Password</label>
                <input className="field" value={password} onChange={(e) => setPassword(e.target.value)} type="password" />
              </div>
              <div>
                <label className="fieldLabel">Name (register)</label>
                <input className="field" value={name} onChange={(e) => setName(e.target.value)} />
              </div>
              {error ? (
                <div style={{ color: "#b00020", fontSize: 12, whiteSpace: "pre-wrap" }}>
                  {error}
                </div>
              ) : null}
              <div style={{ display: "flex", gap: 10, flexWrap: "wrap" }}>
                <button className="btn btnPrimary" onClick={doLogin} disabled={busy}>
                  Login
                </button>
                <button className="btn" onClick={doRegister} disabled={busy}>
                  Register
                </button>
              </div>
            </div>
          )}
        </div>
      ) : null}
    </div>
  );
}
