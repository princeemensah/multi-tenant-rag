"""Tenant-related ORM models."""
import uuid
from datetime import datetime

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from app.database.base import Base


class Tenant(Base):
    __tablename__ = "tenants"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String(255), nullable=False, index=True)
    subdomain = Column(String(63), unique=True, nullable=True, index=True)

    llm_provider = Column(String(50), default="openai")
    llm_model = Column(String(100), default="gpt-4o-mini")
    embedding_model = Column(String(100), default="sentence-transformers/all-MiniLM-L6-v2")
    max_documents = Column(Integer, default=1000)
    max_queries_per_day = Column(Integer, default=10000)

    is_active = Column(Boolean, default=True, index=True)
    created_at = Column(DateTime, default=datetime.utcnow, index=True)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    users = relationship("TenantUser", back_populates="tenant", cascade="all, delete-orphan")
    documents = relationship("Document", back_populates="tenant", cascade="all, delete-orphan")
    queries = relationship("Query", back_populates="tenant", cascade="all, delete-orphan")
    tasks = relationship("Task", back_populates="tenant", cascade="all, delete-orphan")
    incidents = relationship("Incident", back_populates="tenant", cascade="all, delete-orphan")
    conversations = relationship("ConversationSession", back_populates="tenant", cascade="all, delete-orphan")
    conversation_messages = relationship(
        "ConversationMessage",
        back_populates="tenant",
        cascade="all, delete-orphan",
    )

    def __repr__(self) -> str:  # pragma: no cover - debugging
        return f"<Tenant id={self.id} name={self.name!r}>"


class TenantUser(Base):
    __tablename__ = "tenant_users"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id = Column(UUID(as_uuid=True), ForeignKey("tenants.id"), nullable=False, index=True)

    email = Column(String(255), nullable=False, index=True)
    username = Column(String(100), nullable=False)
    hashed_password = Column(String(255), nullable=False)

    role = Column(String(50), default="user")
    permissions = Column(Text)

    is_active = Column(Boolean, default=True, index=True)
    email_verified = Column(Boolean, default=False)
    last_login = Column(DateTime, nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow, index=True)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    tenant = relationship("Tenant", back_populates="users")
    queries = relationship("Query", back_populates="user", cascade="all, delete-orphan")
    created_tasks = relationship("Task", foreign_keys="Task.created_by_id", back_populates="created_by")
    assigned_tasks = relationship("Task", foreign_keys="Task.assigned_to_id", back_populates="assigned_to")
    reported_incidents = relationship("Incident", foreign_keys="Incident.reported_by_id", back_populates="reported_by")
    created_conversations = relationship(
        "ConversationSession",
        foreign_keys="ConversationSession.created_by_id",
        back_populates="created_by",
    )
    conversation_messages = relationship(
        "ConversationMessage",
        foreign_keys="ConversationMessage.author_id",
        back_populates="author",
    )

    def __repr__(self) -> str:  # pragma: no cover
        return f"<TenantUser id={self.id} email={self.email!r} tenant_id={self.tenant_id}>"
