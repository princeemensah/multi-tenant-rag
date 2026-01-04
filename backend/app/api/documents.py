"""Document management endpoints."""
from __future__ import annotations

import json
import logging
import time
from datetime import UTC, datetime
from typing import Dict, List, Optional, Tuple
from uuid import UUID, uuid4

from fastapi import APIRouter, BackgroundTasks, File, Form, HTTPException, UploadFile, status
from sqlalchemy.orm import Session

from app.dependencies import (
    CurrentTenantDep,
    CurrentUserDep,
    DatabaseDep,
    DocumentServiceDep,
    EmbeddingServiceDep,
    VectorServiceDep,
)
from app.models.document import Document, DocumentChunk
from app.schemas.document import (
    DocumentBatchProcessItem,
    DocumentBatchProcessRequest,
    DocumentBatchProcessResponse,
    DocumentChunkResponse,
    DocumentList,
    DocumentProcessResponse,
    DocumentResponse,
    DocumentSearchRequest,
    DocumentSearchResponse,
    DocumentSearchResult,
    DocumentUpload,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/documents", tags=["Documents"])


def _parse_json_field(raw_value: Optional[str], default):
    if not raw_value:
        return default
    try:
        parsed = json.loads(raw_value)
        if parsed is None:
            return default
        if isinstance(default, dict) and not isinstance(parsed, dict):
            raise ValueError
        if isinstance(default, list) and not isinstance(parsed, list):
            raise ValueError
        return parsed
    except json.JSONDecodeError:
        if isinstance(default, list):
            return [item.strip() for item in raw_value.split(",") if item.strip()]
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid JSON payload")
    except ValueError:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid JSON payload type")


def _parse_upload_payload(raw_value: Optional[str]) -> Tuple[Optional[str], List[str], Dict[str, object]]:
    if not raw_value:
        return None, [], {}
    try:
        data = json.loads(raw_value)
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid upload payload JSON") from exc

    if not isinstance(data, dict):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Upload payload must be an object")

    upload = DocumentUpload.model_validate(data)
    tags = [tag.strip() for tag in upload.tags or [] if tag and tag.strip()]
    metadata = upload.metadata or {}
    return upload.title, tags, metadata


@router.post("/upload", response_model=DocumentResponse)
async def upload_document(
    background_tasks: BackgroundTasks,
    current_user: CurrentUserDep,
    current_tenant: CurrentTenantDep,
    db: DatabaseDep,
    document_service: DocumentServiceDep,
    file: UploadFile = File(...),
    metadata: Optional[str] = Form(None),
    title: Optional[str] = Form(None),
    tags: Optional[str] = Form(None),
    upload_payload: Optional[str] = Form(None),
):
    payload_title, payload_tags, payload_metadata = _parse_upload_payload(upload_payload)

    parsed_metadata = _parse_json_field(metadata, {})
    merged_metadata = {**parsed_metadata, **payload_metadata}

    parsed_tags = _parse_json_field(tags, [])
    combined_tags: List[str] = []
    for value in payload_tags + parsed_tags:
        cleaned = value.strip()
        if cleaned and cleaned not in combined_tags:
            combined_tags.append(cleaned)

    final_title = title or payload_title

    document = await document_service.upload_document(
        db=db,
        tenant_id=str(current_tenant.id),
        file=file,
        metadata=merged_metadata,
        title=final_title,
        tags=combined_tags,
    )

    background_tasks.add_task(
        document_service.process_document,
        db=db,
        document_id=str(document.id),
        tenant_id=str(current_tenant.id),
    )

    logger.info(
        "Document upload queued for processing",
        extra={"document_id": str(document.id), "tenant": str(current_tenant.id), "user": current_user.email},
    )
    return document


@router.get("/", response_model=DocumentList)
async def list_documents(
    current_user: CurrentUserDep,
    current_tenant: CurrentTenantDep,
    db: DatabaseDep,
    document_service: DocumentServiceDep,
    skip: int = 0,
    limit: int = 20,
    status_filter: Optional[str] = None,
):
    documents = document_service.list_documents(
        db=db,
        tenant_id=str(current_tenant.id),
        skip=max(skip, 0),
        limit=max(limit, 1),
        status_filter=status_filter,
    )

    total_query = db.query(Document).filter(Document.tenant_id == current_tenant.id)
    if status_filter:
        total_query = total_query.filter(Document.status == status_filter)
    total = total_query.count()
    size = max(limit, 1)
    pages = (total + size - 1) // size if size else 1

    return DocumentList(documents=documents, total=total, page=skip // size + 1, size=size, pages=pages)


@router.get("/{document_id}", response_model=DocumentResponse)
async def get_document(
    document_id: UUID,
    current_user: CurrentUserDep,
    current_tenant: CurrentTenantDep,
    db: DatabaseDep,
    document_service: DocumentServiceDep,
):
    document = document_service.get_document(db, str(document_id), str(current_tenant.id))
    if not document:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found")
    return document


@router.post("/{document_id}/process", response_model=DocumentProcessResponse)
async def process_document(
    document_id: UUID,
    background_tasks: BackgroundTasks,
    current_user: CurrentUserDep,
    current_tenant: CurrentTenantDep,
    db: DatabaseDep,
    document_service: DocumentServiceDep,
    force_reprocess: bool = False,
):
    document = document_service.get_document(db, str(document_id), str(current_tenant.id))
    if not document:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found")

    if document.status == "processed" and not force_reprocess:
        return DocumentProcessResponse(
            document_id=document.id,
            status="already_processed",
            message="Document already processed. Set force_reprocess=true to reprocess.",
            chunks_created=document.total_chunks,
        )

    background_tasks.add_task(
        document_service.process_document,
        db=db,
        document_id=str(document.id),
        tenant_id=str(current_tenant.id),
    )

    return DocumentProcessResponse(
        document_id=document.id,
        status="processing",
        message="Document processing started",
    )


@router.post("/reprocess", response_model=DocumentBatchProcessResponse)
async def reprocess_documents(
    batch_request: DocumentBatchProcessRequest,
    background_tasks: BackgroundTasks,
    current_user: CurrentUserDep,
    current_tenant: CurrentTenantDep,
    db: DatabaseDep,
    document_service: DocumentServiceDep,
):
    tenant_id = str(current_tenant.id)
    requested_ids = [str(value) for value in batch_request.document_ids] if batch_request.document_ids else []

    documents, missing = document_service.select_documents_for_reprocessing(
        db=db,
        tenant_id=tenant_id,
        document_ids=requested_ids or None,
        status_filter=batch_request.status,
        limit=batch_request.limit,
    )

    matched = len(documents)
    requested = len(requested_ids) if requested_ids else matched

    results: List[DocumentBatchProcessItem] = []
    scheduled = 0
    skipped = 0

    for document in documents:
        if document.status == "processed" and not batch_request.force:
            skipped += 1
            results.append(
                DocumentBatchProcessItem(
                    document_id=document.id,
                    action="skipped",
                    message="Document already processed; set force=true to reprocess.",
                )
            )
            continue

        background_tasks.add_task(
            document_service.process_document,
            db=db,
            document_id=str(document.id),
            tenant_id=tenant_id,
        )
        scheduled += 1
        results.append(
            DocumentBatchProcessItem(
                document_id=document.id,
                action="queued",
                message="Document scheduled for background processing",
            )
        )

    for missing_id in missing:
        results.append(
            DocumentBatchProcessItem(
                document_id=missing_id,
                action="missing",
                message="Document not found for tenant",
            )
        )

    logger.info(
        "Batch reprocess requested",
        extra={
            "tenant": tenant_id,
            "scheduled": scheduled,
            "skipped": skipped,
            "requested": requested,
            "missing": [str(value) for value in missing],
            "user": current_user.email,
        },
    )

    return DocumentBatchProcessResponse(
        requested=requested,
        matched=matched,
        scheduled=scheduled,
        skipped=skipped,
        missing=missing,
        results=results,
    )


@router.delete("/{document_id}")
async def delete_document(
    document_id: UUID,
    current_user: CurrentUserDep,
    current_tenant: CurrentTenantDep,
    db: DatabaseDep,
    document_service: DocumentServiceDep,
):
    success = await document_service.delete_document(db, str(document_id), str(current_tenant.id))
    if not success:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found")
    return {"message": "Document deleted"}


@router.get("/{document_id}/chunks", response_model=List[DocumentChunkResponse])
async def get_document_chunks(
    document_id: UUID,
    current_user: CurrentUserDep,
    current_tenant: CurrentTenantDep,
    db: DatabaseDep,
    document_service: DocumentServiceDep,
    skip: int = 0,
    limit: int = 50,
):
    document = document_service.get_document(db, str(document_id), str(current_tenant.id))
    if not document:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found")

    chunks = (
        db.query(DocumentChunk)
        .filter(DocumentChunk.document_id == document.id)
        .order_by(DocumentChunk.chunk_index)
        .offset(max(skip, 0))
        .limit(max(limit, 1))
        .all()
    )
    return chunks


@router.post("/search", response_model=DocumentSearchResponse)
async def search_documents(
    search_request: DocumentSearchRequest,
    current_user: CurrentUserDep,
    current_tenant: CurrentTenantDep,
    db: DatabaseDep,
    vector_service: VectorServiceDep,
    embedding_service: EmbeddingServiceDep,
):
    start_time = time.perf_counter()

    query_embedding = await embedding_service.embed_text(search_request.query)

    filter_conditions = {}
    if search_request.document_ids:
        filter_conditions["document_id"] = [str(doc_id) for doc_id in search_request.document_ids]
    if search_request.tags:
        filter_conditions["tags"] = search_request.tags
    if search_request.document_types:
        filter_conditions["document_type"] = [value.strip() for value in search_request.document_types if value]

    created_range = _build_created_at_range(search_request.created_after, search_request.created_before)
    if created_range:
        filter_conditions["created_at_ts"] = created_range

    results = await vector_service.search_documents(
        tenant_id=str(current_tenant.id),
        query_embedding=query_embedding,
        limit=search_request.limit,
        score_threshold=search_request.score_threshold,
        filter_conditions=filter_conditions or None,
    )

    formatted: List[DocumentSearchResult] = []
    for result in results:
        document_id = result.get("document_id")
        chunk_id = result.get("chunk_id") or result.get("id")
        if not chunk_id:
            chunk_uuid = uuid4()
        else:
            try:
                chunk_uuid = UUID(str(chunk_id))
            except ValueError:
                chunk_uuid = uuid4()
        try:
            document_uuid = UUID(str(document_id)) if document_id else uuid4()
        except ValueError:
            document_uuid = uuid4()

        formatted.append(
            DocumentSearchResult(
                chunk_id=chunk_uuid,
                document_id=document_uuid,
                score=float(result.get("score", 0.0)),
                text=result.get("text", ""),
                source=result.get("source", ""),
                page_number=result.get("page_number"),
                chunk_index=int(result.get("chunk_index", 0)),
                doc_metadata=result.get("metadata", {}),
            )
        )

    elapsed_ms = (time.perf_counter() - start_time) * 1000.0
    return DocumentSearchResponse(
        query=search_request.query,
        results=formatted,
        total_found=len(formatted),
        search_time_ms=elapsed_ms,
    )


def _build_created_at_range(
    created_after: Optional[datetime],
    created_before: Optional[datetime],
) -> Optional[Dict[str, float]]:
    if not created_after and not created_before:
        return None

    range_payload: Dict[str, float] = {}

    if created_after:
        range_payload["gte"] = _to_utc_timestamp(created_after)
    if created_before:
        range_payload["lte"] = _to_utc_timestamp(created_before)

    return range_payload or None


def _to_utc_timestamp(value: datetime) -> float:
    if value.tzinfo is None:
        normalized = value.replace(tzinfo=UTC)
    else:
        normalized = value.astimezone(UTC)
    return normalized.timestamp()
