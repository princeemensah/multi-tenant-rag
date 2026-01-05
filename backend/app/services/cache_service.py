"""Redis-backed caching helpers for retrieval results and metadata."""
from __future__ import annotations

import asyncio
import hashlib
import json
import logging
from collections.abc import Iterable
from typing import Any

try:  # redis is optional during testing; degrade gracefully when absent
    from redis.asyncio import Redis
except Exception:  # pragma: no cover - fallback when redis is unavailable
    Redis = None  # type: ignore

from app.config import settings

logger = logging.getLogger(__name__)


class CacheService:
    """Thin wrapper around Redis for JSON payload caching."""

    def __init__(
        self,
        *,
        url: str | None = None,
        namespace: str | None = None,
        default_ttl: int | None = None,
        enabled: bool | None = None,
    ) -> None:
        self.url = (url or settings.redis_url).strip()
        self.namespace = (namespace or settings.cache_namespace).strip() or "mt_rag"
        self.default_ttl = default_ttl if default_ttl is not None else settings.cache_ttl_seconds
        self.enabled = enabled if enabled is not None else settings.cache_enabled
        self._client: Redis | None = None
        self._lock = asyncio.Lock()

        if not self.url:
            self.enabled = False

    async def _get_client(self) -> Redis | None:
        if not self.enabled:
            return None
        if Redis is None:  # pragma: no cover - safety when redis is not installed
            logger.warning("Redis client not available; disabling cache")
            self.enabled = False
            return None
        if self._client is not None:
            return self._client

        async with self._lock:
            if self._client is not None:
                return self._client
            try:
                self._client = Redis.from_url(
                    self.url,
                    encoding="utf-8",
                    decode_responses=True,
                )
            except Exception as exc:  # pragma: no cover - connection failures
                logger.warning("Failed to initialise Redis client", extra={"error": str(exc)})
                self.enabled = False
                self._client = None
            return self._client

    def _normalise_parts(self, parts: Iterable[Any]) -> str:
        raw_parts = [str(part) for part in parts if part is not None]
        if not raw_parts:
            return self.namespace
        raw_key = ":".join(raw_parts)
        digest = hashlib.sha256(raw_key.encode("utf-8")).hexdigest()
        return f"{self.namespace}:{digest}"

    async def get_json(self, *parts: Any) -> dict[str, Any] | None:
        client = await self._get_client()
        if client is None:
            return None
        key = self._normalise_parts(parts)
        try:
            payload = await client.get(key)
        except Exception as exc:  # pragma: no cover - network errors
            logger.warning("Cache get failed", extra={"key": key, "error": str(exc)})
            return None
        if not payload:
            return None
        try:
            return json.loads(payload)
        except json.JSONDecodeError:
            logger.warning("Cache returned invalid JSON", extra={"key": key})
            return None

    async def set_json(self, value: dict[str, Any], *parts: Any, ttl: int | None = None) -> None:
        client = await self._get_client()
        if client is None:
            return
        key = self._normalise_parts(parts)
        ttl_seconds = ttl if ttl is not None else self.default_ttl
        try:
            payload = json.dumps(value)
            if ttl_seconds > 0:
                await client.setex(key, ttl_seconds, payload)
            else:
                await client.set(key, payload)
        except Exception as exc:  # pragma: no cover - network errors
            logger.warning("Cache set failed", extra={"key": key, "error": str(exc)})

    async def delete(self, *parts: Any) -> None:
        client = await self._get_client()
        if client is None:
            return
        key = self._normalise_parts(parts)
        try:
            await client.delete(key)
        except Exception as exc:  # pragma: no cover - network errors
            logger.warning("Cache delete failed", extra={"key": key, "error": str(exc)})

    async def close(self) -> None:
        if self._client is None:
            return
        try:
            await self._client.close()  # type: ignore[func-returns-value]
        except Exception:  # pragma: no cover - best effort
            pass
        finally:
            self._client = None
