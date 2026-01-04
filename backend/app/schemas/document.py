"""Document-related Pydantic schemas."""
from datetime import datetime
from typing import Any, Dict, List, Optional
from uuid import UUID

from pydantic import BaseModel, Field


class DocumentUpload(BaseModel):
    """Optional metadata submitted alongside uploaded files."""

    title: Optional[str] = None
    tags: List[str] = Field(default_factory=list)
    metadata: Dict[str, Any] = Field(default_factory=dict)


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
    title: Optional[str] = None
    summary: Optional[str] = None
    language: str
    word_count: int
    collection_name: Optional[str] = None
    embedding_model: Optional[str] = None
    doc_metadata: Dict[str, Any]
    tags: List[str]
    uploaded_at: datetime
    processed_at: Optional[datetime] = None
    created_at: datetime

    class Config:
        from_attributes = True


class DocumentList(BaseModel):
    """Paginated document listing."""

    documents: List[DocumentResponse]
    total: int
    page: int
    size: int
    pages: int


class DocumentProcessResponse(BaseModel):
    """Result of a document processing trigger."""

    document_id: UUID
    status: str
    message: str
    chunks_created: Optional[int] = None


class DocumentChunkResponse(BaseModel):
    """Serialized representation of stored document chunks."""

    id: UUID
    document_id: UUID
    chunk_index: int
    text_content: str
    chunk_size: int
    start_char: Optional[int] = None
    end_char: Optional[int] = None
    page_number: Optional[int] = None
    vector_id: Optional[str] = None
    embedding_model: Optional[str] = None
    embedding_dimension: Optional[int] = None
    doc_metadata: Dict[str, Any]
    created_at: datetime

    class Config:
        from_attributes = True


class DocumentSearchRequest(BaseModel):
    """Query payload for semantic search."""

    query: str
    limit: int = Field(default=10, ge=1, le=50)
    score_threshold: float = Field(default=0.7, ge=0.0, le=1.0)
    document_ids: Optional[List[UUID]] = None
    tags: Optional[List[str]] = None
    document_types: Optional[List[str]] = None
    created_after: Optional[datetime] = None
    created_before: Optional[datetime] = None


class DocumentSearchResult(BaseModel):
    """Single search hit returned from the vector store."""

    chunk_id: UUID
    document_id: UUID
    score: float
    text: str
    source: str
    page_number: Optional[int] = None
    chunk_index: int
    doc_metadata: Dict[str, Any]


class DocumentSearchResponse(BaseModel):
    """Semantic search response wrapper."""

    query: str
    results: List[DocumentSearchResult]
    total_found: int
    search_time_ms: float

