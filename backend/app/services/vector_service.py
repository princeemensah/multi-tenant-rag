"""Qdrant vector store integration with tenant isolation."""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Dict, List, Optional
from uuid import uuid4

from qdrant_client import AsyncQdrantClient, QdrantClient
from qdrant_client.http import models
from qdrant_client.http.models import (
    Distance,
    FieldCondition,
    Filter,
    MatchAny,
    MatchValue,
    PointStruct,
    Range,
    VectorParams,
)

from app.config import settings

logger = logging.getLogger(__name__)


@dataclass
class VectorSearchResults:
    """Normalized shape for vector search responses."""

    items: List[Dict[str, Any]]
    next_offset: Optional[int] = None
    has_more: bool = False

    def to_payload(self) -> Dict[str, Any]:
        return {
            "items": self.items,
            "next_offset": self.next_offset,
            "has_more": self.has_more,
        }

    @classmethod
    def from_payload(cls, payload: Dict[str, Any]) -> "VectorSearchResults":
        return cls(
            items=list(payload.get("items", [])),
            next_offset=payload.get("next_offset"),
            has_more=bool(payload.get("has_more", False)),
        )


class QdrantVectorService:
    """Coordinates vector store interactions with strict tenant scoping."""

    def __init__(self) -> None:
        self.default_collection = "multi_tenant_documents"
        self.embedding_dimension = settings.embedding_dimension

        common_kwargs = self._build_client_kwargs()

        self.client = QdrantClient(**common_kwargs)
        self.async_client = AsyncQdrantClient(**common_kwargs)

    def _build_client_kwargs(self) -> Dict[str, Any]:
        """Construct client keyword arguments supporting host or full URL values."""

        host_value = (settings.qdrant_host or "").strip()
        kwargs: Dict[str, Any] = {
            "api_key": settings.qdrant_api_key,
            "timeout": 30.0,
            "prefer_grpc": False,
            "check_compatibility": False,
        }

        if host_value.startswith("http://") or host_value.startswith("https://"):
            kwargs["url"] = host_value.rstrip("/")
        else:
            kwargs["host"] = host_value or "localhost"
            kwargs["port"] = settings.qdrant_port
            kwargs["https"] = False

        return kwargs

    async def init_collection(self, collection_name: Optional[str] = None) -> bool:
        collection = collection_name or self.default_collection
        try:
            collections = await self.async_client.get_collections()
            if collection not in [item.name for item in collections.collections]:
                await self.async_client.create_collection(
                    collection_name=collection,
                    vectors_config=VectorParams(size=self.embedding_dimension, distance=Distance.COSINE),
                )
                await self.async_client.create_payload_index(
                    collection_name=collection,
                    field_name="tenant_id",
                    field_schema=models.PayloadSchemaType.KEYWORD,
                )
                await self.async_client.create_payload_index(
                    collection_name=collection,
                    field_name="document_id",
                    field_schema=models.PayloadSchemaType.KEYWORD,
                )
                await self.async_client.create_payload_index(
                    collection_name=collection,
                    field_name="document_type",
                    field_schema=models.PayloadSchemaType.KEYWORD,
                )
                await self.async_client.create_payload_index(
                    collection_name=collection,
                    field_name="created_at_ts",
                    field_schema=models.PayloadSchemaType.FLOAT,
                )
                logger.info("Created Qdrant collection", extra={"collection": collection})
            return True
        except Exception as exc:
            logger.error("Failed to initialize Qdrant collection", extra={"error": str(exc)})
            return False

    async def add_documents(
        self,
        tenant_id: str,
        documents: List[Dict[str, Any]],
        collection_name: Optional[str] = None,
    ) -> bool:
        collection = collection_name or self.default_collection
        if not documents:
            return True

        points: List[PointStruct] = []
        for doc in documents:
            payload = dict(doc.get("metadata", {}))
            payload.update(
                {
                    "tenant_id": tenant_id,
                    "document_id": doc.get("document_id"),
                    "chunk_id": doc.get("chunk_id"),
                    "text": doc.get("text", ""),
                    "source": doc.get("source", ""),
                    "page_number": doc.get("page_number"),
                    "chunk_index": doc.get("chunk_index", 0),
                    "tags": doc.get("tags", []),
                }
            )
            if doc.get("document_type"):
                payload["document_type"] = doc["document_type"]
            if doc.get("created_at"):
                payload["created_at"] = doc["created_at"]
            if doc.get("created_at_ts") is not None:
                payload["created_at_ts"] = doc["created_at_ts"]
            points.append(PointStruct(id=str(uuid4()), vector=doc["embedding"], payload=payload))

        try:
            await self.async_client.upsert(collection_name=collection, points=points)
            logger.info("Stored document chunks in Qdrant", extra={"count": len(points), "tenant": tenant_id})
            return True
        except Exception as exc:
            logger.error("Failed to upsert vectors", extra={"error": str(exc)})
            return False

    async def search_documents(
        self,
        tenant_id: str,
        query_embedding: List[float],
        limit: int = 10,
        score_threshold: float = 0.7,
        filter_conditions: Optional[Dict[str, Any]] = None,
        collection_name: Optional[str] = None,
        offset: int = 0,
    ) -> VectorSearchResults:
        collection = collection_name or self.default_collection

        conditions = [FieldCondition(key="tenant_id", match=MatchValue(value=tenant_id))]
        if filter_conditions:
            for key, value in filter_conditions.items():
                if isinstance(value, list):
                    conditions.append(FieldCondition(key=key, match=MatchAny(any=value)))
                elif isinstance(value, dict):
                    range_kwargs: Dict[str, float] = {}
                    gte = value.get("gte")
                    lte = value.get("lte")
                    if gte is not None:
                        range_kwargs["gte"] = float(gte)
                    if lte is not None:
                        range_kwargs["lte"] = float(lte)
                    if range_kwargs:
                        conditions.append(FieldCondition(key=key, range=Range(**range_kwargs)))
                else:
                    conditions.append(FieldCondition(key=key, match=MatchValue(value=value)))

        search_filter = Filter(must=conditions)

        try:
            page_size = max(1, limit)
            start_offset = max(0, offset)
            fetch_limit = page_size + 1

            results = await self.async_client.search(
                collection_name=collection,
                query_vector=query_embedding,
                query_filter=search_filter,
                limit=fetch_limit,
                offset=start_offset,
                score_threshold=score_threshold,
                with_payload=True,
                with_vectors=False,
            )

            formatted: List[Dict[str, Any]] = []
            for item in results[:page_size]:
                payload = item.payload or {}
                formatted.append(
                    {
                        "id": item.id,
                        "score": item.score,
                        "text": payload.get("text", ""),
                        "document_id": payload.get("document_id"),
                        "chunk_id": payload.get("chunk_id"),
                        "source": payload.get("source", ""),
                        "page_number": payload.get("page_number"),
                        "chunk_index": payload.get("chunk_index", 0),
                        "metadata": {
                            k: v
                            for k, v in payload.items()
                            if k
                            not in {
                                "text",
                                "tenant_id",
                                "document_id",
                                "chunk_id",
                                "source",
                                "chunk_index",
                            }
                        },
                    }
                )
            has_more = len(results) > page_size
            next_offset = start_offset + page_size if has_more else None
            return VectorSearchResults(items=formatted, next_offset=next_offset, has_more=has_more)
        except Exception as exc:
            logger.error("Vector search failed", extra={"error": str(exc)})
            return VectorSearchResults(items=[], next_offset=None, has_more=False)

    async def delete_document(
        self,
        tenant_id: str,
        document_id: str,
        collection_name: Optional[str] = None,
    ) -> bool:
        collection = collection_name or self.default_collection

        delete_filter = Filter(
            must=[
                FieldCondition(key="tenant_id", match=MatchValue(value=tenant_id)),
                FieldCondition(key="document_id", match=MatchValue(value=document_id)),
            ]
        )

        try:
            await self.async_client.delete(collection_name=collection, points_selector=delete_filter)
            logger.info("Removed document vectors", extra={"document_id": document_id, "tenant": tenant_id})
            return True
        except Exception as exc:
            logger.error("Failed to delete document vectors", extra={"error": str(exc)})
            return False

    async def delete_tenant_data(self, tenant_id: str, collection_name: Optional[str] = None) -> bool:
        collection = collection_name or self.default_collection
        delete_filter = Filter(must=[FieldCondition(key="tenant_id", match=MatchValue(value=tenant_id))])
        try:
            await self.async_client.delete(collection_name=collection, points_selector=delete_filter)
            logger.warning("Removed all tenant vectors", extra={"tenant": tenant_id})
            return True
        except Exception as exc:
            logger.error("Failed to purge tenant vectors", extra={"error": str(exc)})
            return False

    async def get_collection_info(self, collection_name: Optional[str] = None) -> Optional[Dict[str, Any]]:
        collection = collection_name or self.default_collection
        try:
            info = await self.async_client.get_collection(collection)
            return {
                "name": collection,
                "vector_size": info.config.params.vectors.size,
                "distance": info.config.params.vectors.distance.value,
                "points_count": info.points_count,
                "segments_count": info.segments_count,
                "status": info.status.value,
            }
        except Exception as exc:
            logger.error("Failed to fetch collection info", extra={"error": str(exc)})
            return None

    async def health_check(self) -> bool:
        try:
            await self.async_client.get_collections()
            return True
        except Exception as exc:
            logger.error("Qdrant health check failed", extra={"error": str(exc)})
            return False
