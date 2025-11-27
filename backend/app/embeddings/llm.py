import os
from typing import List, Dict

DEFAULT_PROVIDER = os.environ.get("LLM_PROVIDER", "stub")


def generate_answer(query: str, contexts: List[Dict]) -> Dict:
    """
    Minimal LLM abstraction.
    - provider 'stub' just echoes the context.
    - can be extended to call OpenAI/HF when keys are present.
    """
    provider = DEFAULT_PROVIDER
    if provider == "stub":
        joined = "\n\n".join([c.get("text", "") for c in contexts])
        answer = f"[stubbed answer] Query: {query}\nContext:\n{joined}"
        return {"answer": answer, "provider": provider}
    else:
        # Placeholder for future providers
        joined = "\n\n".join([c.get("text", "") for c in contexts])
        return {"answer": f"[unsupported provider {provider}] Context:\n{joined}", "provider": provider}
