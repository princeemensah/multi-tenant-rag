"""Document-related Pydantic schemas."""
from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field, model_validator


class DocumentUpload(BaseModel):
    """Optional metadata submitted alongside uploaded files."""

    title: str | None = None
    tags: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class DocumentResponse(BaseModel):
    """Primary document serialization schema."""

    id: UUID
    tenant_id: UUID
    filename: str
    original_filename: str
    content_type: str
    file_size: int
    status: str
    total_chunks: int
    processed_chunks: int
    title: str | None = None
    summary: str | None = None
    language: str
    word_count: int
    collection_name: str | None = None
    embedding_model: str | None = None
    doc_metadata: dict[str, Any]
    tags: list[str]
    uploaded_at: datetime
    processed_at: datetime | None = None
    created_at: datetime

    class Config:
        from_attributes = True


class DocumentList(BaseModel):
    """Paginated document listing."""

    documents: list[DocumentResponse]
    total: int
    page: int
    size: int
    pages: int


class DocumentProcessResponse(BaseModel):
    """Result of a document processing trigger."""

    document_id: UUID
    status: str
    message: str
    chunks_created: int | None = None


class DocumentChunkResponse(BaseModel):
    """Serialized representation of stored document chunks."""

    id: UUID
    document_id: UUID
    chunk_index: int
    text_content: str
    chunk_size: int
    start_char: int | None = None
    end_char: int | None = None
    page_number: int | None = None
    vector_id: str | None = None
    embedding_model: str | None = None
    embedding_dimension: int | None = None
    doc_metadata: dict[str, Any]
    created_at: datetime

    class Config:
        from_attributes = True


class DocumentSearchRequest(BaseModel):
    """Query payload for semantic search."""

    query: str
    limit: int = Field(default=10, ge=1, le=50)
    score_threshold: float = Field(default=0.7, ge=0.0, le=1.0)
    offset: int = Field(default=0, ge=0)
    document_ids: list[UUID] | None = None
    tags: list[str] | None = None
    document_types: list[str] | None = None
    created_after: datetime | None = None
    created_before: datetime | None = None


class DocumentSearchResult(BaseModel):
    """Single search hit returned from the vector store."""

    chunk_id: UUID
    document_id: UUID
    score: float
    text: str
    source: str
    page_number: int | None = None
    chunk_index: int
    doc_metadata: dict[str, Any]


class DocumentSearchResponse(BaseModel):
    """Semantic search response wrapper."""

    query: str
    results: list[DocumentSearchResult]
    total_found: int
    search_time_ms: float
    offset: int
    next_offset: int | None = None
    has_more: bool = False
    scores: list[float] = Field(default_factory=list)


class DocumentBatchProcessRequest(BaseModel):
    """Batch trigger payload for document reprocessing."""

    document_ids: list[UUID] | None = None
    status: str | None = Field(default=None, max_length=64)
    limit: int | None = Field(default=None, ge=1, le=500)
    force: bool = False

    @model_validator(mode="after")
    def ensure_scope(cls, values: "DocumentBatchProcessRequest") -> "DocumentBatchProcessRequest":
        if not values.document_ids and not values.status and not values.limit:
            raise ValueError("Provide document_ids, status, or limit to scope reprocessing")
        return values


class DocumentBatchProcessItem(BaseModel):
    """Outcome for an individual document queued during batch processing."""

    document_id: UUID
    action: str
    message: str


class DocumentBatchProcessResponse(BaseModel):
    """Summary response for batch document processing triggers."""

    requested: int
    matched: int
    scheduled: int
    skipped: int
    missing: list[UUID]
    results: list[DocumentBatchProcessItem]

