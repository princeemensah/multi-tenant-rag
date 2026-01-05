"""Query and RAG endpoints."""
from __future__ import annotations

import json
import logging
import time
from collections.abc import AsyncGenerator
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

from fastapi import APIRouter, BackgroundTasks, HTTPException, status
from fastapi.responses import StreamingResponse
from qdrant_client.http.models import FieldCondition, Filter, MatchValue
from sqlalchemy import func

from app.dependencies import (
    ConversationServiceDep,
    CurrentTenantDep,
    CurrentUserDep,
    DatabaseDep,
    EmbeddingServiceDep,
    LLMServiceDep,
    RetrievalServiceDep,
    VectorServiceDep,
)
from app.models.query import Query
from app.models.query import QueryResponse as QueryResponseModel
from app.schemas.query import (
    ContextDocument,
    QueryAnalytics,
    QueryFeedback,
    QueryHistory,
    QueryResponse,
    RAGRequest,
    RAGResponse,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/queries", tags=["Queries"])


@router.get("/debug/vector-status")
async def debug_vector_status(
    current_user: CurrentUserDep,
    current_tenant: CurrentTenantDep,
    vector_service: VectorServiceDep,
):
    try:
        collection_ready = await vector_service.init_collection()
        info = await vector_service.get_collection_info()

        tenant_filter = Filter(
            must=[FieldCondition(key="tenant_id", match=MatchValue(value=str(current_tenant.id)))]
        )

        scroll = await vector_service.async_client.scroll(  # type: ignore[attr-defined]
            collection_name=vector_service.default_collection,
            scroll_filter=tenant_filter,
            limit=500,
            with_payload=True,
            with_vectors=False,
        )
        points = scroll[0] if scroll else []

        sample = [
            {
                "id": item.id,
                "document_id": item.payload.get("document_id") if item.payload else None,
                "source": (item.payload or {}).get("source"),
            }
            for item in points[:5]
        ]

        total_vectors = info.get("points_count") if info else None
        response_payload = {
            "collection_ready": collection_ready,
            "collection_info": info,
            "tenant_documents": len(points),
            "tenant_id": str(current_tenant.id),
            "total_vectors": total_vectors,
            "sample": sample,
            "sample_documents": sample,
        }
        return response_payload
    except Exception as exc:  # pragma: no cover - diagnostics only
        logger.error("Vector status probe failed", extra={"error": str(exc)})
        return {
            "collection_ready": False,
            "collection_info": None,
            "tenant_documents": 0,
            "error": str(exc),
        }


@router.get("/debug/search-test")
async def debug_search_test(
    query: str = "test",
    max_chunks: int = 5,
    score_threshold: float = 0.3,
    current_user: CurrentUserDep = None,
    current_tenant: CurrentTenantDep = None,
    vector_service: VectorServiceDep = None,
    embedding_service: EmbeddingServiceDep = None,
    retrieval_service: RetrievalServiceDep = None,
):
    try:
        query_embedding = []
        if embedding_service is not None:  # type: ignore[truthy-function]
            query_embedding = await embedding_service.embed_text(query)  # type: ignore[union-attr]

        if retrieval_service is not None:
            results = await retrieval_service.search_documents(
                tenant_id=str(current_tenant.id),
                query=query,
                limit=max(1, max_chunks),
                score_threshold=score_threshold,
                use_cache=False,
            )
        else:
            results = await vector_service.search_documents(  # type: ignore[union-attr]
                tenant_id=str(current_tenant.id),
                query_embedding=query_embedding,
                limit=max(1, max_chunks),
                score_threshold=score_threshold,
            )

        scores = [item.get("score", 0.0) for item in results.items]
        top_results = results.items[: min(len(results.items), 3)]
        return {
            "query": query,
            "tenant_id": str(current_tenant.id),
            "embedding_dimension": len(query_embedding) if query_embedding else None,
            "score_threshold": score_threshold,
            "results_found": len(results.items),
            "scores": scores,
            "all_scores": scores,
            "sample": top_results,
            "results": top_results,
            "has_more": results.has_more,
            "next_offset": results.next_offset,
        }
    except Exception as exc:
        logger.error("Search test failed", extra={"error": str(exc)})
        return {
            "query": query,
            "embedding_dimension": 0,
            "results_found": 0,
            "error": str(exc),
        }


def _format_context_documents(results: list[dict[str, object]]) -> list[ContextDocument]:
    formatted: list[ContextDocument] = []
    for result in results:
        chunk_id = str(result.get("chunk_id") or result.get("id") or uuid4())
        document_id = str(result.get("document_id") or uuid4())
        source = str(result.get("source") or (result.get("metadata", {}) or {}).get("filename", "Unknown"))
        metadata = result.get("metadata")
        if isinstance(metadata, str):
            try:
                metadata = json.loads(metadata)
            except json.JSONDecodeError:
                metadata = {"raw": metadata}
        if not isinstance(metadata, dict):
            metadata = {}

        formatted.append(
            ContextDocument(
                chunk_id=chunk_id,
                document_id=document_id,
                score=float(result.get("score", 0.0)),
                text=str(result.get("text", "")),
                source=source,
                page_number=result.get("page_number"),
                chunk_index=int(result.get("chunk_index", 0)),
                doc_metadata=metadata,
            )
        )
    return formatted


async def _record_failed_query(
    db: DatabaseDep,
    tenant_id: UUID,
    user_id: UUID,
    request_data: RAGRequest,
    error: Exception,
    elapsed_ms: float,
) -> None:
    failed = Query(
        tenant_id=tenant_id,
        user_id=user_id,
        query_text=request_data.query,
        query_type="rag",
        processing_time_ms=elapsed_ms,
        status="failed",
        query_metadata={"error": str(error), "request": request_data.model_dump(mode="json")},
    )
    db.add(failed)
    db.commit()


@router.post("/rag", response_model=RAGResponse)
async def generate_rag_response(
    rag_request: RAGRequest,
    background_tasks: BackgroundTasks,
    current_user: CurrentUserDep,
    current_tenant: CurrentTenantDep,
    db: DatabaseDep,
    llm_service: LLMServiceDep,
    retrieval_service: RetrievalServiceDep,
    conversation_service: ConversationServiceDep,
):
    start = time.perf_counter()
    try:
        session_uuid: UUID | None = None
        session = None
        if rag_request.session_id:
            try:
                session_uuid = UUID(rag_request.session_id)
            except ValueError as exc:
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid session_id") from exc

            session = conversation_service.get_session(db, current_tenant.id, session_uuid)
            if not session:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Conversation session not found")
        else:
            session = conversation_service.create_session(
                db,
                current_tenant.id,
                created_by_id=current_user.id,
            )
            session_uuid = session.id

        if session is None or session_uuid is None:  # defensive guard
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Conversation session unavailable")

        history_limit = 12
        prior_messages = conversation_service.get_context(db, current_tenant.id, session_uuid, limit=history_limit)
        llm_conversation_history = [*prior_messages, {"role": "user", "content": rag_request.query}]
        conversation_turn = session.message_count // 2 + 1

        filter_conditions: dict[str, object] = {}
        if rag_request.document_ids:
            filter_conditions["document_id"] = [str(doc_id) for doc_id in rag_request.document_ids]
        if rag_request.tags:
            filter_conditions["tags"] = rag_request.tags

        search_results = await retrieval_service.search_documents(
            tenant_id=str(current_tenant.id),
            query=rag_request.query,
            limit=rag_request.max_chunks,
            score_threshold=rag_request.score_threshold,
            filter_conditions=filter_conditions or None,
        )

        context_documents = _format_context_documents(search_results.items)
        context_text = "\n\n".join(doc.text for doc in context_documents)

        user_metadata = {
            "source": "rag_endpoint",
            "document_filters": filter_conditions or None,
            "temperature": rag_request.temperature,
            "conversation_turn": conversation_turn,
        }
        conversation_service.add_message(
            db,
            current_tenant.id,
            session_uuid,
            role="user",
            content=rag_request.query,
            author_id=current_user.id,
            metadata=user_metadata,
        )

        provider = rag_request.llm_provider or current_tenant.llm_provider
        model = rag_request.llm_model or current_tenant.llm_model

        llm_response = await llm_service.generate_rag_response(
            query=rag_request.query,
            context_documents=[doc.model_dump() for doc in context_documents],
            provider=provider,
            model=model,
            system_prompt=rag_request.system_prompt,
            temperature=rag_request.temperature,
            max_tokens=rag_request.max_tokens,
            stream=False,
            conversation_history=llm_conversation_history,
        )

        elapsed_ms = (time.perf_counter() - start) * 1000.0

        retrieved_docs: list[UUID] = []
        for doc in context_documents:
            try:
                retrieved_docs.append(UUID(doc.document_id))
            except ValueError:
                retrieved_docs.append(uuid4())

        assistant_metadata = {
            "source": "rag_endpoint",
            "retrieved_chunks": [doc.chunk_id for doc in context_documents],
            "retrieved_documents": [doc.document_id for doc in context_documents],
            "provider": provider,
            "model": model,
            "conversation_turn": conversation_turn,
        }
        conversation_service.add_message(
            db,
            current_tenant.id,
            session_uuid,
            role="assistant",
            content=llm_response.content,
            author_id=None,
            metadata=assistant_metadata,
        )

        session_id_value = str(session_uuid)

        query_record = Query(
            tenant_id=current_tenant.id,
            user_id=current_user.id,
            query_text=rag_request.query,
            query_type="rag",
            processing_time_ms=elapsed_ms,
            status="completed",
            retrieved_chunks_count=len(context_documents),
            retrieved_documents=retrieved_docs,
            similarity_threshold=rag_request.score_threshold,
            llm_provider=provider,
            llm_model=model,
            input_tokens=llm_response.usage.get("prompt_tokens", 0),
            output_tokens=llm_response.usage.get("completion_tokens", 0),
            total_tokens=llm_response.usage.get("total_tokens", 0),
            estimated_cost=llm_response.metadata.get("estimated_cost", 0.0),
            session_id=session_id_value,
            conversation_turn=conversation_turn,
            query_metadata={"rag_request": rag_request.model_dump(mode="json")},
        )
        db.add(query_record)
        db.commit()
        db.refresh(query_record)

        response_record = QueryResponseModel(
            query_id=query_record.id,
            response_text=llm_response.content,
            response_format="text",
            context_used=context_text,
            context_chunks=[doc.chunk_id for doc in context_documents],
            confidence_score=None,
            source_attribution=[doc.source for doc in context_documents],
            contains_citations=False,
            fact_checked=False,
            is_cached=llm_response.metadata.get("cache_hit", False),
            cache_hit=llm_response.metadata.get("cache_hit", False),
        )
        db.add(response_record)
        db.commit()

        background_tasks.add_task(db.expunge, response_record)

        rag_payload = RAGResponse(
            query_id=query_record.id,
            query=rag_request.query,
            response=llm_response.content,
            context_documents=context_documents,
            context_used=context_text,
            processing_time_ms=elapsed_ms,
            llm_provider=provider,
            llm_model=model,
            input_tokens=llm_response.usage.get("prompt_tokens", 0),
            output_tokens=llm_response.usage.get("completion_tokens", 0),
            total_tokens=llm_response.usage.get("total_tokens", 0),
            estimated_cost=llm_response.metadata.get("estimated_cost", 0.0),
            confidence_score=None,
            source_attribution=list({doc.source for doc in context_documents}),
            contains_citations=False,
            session_id=session_id_value,
            conversation_turn=conversation_turn,
            created_at=query_record.created_at,
        )
        logger.info(
            "RAG query completed",
            extra={
                "query_id": str(query_record.id),
                "tenant_id": str(current_tenant.id),
                "user": current_user.email,
                "retrieved_chunks": len(context_documents),
            },
        )
        return rag_payload
    except Exception as exc:
        elapsed_ms = (time.perf_counter() - start) * 1000.0
        logger.exception("RAG query failed", extra={"error": str(exc)})
        try:
            await _record_failed_query(db, current_tenant.id, current_user.id, rag_request, exc, elapsed_ms)
        except Exception:  # pragma: no cover - defensive
            db.rollback()
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="RAG query failed") from exc


