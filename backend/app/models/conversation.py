"""Conversation session and message models for tenant chat history."""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import relationship

from app.database.base import Base


class ConversationSession(Base):
    """Represents a persisted chat session for a tenant."""

    __tablename__ = "conversation_sessions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id = Column(UUID(as_uuid=True), ForeignKey("tenants.id"), nullable=False, index=True)
    created_by_id = Column(UUID(as_uuid=True), ForeignKey("tenant_users.id"), nullable=True, index=True)

    title = Column(String(255), nullable=False)
    message_count = Column(Integer, default=0)

    created_at = Column(DateTime, default=datetime.utcnow, index=True)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    tenant = relationship("Tenant", back_populates="conversations")
    created_by = relationship("TenantUser", back_populates="created_conversations")
    messages = relationship(
        "ConversationMessage",
        back_populates="conversation",
        cascade="all, delete-orphan",
        order_by="ConversationMessage.created_at",
    )

    def __repr__(self) -> str:  # pragma: no cover
        return f"<ConversationSession id={self.id} tenant={self.tenant_id} title={self.title!r}>"


class ConversationMessage(Base):
    """Individual message within a conversation session."""

    __tablename__ = "conversation_messages"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    conversation_id = Column(UUID(as_uuid=True), ForeignKey("conversation_sessions.id"), nullable=False, index=True)
    tenant_id = Column(UUID(as_uuid=True), ForeignKey("tenants.id"), nullable=False, index=True)
    author_id = Column(UUID(as_uuid=True), ForeignKey("tenant_users.id"), nullable=True, index=True)

    role = Column(String(32), nullable=False)
    content = Column(Text, nullable=False)
    message_metadata = Column("metadata", JSONB, default=dict)
    sequence = Column(Integer, nullable=False)

    created_at = Column(DateTime, default=datetime.utcnow, index=True)

    conversation = relationship("ConversationSession", back_populates="messages")
    tenant = relationship("Tenant", back_populates="conversation_messages")
    author = relationship("TenantUser", back_populates="conversation_messages")

    def __repr__(self) -> str:  # pragma: no cover
        return f"<ConversationMessage id={self.id} conversation={self.conversation_id} role={self.role}>"
