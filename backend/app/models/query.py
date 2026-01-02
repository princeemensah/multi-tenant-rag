"""Query tracking ORM models."""
import uuid
from datetime import datetime

from sqlalchemy import Boolean, Column, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import relationship

from app.database.base import Base


class Query(Base):
    __tablename__ = "queries"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id = Column(UUID(as_uuid=True), ForeignKey("tenants.id"), nullable=False, index=True)
    user_id = Column(UUID(as_uuid=True), ForeignKey("tenant_users.id"), nullable=False, index=True)

    query_text = Column(Text, nullable=False)
    query_type = Column(String(50), default="search")

    processing_time_ms = Column(Float, nullable=True)
    status = Column(String(50), default="completed", index=True)

    retrieved_chunks_count = Column(Integer, default=0)
    retrieved_documents = Column(JSONB, default=list)
    similarity_threshold = Column(Float, default=0.7)

    llm_provider = Column(String(50), nullable=True)
    llm_model = Column(String(100), nullable=True)
    prompt_template = Column(Text, nullable=True)

    input_tokens = Column(Integer, default=0)
    output_tokens = Column(Integer, default=0)
    total_tokens = Column(Integer, default=0)
    estimated_cost = Column(Float, default=0.0)

    user_rating = Column(Integer, nullable=True)
    feedback = Column(Text, nullable=True)

    session_id = Column(String(100), nullable=True, index=True)
    conversation_turn = Column(Integer, default=1)

    query_metadata = Column(JSONB, default=dict)

    created_at = Column(DateTime, default=datetime.utcnow, index=True)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    tenant = relationship("Tenant", back_populates="queries")
    user = relationship("TenantUser", back_populates="queries")
    response = relationship("QueryResponse", back_populates="query", uselist=False)

    def __repr__(self) -> str:  # pragma: no cover
        snippet = (self.query_text or "")[:50]
        return f"<Query id={self.id} tenant={self.tenant_id} query_text={snippet!r}>"


class QueryResponse(Base):
    __tablename__ = "query_responses"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    query_id = Column(UUID(as_uuid=True), ForeignKey("queries.id"), nullable=False, unique=True, index=True)

    response_text = Column(Text, nullable=False)
    response_format = Column(String(50), default="text")

    context_used = Column(Text, nullable=True)
    context_chunks = Column(JSONB, default=list)

    confidence_score = Column(Float, nullable=True)
    source_attribution = Column(JSONB, default=list)

    contains_citations = Column(Boolean, default=False)
    fact_checked = Column(Boolean, default=False)
    is_cached = Column(Boolean, default=False)
    cache_hit = Column(Boolean, default=False)

    generated_at = Column(DateTime, default=datetime.utcnow, index=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    query = relationship("Query", back_populates="response")

    def __repr__(self) -> str:  # pragma: no cover
        return f"<QueryResponse id={self.id} query_id={self.query_id}>"