@router.post("/rag/stream")
async def generate_rag_response_stream(
    rag_request: RAGRequest,
    current_user: CurrentUserDep,
    current_tenant: CurrentTenantDep,
    db: DatabaseDep,
    llm_service: LLMServiceDep,
    retrieval_service: RetrievalServiceDep,
    conversation_service: ConversationServiceDep,
):
    try:
        session_uuid: UUID | None = None
        session = None
        if rag_request.session_id:
            try:
                session_uuid = UUID(rag_request.session_id)
            except ValueError as exc:
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid session_id") from exc

            session = conversation_service.get_session(db, current_tenant.id, session_uuid)
            if not session:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Conversation session not found")
        else:
            session = conversation_service.create_session(
                db,
                current_tenant.id,
                created_by_id=current_user.id,
            )
            session_uuid = session.id

        if session is None or session_uuid is None:
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Conversation session unavailable")

        history_limit = 12
        prior_messages = conversation_service.get_context(db, current_tenant.id, session_uuid, limit=history_limit)
        conversation_turn = session.message_count // 2 + 1
        llm_conversation_history = [*prior_messages, {"role": "user", "content": rag_request.query}]

        filter_conditions: dict[str, object] = {}
        if rag_request.document_ids:
            filter_conditions["document_id"] = [str(doc_id) for doc_id in rag_request.document_ids]
        if rag_request.tags:
            filter_conditions["tags"] = rag_request.tags

        search_results = await retrieval_service.search_documents(
            tenant_id=str(current_tenant.id),
            query=rag_request.query,
            limit=rag_request.max_chunks,
            score_threshold=rag_request.score_threshold,
            filter_conditions=filter_conditions or None,
        )

        formatted_context = _format_context_documents(search_results.items)
        context_payload = [doc.model_dump() for doc in formatted_context]

        user_metadata = {
            "source": "rag_endpoint",
            "document_filters": filter_conditions or None,
            "temperature": rag_request.temperature,
            "conversation_turn": conversation_turn,
        }
        conversation_service.add_message(
            db,
            current_tenant.id,
            session_uuid,
            role="user",
            content=rag_request.query,
            author_id=current_user.id,
            metadata=user_metadata,
        )

        provider = rag_request.llm_provider or current_tenant.llm_provider
        model = rag_request.llm_model or current_tenant.llm_model

        stream = await llm_service.generate_rag_response(
            query=rag_request.query,
            context_documents=context_payload,
            provider=provider,
            model=model,
            system_prompt=rag_request.system_prompt,
            temperature=rag_request.temperature,
            max_tokens=rag_request.max_tokens,
            stream=True,
            conversation_history=llm_conversation_history,
        )

        accumulated_chunks: list[str] = []

        async def iterator() -> AsyncGenerator[str, None]:
            try:
                async for chunk in stream:
                    if chunk:
                        accumulated_chunks.append(chunk)
                        yield f"data: {chunk}\n\n"
                full_response = "".join(accumulated_chunks)
                assistant_metadata = {
                    "source": "rag_endpoint",
                    "retrieved_chunks": [doc.chunk_id for doc in formatted_context],
                    "retrieved_documents": [doc.document_id for doc in formatted_context],
                    "provider": provider,
                    "model": model,
                    "conversation_turn": conversation_turn,
                }
                if full_response:
                    conversation_service.add_message(
                        db,
                        current_tenant.id,
                        session_uuid,
                        role="assistant",
                        content=full_response,
                        author_id=None,
                        metadata=assistant_metadata,
                    )
                yield "data: [DONE]\n\n"
            except Exception as exc:  # pragma: no cover - streaming best-effort
                logger.error("Streaming RAG failed", extra={"error": str(exc)})
                yield "data: [ERROR]\n\n"

        return StreamingResponse(
            iterator(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
            },
        )
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("Unable to start streaming response", extra={"error": str(exc)})
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Streaming RAG query failed") from exc


