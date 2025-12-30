export function getApiBase() {
  if (typeof window === "undefined") return "http://localhost:8000";
  return window.localStorage.getItem("docfoundry_api_base") || "http://localhost:8000";
}

export function setApiBase(base) {
  if (typeof window === "undefined") return;
  window.localStorage.setItem("docfoundry_api_base", base);
  window.dispatchEvent(new Event("docfoundry_api_base_change"));
}

export function getToken() {
  if (typeof window === "undefined") return "";
  return window.localStorage.getItem("docfoundry_token") || "";
}

export function setToken(token) {
  if (typeof window === "undefined") return;
  if (token) window.localStorage.setItem("docfoundry_token", token);
  else window.localStorage.removeItem("docfoundry_token");
  window.dispatchEvent(new Event("docfoundry_token_change"));
}

export function decodeJwtPayload(token) {
  try {
    const parts = String(token).split(".");
    if (parts.length < 2) return null;
    const b64 = parts[1].replace(/-/g, "+").replace(/_/g, "/");
    const pad = "=".repeat((4 - (b64.length % 4)) % 4);
    const json = atob(b64 + pad);
    return JSON.parse(json);
  } catch {
    return null;
  }
}

