from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, List, Optional

from app.embeddings.llm import chat


@dataclass(frozen=True)
class DocumentProfileResult:
    doc_type: Optional[str]
    year_start: Optional[int]
    year_end: Optional[int]
    summary: str
    tags: List[str]
    meta: Dict[str, Any]


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


def _fallback_profile(text: str) -> DocumentProfileResult:
    cleaned = (text or "").strip()
    summary = cleaned[:600] + ("..." if len(cleaned) > 600 else "")
    tags: List[str] = []

    lowered = cleaned.lower()
    if any(k in lowered for k in ["income statement", "balance sheet", "cash flow", "profit", "revenue", "net income", "p&l"]):
        tags.append("finance")
    if any(k in lowered for k in ["contract", "agreement", "term", "party", "liability"]):
        tags.append("legal")
    if any(k in lowered for k in ["policy", "procedure", "hr", "employee"]):
        tags.append("policy")

    years = [int(y) for y in re.findall(r"\b(20\d{2})\b", cleaned)][:8]
    year_start = min(years) if years else None
    year_end = max(years) if years else None

    return DocumentProfileResult(
        doc_type=None,
        year_start=year_start,
        year_end=year_end,
        summary=summary or "(empty document)",
        tags=tags,
        meta={"fallback": True},
    )


def generate_document_profile(*, title: str, file_name: str, text: str) -> DocumentProfileResult:
    """
    Generate a compact, searchable profile for a document version.
    Uses the configured LLM provider when available; falls back to simple heuristics.
    """
    snippet = (text or "")[:6000]
    messages = [
        {
            "role": "system",
            "content": (
                "You are building a searchable profile for an internal document. "
                "Return ONLY valid JSON (no markdown)."
            ),
        },
        {
            "role": "user",
            "content": (
                f"Document title: {title}\n"
                f"Filename: {file_name}\n\n"
                "Extract a compact profile:\n"
                '- doc_type: short category like "financial_report", "invoice", "contract", "meeting_notes", "policy", "other"\n'
                "- year_start: integer year or null\n"
                "- year_end: integer year or null\n"
                "- tags: array of short strings\n"
                "- summary: 2-4 sentences, factual, no speculation\n\n"
                "Text excerpt:\n"
                f"{snippet}"
            ),
        },
    ]

    try:
        resp = chat(messages)
        data = _extract_json_obj(resp.get("content") or "")
        if not isinstance(data, dict):
            return _fallback_profile(text)

        doc_type = data.get("doc_type")
        year_start = data.get("year_start")
        year_end = data.get("year_end")
        summary = data.get("summary")
        tags = data.get("tags") or []

        if not isinstance(summary, str) or not summary.strip():
            return _fallback_profile(text)
        if not isinstance(tags, list):
            tags = []
        tags = [str(t).strip() for t in tags if str(t).strip()][:16]

        def _as_int(v):
            try:
                return int(v)
            except Exception:
                return None

        return DocumentProfileResult(
            doc_type=str(doc_type).strip() if doc_type else None,
            year_start=_as_int(year_start),
            year_end=_as_int(year_end),
            summary=summary.strip(),
            tags=tags,
            meta={"llm": {"provider": resp.get("provider"), "model": resp.get("model")}},
        )
    except Exception:
        return _fallback_profile(text)

