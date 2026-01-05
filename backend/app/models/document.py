"""Document ORM models."""
import uuid
from datetime import UTC, datetime

from sqlalchemy import Column, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import relationship

from app.database.base import Base


def _utcnow() -> datetime:
    """Return a timezone-aware UTC timestamp for SQLAlchemy defaults."""
    return datetime.now(UTC)


class Document(Base):
    __tablename__ = "documents"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id = Column(UUID(as_uuid=True), ForeignKey("tenants.id"), nullable=False, index=True)

    filename = Column(String(255), nullable=False)
    original_filename = Column(String(255), nullable=False)
    content_type = Column(String(100), nullable=False)
    file_size = Column(Integer, nullable=False)
    file_path = Column(String(500), nullable=False)

    status = Column(String(50), default="uploaded", index=True)
    total_chunks = Column(Integer, default=0)
    processed_chunks = Column(Integer, default=0)

    title = Column(String(500), nullable=True)
    summary = Column(Text, nullable=True)
    language = Column(String(10), default="en")
    word_count = Column(Integer, default=0)

    collection_name = Column(String(100), nullable=True)
    embedding_model = Column(String(100), nullable=True)

    doc_metadata = Column(JSONB, default=dict)
    tags = Column(JSONB, default=list)

    uploaded_at = Column(DateTime, default=_utcnow, index=True)
    processed_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=_utcnow)
    updated_at = Column(DateTime, default=_utcnow, onupdate=_utcnow)

    tenant = relationship("Tenant", back_populates="documents")
    chunks = relationship("DocumentChunk", back_populates="document", cascade="all, delete-orphan")

    def __repr__(self) -> str:  # pragma: no cover
        return f"<Document id={self.id} filename={self.filename!r} tenant={self.tenant_id}>"


class DocumentChunk(Base):
    __tablename__ = "document_chunks"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    document_id = Column(UUID(as_uuid=True), ForeignKey("documents.id"), nullable=False, index=True)
    tenant_id = Column(UUID(as_uuid=True), ForeignKey("tenants.id"), nullable=False, index=True)

    chunk_index = Column(Integer, nullable=False)
    text_content = Column(Text, nullable=False)
    chunk_size = Column(Integer, nullable=False)

    start_char = Column(Integer, nullable=True)
    end_char = Column(Integer, nullable=True)
    page_number = Column(Integer, nullable=True)

    vector_id = Column(String(100), nullable=True, index=True)
    embedding_model = Column(String(100), nullable=True)
    embedding_dimension = Column(Integer, nullable=True)

    last_similarity_score = Column(Float, nullable=True)
    doc_metadata = Column(JSONB, default=dict)

    created_at = Column(DateTime, default=_utcnow, index=True)
    updated_at = Column(DateTime, default=_utcnow, onupdate=_utcnow)

    document = relationship("Document", back_populates="chunks")
    tenant = relationship("Tenant")

    def __repr__(self) -> str:  # pragma: no cover
        return f"<DocumentChunk id={self.id} document={self.document_id}>"
