import os
from pathlib import Path
from typing import Any, Dict, List, Optional
import requests

try:
    from cerebras.cloud.sdk import Cerebras  # type: ignore
except Exception:
    Cerebras = None

DEFAULT_PROVIDER = os.environ.get("LLM_PROVIDER", "stub")
DEFAULT_CEREBRAS_MODEL = os.environ.get("CEREBRAS_MODEL", "qwen-3-235b-a22b-instruct-2507")


def _load_api_key_from_file(path: Path) -> str:
    """
    Supports:
    - raw key in first non-empty line
    - KEY=VALUE format (e.g. CEREBRAS_API_KEY=...)
    """
    raw = path.read_text(encoding="utf-8", errors="ignore")
    for line in raw.splitlines():
        s = line.strip()
        if not s or s.startswith("#"):
            continue
        if "=" in s:
            k, v = s.split("=", 1)
            if k.strip() in {"CEREBRAS_API_KEY", "API_KEY", "LLM_API_KEY"}:
                return v.strip()
            continue
        return s
    return ""


def _get_cerebras_api_key() -> str:
    # Highest priority: explicit env var
    env = (os.environ.get("CEREBRAS_API_KEY") or "").strip()
    if env:
        return env

    # Optional: explicit file env var
    key_file = (os.environ.get("CEREBRAS_API_KEY_FILE") or os.environ.get("APIKEY_FILE") or "").strip()
    if key_file:
        p = Path(key_file).expanduser()
        if p.exists():
            return _load_api_key_from_file(p)

    # Fallback: repo root `APIKEY` file (commonly gitignored)
    try:
        repo_root = Path(__file__).resolve().parents[3]
        for candidate in (repo_root / "APIKEY", repo_root / "backend" / "APIKEY"):
            if candidate.exists():
                key = _load_api_key_from_file(candidate)
                if key:
                    return key
    except Exception:
        pass

    return ""


def chat(
    messages: List[Dict[str, str]],
    *,
    model: Optional[str] = None,
    temperature: float = 0.2,
    max_tokens: Optional[int] = None,
) -> Dict[str, Any]:
    """
    Minimal chat interface used by the agent.
    Returns: {provider, model, content}
    """
    provider = DEFAULT_PROVIDER
    if provider == "stub":
        joined = "\n\n".join([m.get("content", "") for m in messages if m.get("role") != "system"])
        return {"provider": provider, "model": None, "content": f"[stubbed chat]\n{joined}"}

    if provider != "cerebras":
        raise RuntimeError(f"unsupported provider {provider}")

    api_key = _get_cerebras_api_key()
    if not api_key:
        raise RuntimeError("missing API key (set CEREBRAS_API_KEY or provide APIKEY file)")

    chosen_model = model or DEFAULT_CEREBRAS_MODEL

    # Prefer official SDK; fall back to raw HTTP if not installed
    if Cerebras:
        client = Cerebras(api_key=api_key)
        kwargs: Dict[str, Any] = {"model": chosen_model, "messages": messages, "temperature": temperature}
        if max_tokens is not None:
            kwargs["max_tokens"] = max_tokens
        resp = client.chat.completions.create(**kwargs)
        choices = getattr(resp, "choices", []) or []
        if choices and getattr(choices[0], "message", None):
            msg = choices[0].message
            content = msg.get("content") if isinstance(msg, dict) else msg.content
        else:
            content = ""
        return {"provider": provider, "model": chosen_model, "content": content}

    payload: Dict[str, Any] = {"model": chosen_model, "messages": messages, "temperature": temperature}
    if max_tokens is not None:
        payload["max_tokens"] = max_tokens
    resp = requests.post(
        "https://api.cerebras.ai/v1/chat/completions",
        json=payload,
        headers={"Authorization": f"Bearer {api_key}"},
        timeout=30,
    )
    resp.raise_for_status()
    data = resp.json()
    choices = data.get("choices") or []
    content = choices[0]["message"]["content"] if choices else ""
    return {"provider": provider, "model": chosen_model, "content": content}


def generate_answer(query: str, contexts: List[Dict]) -> Dict:
    """
    Minimal LLM abstraction.
    - provider 'stub' just echoes the context.
    - provider 'cerebras' calls Cerebras (OpenAI-compatible) chat completions.
    """
    provider = DEFAULT_PROVIDER
    if provider == "stub":
        joined = "\n\n".join([c.get("text", "") for c in contexts])
        answer = f"[stubbed answer] Query: {query}\nContext:\n{joined}"
        return {"answer": answer, "provider": provider}
    elif provider == "cerebras":
        model = DEFAULT_CEREBRAS_MODEL
        prompt_context = "\n\n".join([c.get("text", "") for c in contexts])
        messages = [
            {"role": "system", "content": "You are a helpful assistant. Use the provided context to answer."},
            {"role": "user", "content": f"Question: {query}\n\nContext:\n{prompt_context}"},
        ]
        try:
            resp = chat(messages, model=model)
            content = resp.get("content") or ""
            if not content:
                content = "[cerebras] no content returned"
            return {"answer": content, "provider": provider, "model": resp.get("model")}
        except Exception as exc:
            return {"answer": f"[cerebras] request failed: {exc}", "provider": provider, "model": model}
    else:
        # Placeholder for future providers
        joined = "\n\n".join([c.get("text", "") for c in contexts])
        return {"answer": f"[unsupported provider {provider}] Context:\n{joined}", "provider": provider}
