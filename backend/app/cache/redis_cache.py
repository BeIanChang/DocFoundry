from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from typing import Any, Dict, Optional

from app.agent.schemas import AgentQueryRequest, AgentQueryResponse

try:
    import redis
except Exception:  # pragma: no cover
    redis = None

try:
    import redislite
except Exception:  # pragma: no cover
    redislite = None


class AgentQueryCache:
    def __init__(self) -> None:
        self.enabled = (os.environ.get("AGENT_QUERY_CACHE_ENABLED", "false").strip().lower() in {"1", "true", "yes", "on"})
        self.ttl_seconds = max(1, int(os.environ.get("AGENT_QUERY_CACHE_TTL_SECONDS", "3600")))
        self.prefix = os.environ.get("AGENT_QUERY_CACHE_PREFIX", "agent-query-cache:v1")
        self.backend = (os.environ.get("AGENT_QUERY_CACHE_BACKEND", "redislite").strip().lower())
        self._client = None
        self._init_client()

    def _init_client(self) -> None:
        if not self.enabled or redis is None:
            return
        if self.backend == "redis":
            url = os.environ.get("REDIS_URL", "redis://127.0.0.1:16379/0")
            try:
                client = redis.Redis.from_url(url, decode_responses=True)
                client.ping()
                self._client = client
            except Exception:
                self._client = None
            return
        if redislite is None:
            return
        db_path = Path(os.environ.get("REDISLITE_PATH", "./.cache/docfoundry-redislite.db"))
        db_path.parent.mkdir(parents=True, exist_ok=True)
        try:
            self._client = redislite.Redis(str(db_path), decode_responses=True)
        except Exception:
            self._client = None

    def is_available(self) -> bool:
        return self.enabled and self._client is not None

    def _key_for(self, payload: AgentQueryRequest, user_id: Optional[str]) -> str:
        body = {
            "user_id": user_id,
            "message": payload.message,
            "project_id": payload.project_id,
            "project_ids": payload.project_ids or [],
            "folder_id": payload.folder_id,
            "kb_id": payload.kb_id,
            "document_id": payload.document_id,
            "top_k": payload.top_k,
            "max_steps": payload.max_steps,
            "mode": payload.mode,
            "loop_engine": payload.loop_engine,
            "return_steps": payload.return_steps,
        }
        digest = hashlib.sha256(json.dumps(body, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()
        return f"{self.prefix}:{digest}"

    def get(self, payload: AgentQueryRequest, user_id: Optional[str]) -> Optional[AgentQueryResponse]:
        if not self.is_available():
            return None
        raw = self._client.get(self._key_for(payload, user_id))
        if not raw:
            return None
        try:
            return AgentQueryResponse.model_validate_json(raw)
        except Exception:
            return None

    def set(self, payload: AgentQueryRequest, user_id: Optional[str], response: AgentQueryResponse) -> None:
        if not self.is_available():
            return
        try:
            self._client.setex(self._key_for(payload, user_id), self.ttl_seconds, response.model_dump_json())
        except Exception:
            return


agent_query_cache = AgentQueryCache()
