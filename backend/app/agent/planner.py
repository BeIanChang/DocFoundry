from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from app.embeddings.llm import chat


ALLOWED_ACTIONS = {
    "final",
    "list_documents",
    "get_document_profile",
    "route_documents",
    "vector_search",
    "keyword_search",
    "grep_search",
    "web_search",
    "answer_with_context",
}


@dataclass(frozen=True)
class PlanStep:
    action: str
    args: Dict[str, Any]
    rationale: str


def _extract_json_obj(text: str) -> Optional[Dict[str, Any]]:
    if not text:
        return None
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1 or end <= start:
        return None
    snippet = text[start : end + 1]
    try:
        return json.loads(snippet)
    except Exception:
        return None


def plan_next_step(
    *,
    user_message: str,
    scope: Dict[str, Any],
    observations: List[Dict[str, Any]],
    max_doc_picks: int = 5,
    top_k: int = 5,
) -> PlanStep:
    """
    Ask the LLM to choose the next action (tool call or final response).
    The planner must return ONLY JSON.
    """
    messages = [
        {
            "role": "system",
            "content": (
                "You are an agent planner. Decide the NEXT action only.\n"
                "Return ONLY valid JSON with keys: action, args, rationale.\n"
                f"Allowed actions: {sorted(ALLOWED_ACTIONS)}\n"
                "Rules:\n"
                "- Keep rationale short (<= 1 sentence).\n"
                "- Output must be JSON only. No markdown.\n"
                "- If scope.document_id is set, do NOT route other documents.\n"
                "- Avoid repeating the same action more than once in a run.\n"
                "- If a list_documents/get_document_profile observation includes context_ready=true, you already have document summaries; proceed to answer_with_context or vector_search.\n"
                "- If the user asks to list/show documents, choose list_documents.\n"
                "- If you need evidence from docs, choose route_documents (optional) then vector_search then answer_with_context.\n"
                "- Do NOT ask the user clarifying questions; make best-effort assumptions and proceed.\n"
                "- If info is missing/ambiguous, prefer vector_search and then produce a final answer that states assumptions/uncertainty.\n"
                "- Prefer keyword_search for exact terms (IDs, numbers, quoted phrases); vector_search for semantic queries.\n"
                "- Prefer grep_search for regex/pattern matching or exact multi-line snippets.\n"
                "- Use web_search for general internet queries not likely contained in the KB.\n"
                "Args schema hints:\n"
                "- final: {\"answer\": \"...\"}\n"
                "- vector_search: {\"query\": \"...\", \"top_k\": <int optional>, \"document_id\": <str optional>}\n"
                "- keyword_search: {\"query\": \"...\", \"top_k\": <int optional>, \"document_id\": <str optional>}\n"
                "- grep_search: {\"query\": \"re:... or /.../ or literal\", \"top_k\": <int optional>, \"document_id\": <str optional>}\n"
                "- web_search: {\"query\": \"...\", \"top_k\": <int optional>}\n"
            ),
        },
        {
            "role": "user",
            "content": json.dumps(
                {
                    "user_message": user_message,
                    "scope": scope,
                    "top_k": top_k,
                    "max_doc_picks": max_doc_picks,
                    "observations": observations[-6:],
                },
                ensure_ascii=False,
            ),
        },
    ]

    resp = chat(messages, temperature=0.0, max_tokens=300)
    obj = _extract_json_obj((resp.get("content") or "").strip()) or {}
    action = str(obj.get("action") or "").strip()
    args_raw = obj.get("args")
    args = args_raw if isinstance(args_raw, dict) else {}
    rationale = str(obj.get("rationale") or "").strip()

    if action not in ALLOWED_ACTIONS:
        # Safe fallback: retrieve then answer
        return PlanStep(action="vector_search", args={"query": user_message, "top_k": top_k}, rationale="fallback to retrieval")
    return PlanStep(action=action, args=args, rationale=rationale or "ok")
