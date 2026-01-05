"""Tenant-aware retrieval orchestrator with caching and reranking."""
from __future__ import annotations

import logging
from typing import Any, Dict, Optional

from app.services.cache_service import CacheService
from app.services.embedding_service import EmbeddingService
from app.services.rerank_service import RerankService
from app.services.vector_service import QdrantVectorService, VectorSearchResults

logger = logging.getLogger(__name__)


class RetrievalService:
    """Coordinates embedding, vector search, caching, and optional reranking."""

    def __init__(
        self,
        *,
        embedding_service: Optional[EmbeddingService] = None,
        vector_service: Optional[QdrantVectorService] = None,
        cache_service: Optional[CacheService] = None,
        rerank_service: Optional[RerankService] = None,
    ) -> None:
        self.embedding_service = embedding_service or EmbeddingService()
        self.vector_service = vector_service or QdrantVectorService()
        self.cache_service = cache_service
        self.rerank_service = rerank_service

    async def search_documents(
        self,
        *,
        tenant_id: str,
        query: str,
        limit: int = 10,
        score_threshold: float = 0.3,
        filter_conditions: Optional[Dict[str, Any]] = None,
        offset: int = 0,
        use_cache: bool = True,
        rerank: bool = True,
    ) -> VectorSearchResults:
        cache_key: Optional[str] = None
        cache_payload: Optional[Dict[str, Any]] = None
        filters = filter_conditions or {}
        if (
            use_cache
            and offset == 0
            and self.cache_service is not None
            and filters.get("document_id") is None
        ):
            cache_key = self._build_cache_key(tenant_id, query, limit, score_threshold, filters)
            cache_payload = await self.cache_service.get_json(cache_key)
            if cache_payload:
                return VectorSearchResults.from_payload(cache_payload)

        query_embedding = await self.embedding_service.embed_text(query)
        results = await self.vector_service.search_documents(
            tenant_id=tenant_id,
            query_embedding=query_embedding,
            limit=limit,
            score_threshold=score_threshold,
            filter_conditions=filters or None,
            offset=offset,
        )

        if rerank and self.rerank_service and results.items:
            reranked_items = await self.rerank_service.rerank(query, results.items, top_k=limit)
            if reranked_items:
                results = VectorSearchResults(
                    items=reranked_items,
                    next_offset=results.next_offset,
                    has_more=results.has_more,
                )

        if cache_key and self.cache_service:
            await self.cache_service.set_json(results.to_payload(), cache_key)

        return results

    def _build_cache_key(
        self,
        tenant_id: str,
        query: str,
        limit: int,
        score_threshold: float,
        filters: Dict[str, Any],
    ) -> str:
        serialised_filters = self._serialise_filters(filters)
        return "|".join(
            [
                "retrieval",
                tenant_id,
                query.strip(),
                str(limit),
                f"{score_threshold:.3f}",
                serialised_filters,
            ]
        )

    def _serialise_filters(self, filters: Dict[str, Any]) -> str:
        if not filters:
            return "*"
        normalised: Dict[str, Any] = {}
        for key, value in sorted(filters.items()):
            if isinstance(value, list):
                normalised[key] = sorted(str(item) for item in value)
            elif isinstance(value, dict):
                normalised[key] = {k: value[k] for k in sorted(value)}
            else:
                normalised[key] = str(value)
        return str(normalised)