@router.get("/history", response_model=QueryHistory)
async def get_query_history(
    current_user: CurrentUserDep,
    current_tenant: CurrentTenantDep,
    db: DatabaseDep,
    skip: int = 0,
    limit: int = 20,
    session_id: str | None = None,
):
    try:
        query = (
            db.query(Query)
            .filter(Query.tenant_id == current_tenant.id, Query.user_id == current_user.id)
            .order_by(Query.created_at.desc())
        )
        if session_id:
            query = query.filter(Query.session_id == session_id)

        total = query.count()
        page = max(1, skip // max(limit, 1) + 1)
        size = max(limit, 1)
        items = query.offset(max(skip, 0)).limit(size).all()

        return QueryHistory(queries=items, total=total, page=page, size=size, pages=(total + size - 1) // size)
    except Exception as exc:
        logger.error("Failed to fetch query history", extra={"error": str(exc)})
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to get query history") from exc


@router.get("/{query_id}", response_model=QueryResponse)
async def get_query(
    query_id: UUID,
    current_user: CurrentUserDep,
    current_tenant: CurrentTenantDep,
    db: DatabaseDep,
):
    record = (
        db.query(Query)
        .filter(Query.id == query_id, Query.tenant_id == current_tenant.id, Query.user_id == current_user.id)
        .first()
    )
    if not record:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Query not found")
    return record


@router.post("/{query_id}/feedback")
async def submit_query_feedback(
    query_id: UUID,
    feedback: QueryFeedback,
    current_user: CurrentUserDep,
    current_tenant: CurrentTenantDep,
    db: DatabaseDep,
):
    record = (
        db.query(Query)
        .filter(Query.id == query_id, Query.tenant_id == current_tenant.id, Query.user_id == current_user.id)
        .first()
    )
    if not record:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Query not found")

    record.user_rating = feedback.rating
    record.feedback = feedback.feedback
    db.commit()
    logger.info("Query feedback submitted", extra={"query_id": str(query_id), "user": current_user.email})
    return {"message": "Feedback submitted"}


@router.get("/analytics/summary", response_model=QueryAnalytics)
async def get_query_analytics(
    current_user: CurrentUserDep,
    current_tenant: CurrentTenantDep,
    db: DatabaseDep,
    days: int = 30,
):
    try:
        end_date = datetime.now(UTC)
        start_date = end_date - timedelta(days=max(days, 1))
        today_start = end_date.replace(hour=0, minute=0, second=0, microsecond=0)

        base_query = db.query(Query).filter(
            Query.tenant_id == current_tenant.id,
            Query.created_at >= start_date,
            Query.created_at <= end_date,
        )

        total_queries = base_query.count()
        queries_today = db.query(Query).filter(Query.tenant_id == current_tenant.id, Query.created_at >= today_start).count()
        avg_processing_time = (
            base_query.filter(Query.processing_time_ms.isnot(None))
            .with_entities(func.avg(Query.processing_time_ms))
            .scalar()
            or 0.0
        )
        avg_tokens = (
            base_query.filter(Query.total_tokens > 0)
            .with_entities(func.avg(Query.total_tokens))
            .scalar()
            or 0.0
        )
        total_cost = base_query.with_entities(func.sum(Query.estimated_cost)).scalar() or 0.0

        type_counts = (
            db.query(Query.query_type, func.count(Query.id))
            .filter(Query.tenant_id == current_tenant.id, Query.created_at >= start_date)
            .group_by(Query.query_type)
            .all()
        )
        top_query_types = [{"type": query_type, "count": count} for query_type, count in type_counts]

        avg_rating = (
            base_query.filter(Query.user_rating.isnot(None))
            .with_entities(func.avg(Query.user_rating))
            .scalar()
        )

        return QueryAnalytics(
            tenant_id=current_tenant.id,
            total_queries=total_queries,
            queries_today=queries_today,
            avg_processing_time_ms=float(avg_processing_time),
            avg_tokens_per_query=float(avg_tokens),
            total_cost=float(total_cost),
            top_query_types=top_query_types,
            avg_rating=float(avg_rating) if avg_rating is not None else None,
            period_start=start_date,
            period_end=end_date,
        )
    except Exception as exc:
        logger.error("Failed to compute query analytics", extra={"error": str(exc)})
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to get query analytics") from exc
