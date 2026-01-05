"""Optional cross-encoder based reranking for retrieval results."""
from __future__ import annotations

import asyncio
import logging
from typing import Any

from app.config import settings

try:  # Optional heavy dependency
    from sentence_transformers import CrossEncoder  # type: ignore
except Exception:  # pragma: no cover - fallback when package missing
    CrossEncoder = None  # type: ignore[misc]

logger = logging.getLogger(__name__)


class RerankService:
    """Provides score-based reranking using a sentence-transformers cross encoder."""

    def __init__(
        self,
        *,
        model_name: str | None = None,
        enabled: bool | None = None,
        max_candidates: int | None = None,
    ) -> None:
        requested = model_name or settings.reranker_model
        self.model_name = requested
        flag = enabled if enabled is not None else settings.reranker_enabled
        self.enabled = bool(flag and CrossEncoder is not None)
        self.max_candidates = max_candidates or settings.reranker_max_candidates
        self._model: CrossEncoder | None = None
        self._lock = asyncio.Lock()

        if flag and CrossEncoder is None:
            logger.warning("Reranker enabled but sentence-transformers is unavailable; skipping load")

    async def _ensure_model(self) -> CrossEncoder | None:
        if not self.enabled:
            return None
        if self._model is not None:
            return self._model
        async with self._lock:
            if self._model is not None:
                return self._model
            try:
                loop = asyncio.get_running_loop()
            except RuntimeError:  # pragma: no cover - should not happen under FastAPI
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
            try:
                self._model = await loop.run_in_executor(None, CrossEncoder, self.model_name)  # type: ignore[arg-type]
                logger.info("Loaded reranker model", extra={"model": self.model_name})
            except Exception as exc:  # pragma: no cover - download failures
                logger.warning("Failed to load reranker model", extra={"model": self.model_name, "error": str(exc)})
                self.enabled = False
                self._model = None
            return self._model

    def is_available(self) -> bool:
        return self.enabled and self._model is not None

    async def rerank(
        self,
        query: str,
        items: list[dict[str, Any]],
        *,
        top_k: int | None = None,
    ) -> list[dict[str, Any]]:
        if not self.enabled or not items:
            return items

        model = await self._ensure_model()
        if model is None:
            return items

        limit = min(len(items), self.max_candidates)
        candidates = items[:limit]
        pairs = [(query, str(candidate.get("text", ""))) for candidate in candidates]

        loop = asyncio.get_running_loop()

        def _predict() -> list[float]:
            scores = model.predict(pairs, convert_to_numpy=True)  # type: ignore[call-arg]
            return scores.tolist() if hasattr(scores, "tolist") else list(scores)

        try:
            scores = await loop.run_in_executor(None, _predict)
        except Exception as exc:  # pragma: no cover - runtime errors
            logger.warning("Reranker prediction failed", extra={"error": str(exc)})
            return items

        ranked = []
        for candidate, score in zip(candidates, scores, strict=False):
            enriched = dict(candidate)
            enriched["rerank_score"] = float(score)
            ranked.append(enriched)

        ranked.sort(key=lambda entry: entry.get("rerank_score", 0.0), reverse=True)
        if top_k is not None and top_k > 0:
            ranked = ranked[:top_k]
        return ranked
