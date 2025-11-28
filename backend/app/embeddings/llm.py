import os
from typing import List, Dict
import requests

try:
    from cerebras.cloud.sdk import Cerebras  # type: ignore
except Exception:
    Cerebras = None

DEFAULT_PROVIDER = os.environ.get("LLM_PROVIDER", "stub")
DEFAULT_CEREBRAS_MODEL = os.environ.get("CEREBRAS_MODEL", "qwen-3-235b-a22b-instruct-2507")


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
        api_key = os.environ.get("CEREBRAS_API_KEY")
        if not api_key:
            return {"answer": "[cerebras] missing CEREBRAS_API_KEY", "provider": provider}
        model = DEFAULT_CEREBRAS_MODEL
        prompt_context = "\n\n".join([c.get("text", "") for c in contexts])
        messages = [
            {"role": "system", "content": "You are a helpful assistant. Use the provided context to answer."},
            {"role": "user", "content": f"Question: {query}\n\nContext:\n{prompt_context}"},
        ]
        # Prefer official SDK; fall back to raw HTTP if not installed
        if Cerebras:
            try:
                client = Cerebras(api_key=api_key)
                resp = client.chat.completions.create(model=model, messages=messages)
                choices = getattr(resp, "choices", []) or []
                if choices and getattr(choices[0], "message", None):
                    content = choices[0].message.get("content") if isinstance(choices[0].message, dict) else choices[0].message.content
                else:
                    content = "[cerebras] no choices returned"
                return {"answer": content, "provider": provider, "model": model}
            except Exception as exc:
                return {"answer": f"[cerebras] sdk failed: {exc}", "provider": provider, "model": model}
        else:
            payload = {"model": model, "messages": messages}
            try:
                resp = requests.post(
                    "https://api.cerebras.ai/v1/chat/completions",
                    json=payload,
                    headers={"Authorization": f"Bearer {api_key}"},
                    timeout=30,
                )
                resp.raise_for_status()
                data = resp.json()
                choices = data.get("choices") or []
                if choices:
                    content = choices[0]["message"]["content"]
                else:
                    content = "[cerebras] no choices returned"
                return {"answer": content, "provider": provider, "model": model}
            except Exception as exc:
                return {"answer": f"[cerebras] request failed: {exc}", "provider": provider, "model": model}
    else:
        # Placeholder for future providers
        joined = "\n\n".join([c.get("text", "") for c in contexts])
        return {"answer": f"[unsupported provider {provider}] Context:\n{joined}", "provider": provider}
