"""Query and RAG schemas."""
from datetime import datetime
from typing import Any, Dict, List, Optional
from uuid import UUID

from pydantic import BaseModel, Field


class QueryRequest(BaseModel):
    """Basic query invocation payload."""

    query_text: str = Field(..., min_length=1, max_length=1000)
    query_type: str = Field(default="search")
    session_id: Optional[str] = None


class RAGRequest(BaseModel):
    """Semantic-retrieval + generation request payload."""

    query: str = Field(..., min_length=1, max_length=1000)
    max_chunks: int = Field(default=5, ge=1, le=20)
    score_threshold: float = Field(default=0.7, ge=0.0, le=1.0)
    document_ids: Optional[List[UUID]] = None
    tags: Optional[List[str]] = None
    llm_provider: Optional[str] = None
    llm_model: Optional[str] = None
    temperature: float = Field(default=0.7, ge=0.0, le=2.0)
    max_tokens: int = Field(default=1000, ge=100, le=4000)
    system_prompt: Optional[str] = None
    session_id: Optional[str] = None
    conversation_turn: int = Field(default=1, ge=1)
    stream: bool = Field(default=False)
    include_sources: bool = Field(default=True)


class ContextDocument(BaseModel):
    """Chunk of context surfaced for a RAG response."""

    chunk_id: str
    document_id: str
    score: float
    text: str
    source: str
    page_number: Optional[int] = None
    chunk_index: int
    doc_metadata: Dict[str, Any]


class RAGResponse(BaseModel):
    """Full RAG response payload returned to clients."""

    query_id: UUID
    query: str
    response: str
    context_documents: List[ContextDocument]
    context_used: str
    processing_time_ms: float
    llm_provider: str
    llm_model: str
    input_tokens: int
    output_tokens: int
    total_tokens: int
    estimated_cost: float
    confidence_score: Optional[float] = None
    source_attribution: List[str]
    contains_citations: bool
    session_id: Optional[str] = None
    conversation_turn: int
    created_at: datetime


class QueryResponseData(BaseModel):
    """Generated answer metadata stored separately from the query."""

    id: UUID
    query_id: UUID
    response_text: str
    response_format: str
    context_used: Optional[str] = None
    context_chunks: List[Any]
    confidence_score: Optional[float] = None
    source_attribution: List[str]
    contains_citations: bool
    fact_checked: bool
    is_cached: bool
    cache_hit: bool
    generated_at: datetime

    class Config:
        from_attributes = True


class QueryResponse(BaseModel):
    """Stored query metadata and associated response."""

    id: UUID
    tenant_id: UUID
    user_id: UUID
    query_text: str
    query_type: str
    processing_time_ms: Optional[float] = None
    status: str
    retrieved_chunks_count: int
    retrieved_documents: List[UUID]
    similarity_threshold: float
    llm_provider: Optional[str] = None
    llm_model: Optional[str] = None
    input_tokens: int
    output_tokens: int
    total_tokens: int
    estimated_cost: float
    user_rating: Optional[int] = None
    feedback: Optional[str] = None
    session_id: Optional[str] = None
    conversation_turn: int
    query_metadata: Dict[str, Any]
    created_at: datetime
    response: Optional[QueryResponseData] = None

    class Config:
        from_attributes = True


class QueryHistory(BaseModel):
    """Paginated history response."""

    queries: List[QueryResponse]
    total: int
    page: int
    size: int
    pages: int


class QueryFeedback(BaseModel):
    """Feedback submission payload."""

    query_id: UUID
    rating: int = Field(..., ge=1, le=5)
    feedback: Optional[str] = None


class QueryAnalytics(BaseModel):
    """Aggregated analytics for a tenant's queries."""

    tenant_id: UUID
    total_queries: int
    queries_today: int
    avg_processing_time_ms: float
    avg_tokens_per_query: float
    total_cost: float
    top_query_types: List[Dict[str, Any]]
    avg_rating: Optional[float] = None
    period_start: datetime
    period_end: datetime


QueryResponse.model_rebuild()
